"""The environment a brand's job runs with: that brand's connected keys under the names the vs engine reads, and
nothing from any other brand. Values are read from the secrets backend at job time and never written to disk."""
import logging
import uuid

from sqlalchemy import select

from . import secrets_store
from .db import SessionLocal
from .models import Connection, ConnStatus
from .providers import PROVIDERS

log = logging.getLogger(__name__)


def brand_env(brand_id: uuid.UUID) -> dict[str, str]:
    with SessionLocal() as db:
        conns = db.scalars(select(Connection).where(Connection.brand_id == brand_id,
                                                    Connection.status == ConnStatus.connected)).all()
        refs = [(c.provider, c.secret_ref) for c in conns if c.secret_ref]
    env = {}
    for pid, ref in refs:
        p = PROVIDERS.get(pid)
        if not p or not p.env:
            continue
        try:
            value = secrets_store.get(ref)
        except secrets_store.SecretsUnavailable as e:
            log.warning("brand %s: %s not available: %s", brand_id, pid, e)
            continue
        if value:
            env[p.env] = value
    return env
