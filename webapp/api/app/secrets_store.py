"""Where third-party credentials live. Nothing else in the app ever holds a secret value:
the database keeps only an opaque reference (`secret_ref`) and the last 4 characters for display.

  local  values encrypted with Fernet (AES-128-CBC + HMAC-SHA256) under SECRETS_KEY, stored in `secret_values`
  aws    AWS Secrets Manager, one secret per brand connection: <SECRETS_AWS_PREFIX>/brand/<brand_id>/<provider>
"""
import uuid
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import LargeBinary, String, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import get_settings
from .db import Base, SessionLocal


class SecretValue(Base):
    __tablename__ = "secret_values"
    ref: Mapped[str] = mapped_column(String(300), primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)


class SecretsUnavailable(RuntimeError):
    pass


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().secrets_key
    if not key:
        raise SecretsUnavailable("SECRETS_KEY is not set: connections can't store credentials")
    return Fernet(key.encode())


@lru_cache
def _aws():
    import boto3
    return boto3.client("secretsmanager", region_name=get_settings().s3_region)


def ref_for(brand_id: uuid.UUID, provider: str) -> str:
    return f"{get_settings().secrets_aws_prefix}/brand/{brand_id}/{provider}"


def put(db: Session, ref: str, value: str) -> None:
    if get_settings().secrets_backend == "aws":
        try:
            _aws().put_secret_value(SecretId=ref, SecretString=value)
        except _aws().exceptions.ResourceNotFoundException:
            _aws().create_secret(Name=ref, SecretString=value)
        return
    token = _fernet().encrypt(value.encode())
    row = db.get(SecretValue, ref)
    if row:
        row.ciphertext = token
    else:
        db.add(SecretValue(ref=ref, ciphertext=token))


def get(ref: str) -> str | None:
    """Read a secret (workers and verification only; never returned by any API)."""
    if get_settings().secrets_backend == "aws":
        try:
            return _aws().get_secret_value(SecretId=ref)["SecretString"]
        except _aws().exceptions.ResourceNotFoundException:
            return None
    with SessionLocal() as db:
        row = db.get(SecretValue, ref)
        if not row:
            return None
        try:
            return _fernet().decrypt(row.ciphertext).decode()
        except InvalidToken as e:
            raise SecretsUnavailable("stored secret can't be decrypted (SECRETS_KEY changed?)") from e


def remove(db: Session, ref: str) -> None:
    if get_settings().secrets_backend == "aws":
        try:
            _aws().delete_secret(SecretId=ref, ForceDeleteWithoutRecovery=True)
        except _aws().exceptions.ResourceNotFoundException:
            pass
        return
    db.execute(delete(SecretValue).where(SecretValue.ref == ref))


def exists(db: Session, ref: str) -> bool:
    if get_settings().secrets_backend == "aws":
        return get(ref) is not None
    return db.scalar(select(SecretValue.ref).where(SecretValue.ref == ref)) is not None
