"""The Agent SDK's SessionStore, backed by Postgres: Claude Code still writes its transcript to the worker's disk, and
the SDK mirrors every entry here. `resume` loads it back, so the next message in a conversation can run on any
worker (containers are disposable; the conversation is not)."""
import asyncio
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from .db import SessionLocal
from .models import AgentTranscriptEntry as T


def _sub(key: dict) -> str:
    return key.get("subpath") or ""


class PgSessionStore:
    """Implements append/load (required) plus list_subkeys and delete (optional) of claude_agent_sdk.SessionStore."""

    async def append(self, key: dict, entries: list[dict[str, Any]]) -> None:
        if entries:
            await asyncio.to_thread(self._append, key, entries)

    def _append(self, key: dict, entries: list[dict]) -> None:
        rows = [{"project_key": key["project_key"], "session_id": key["session_id"], "subpath": _sub(key),
                 "uuid": e.get("uuid") or None, "entry": e} for e in entries]
        with SessionLocal() as db:
            # entries carrying a uuid are idempotent (the SDK retries batches); others are appended as they come
            for r in rows:
                if r["uuid"]:
                    db.execute(insert(T).values(**r).on_conflict_do_nothing(
                        index_elements=["project_key", "session_id", "subpath", "uuid"],
                        index_where=T.uuid.isnot(None)))
                else:
                    db.add(T(**r))
            db.commit()

    async def load(self, key: dict) -> list[dict[str, Any]] | None:
        return await asyncio.to_thread(self._load, key)

    def _load(self, key: dict) -> list[dict] | None:
        with SessionLocal() as db:
            rows = db.scalars(select(T.entry).where(T.project_key == key["project_key"],
                                                    T.session_id == key["session_id"], T.subpath == _sub(key))
                              .order_by(T.id)).all()
        return list(rows) or None

    async def list_subkeys(self, key: dict) -> list[str]:
        def run():
            with SessionLocal() as db:
                return [s for s in db.scalars(select(T.subpath).distinct().where(
                    T.project_key == key["project_key"], T.session_id == key["session_id"], T.subpath != ""))]
        return await asyncio.to_thread(run)

    async def delete(self, key: dict) -> None:
        def run():
            with SessionLocal() as db:
                q = delete(T).where(T.project_key == key["project_key"], T.session_id == key["session_id"])
                if key.get("subpath"):
                    q = q.where(T.subpath == key["subpath"])
                db.execute(q)
                db.commit()
        await asyncio.to_thread(run)
