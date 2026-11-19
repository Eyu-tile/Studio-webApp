"""Monthly budgets and caps, enforced before money is spent.

Two kinds of limit, both per brand and per calendar month (UTC), in USD:

  Claude budget   the studio's own Anthropic bill for that brand (Brand.claude_budget_monthly, default
                  AGENT_BRAND_MONTHLY_BUDGET_USD). A message is refused when the month's budget is used up; a turn
                  reserves its spending limit (a hold) before Claude starts and runs with at most what's left, so
                  concurrent turns can't overshoot together; the hold becomes the actual cost when the turn ends.
  Tool caps       the client's own accounts (Connection.spend_cap_monthly: Higgsfield, ElevenLabs, ...). A paid step
                  is declined outright once the month's cap is reached; approving one needs the approver's estimate
                  of its cost, and is refused if that would go over the cap.

Everything goes through the `spend_entries` ledger, so the numbers on screen are the numbers enforced.
"""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import utcnow
from .models import Brand, Connection, Job, JobStatus, SpendEntry

CLAUDE = "anthropic"
MIN_TURN_USD = 0.05            # below this a turn can't do anything useful: refuse instead of starting
LIVE = (JobStatus.queued, JobStatus.running)


class BudgetExhausted(Exception):
    """The money for this isn't there this month. The message is shown to the editor as is."""


def month_start(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def month_name(now: datetime | None = None) -> str:
    return (now or utcnow()).strftime("%B %Y")


def spent(db: Session, brand_id: uuid.UUID, provider: str, since: datetime | None = None) -> float:
    """This month's spend: actual costs and approved estimates, plus holds of turns still queued or running."""
    since = since or month_start()
    base = select(func.coalesce(func.sum(SpendEntry.amount_usd), 0.0)).where(
        SpendEntry.brand_id == brand_id, SpendEntry.provider == provider, SpendEntry.created_at >= since)
    done = db.scalar(base.where(SpendEntry.kind.in_(("actual", "estimate"))))
    held = db.scalar(base.join(Job, Job.id == SpendEntry.job_id).where(SpendEntry.kind == "hold",
                                                                        Job.status.in_(LIVE)))
    return round(float(done or 0) + float(held or 0), 4)


@dataclass
class Budget:
    limit: float | None          # None: no limit
    spent: float
    month: str

    @property
    def remaining(self) -> float | None:
        return None if self.limit is None else round(self.limit - self.spent, 4)

    @property
    def exhausted(self) -> bool:
        return self.limit is not None and self.spent >= self.limit - 1e-9

    def as_dict(self) -> dict:
        return {"limit_usd": self.limit, "spent_usd": self.spent, "remaining_usd": self.remaining,
                "month": self.month}


def claude_limit(brand: Brand) -> float | None:
    if brand.claude_budget_monthly is not None:
        return brand.claude_budget_monthly
    return get_settings().agent_brand_monthly_budget_usd


def claude_budget(db: Session, brand: Brand) -> Budget:
    return Budget(claude_limit(brand), spent(db, brand.id, CLAUDE), month_name())


def refuse_if_exhausted(db: Session, brand: Brand) -> None:
    b = claude_budget(db, brand)
    if b.limit == 0:
        raise BudgetExhausted(f"Claude is switched off for {brand.name} (monthly budget $0): an admin can set a "
                              "budget on the brand's Settings page")
    if b.exhausted:
        raise BudgetExhausted(f"{brand.name} has used its ${b.limit:,.2f} Claude budget for {b.month} "
                              f"(${b.spent:,.2f} spent): an admin can raise it on the brand's Settings page")


def hold_for_turn(db: Session, brand_id: uuid.UUID, job_id: uuid.UUID, want: float) -> float:
    """Reserve up to `want` of this month's Claude budget for a turn and return the amount: the turn's spending
    limit. The brand row is locked, so two turns starting together can't both take the last dollars."""
    brand = db.scalar(select(Brand).where(Brand.id == brand_id).with_for_update())
    refuse_if_exhausted(db, brand)
    b = claude_budget(db, brand)
    amount = want if b.remaining is None else min(want, b.remaining)
    if amount < MIN_TURN_USD:
        raise BudgetExhausted(f"only ${max(b.remaining or 0, 0):,.2f} of {brand.name}'s Claude budget is left for "
                              f"{b.month}: an admin can raise it on the brand's Settings page")
    db.add(SpendEntry(brand_id=brand_id, provider=CLAUDE, kind="hold", amount_usd=amount, job_id=job_id,
                      note="reserved while the turn runs"))
    db.commit()
    return amount


def settle_turn(db: Session, brand_id: uuid.UUID, job_id: uuid.UUID, cost: float | None, held: float,
                thread_id: uuid.UUID | None = None) -> float:
    """Replace a turn's hold with what it cost. Unknown cost (the turn broke off before Claude reported one) is
    counted as the whole hold: it may have spent that much."""
    db.execute(delete(SpendEntry).where(SpendEntry.job_id == job_id, SpendEntry.kind == "hold"))
    amount = held if cost is None else float(cost)
    if amount > 0:
        db.add(SpendEntry(brand_id=brand_id, provider=CLAUDE, kind="actual", amount_usd=round(amount, 6),
                          job_id=job_id, thread_id=thread_id,
                          note="" if cost is not None else "cost not reported: counted as the turn's limit"))
    db.commit()
    return amount


# --- tool caps (the client's own accounts) ---------------------------------------------------------------------------

def cap_budget(db: Session, conn: Connection) -> Budget:
    return Budget(conn.spend_cap_monthly, spent(db, conn.brand_id, conn.provider), month_name())


def cap_reached(db: Session, conn: Connection | None) -> str | None:
    """Why a paid step on this account is declined outright this month, or None."""
    if conn is None or conn.spend_cap_monthly is None:
        return None
    b = cap_budget(db, conn)
    if b.exhausted:
        return (f"the ${b.limit:,.2f} monthly cap on this client's account is reached for {b.month} "
                f"(${b.spent:,.2f} approved): a lead can raise it on the brand's Connections page")
    return None


def approve_paid(db: Session, conn: Connection | None, cost: float | None, approval_id: uuid.UUID,
                 thread_id: uuid.UUID) -> None:
    """Count an approved paid step against its account's cap. With a cap the approver's estimate is required, and an
    approval that would go over the cap is refused. Locks the connection so two approvals can't both fit."""
    if conn is not None:
        conn = db.scalar(select(Connection).where(Connection.id == conn.id).with_for_update())
    capped = conn is not None and conn.spend_cap_monthly is not None
    if capped and cost is None:
        raise BudgetExhausted("this account has a monthly cap: enter the estimated cost to approve")
    if capped:
        b = cap_budget(db, conn)
        if b.spent + cost > conn.spend_cap_monthly + 1e-9:
            raise BudgetExhausted(f"approving this (${cost:,.2f}) would go over the ${b.limit:,.2f} monthly cap "
                                  f"(${b.spent:,.2f} approved in {b.month}): raise the cap on the Connections page "
                                  "or decline")
    if conn is not None and cost:
        db.add(SpendEntry(brand_id=conn.brand_id, provider=conn.provider, kind="estimate", amount_usd=cost,
                          thread_id=thread_id, approval_id=approval_id, note="approved paid step"))
