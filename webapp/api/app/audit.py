import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditEvent, User
from .security import client_ip


def record(db: Session, actor: User | None, action: str, target: str = "", brand_id: uuid.UUID | None = None,
           request: Request | None = None, **details) -> None:
    """Add an audit row to the current transaction (committed with the change it describes)."""
    db.add(AuditEvent(actor_id=actor.id if actor else None, brand_id=brand_id, action=action, target=target[:200],
                      details={k: v for k, v in details.items() if v is not None},
                      ip=client_ip(request) if request else ""))
