"""All configuration comes from environment variables (12-factor). See webapp/.env.example."""
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # STUDIO_ENV_FILE=none (tests) reads only real environment variables, never a developer's .env
    model_config = SettingsConfigDict(env_file=None if os.environ.get("STUDIO_ENV_FILE") == "none" else (".env", "../.env"),
                                      env_file_encoding="utf-8", extra="ignore",
                                      env_ignore_empty=True)      # KEY= in an env file means "use the default"

    env: str = Field("development", description="development | test | production")
    app_name: str = "Studio"
    public_url: str = "http://localhost:3000"           # where the web app is served (cookies, redirects, CORS)
    api_prefix: str = "/api"
    secret_key: str = "dev-only-change-me"              # signs the short-lived sign-in state cookie; set in production

    database_url: str = "postgresql+psycopg://studio:studio@localhost:5432/studio"
    redis_url: str = "redis://localhost:6379/0"

    # S3-compatible storage (AWS S3, Cloudflare R2, MinIO)
    s3_bucket: str = "studio-media"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None                  # set for R2 / MinIO; unset for AWS
    s3_public_endpoint_url: str | None = None           # endpoint the browser uses, if different (docker networks)
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_presign_ttl: int = 900
    s3_create_bucket: bool = False                      # dev only: create the bucket and its CORS rule on start

    # Sign-in. dev: email only (refused in production). oidc: Google Workspace / Microsoft Entra / any OIDC issuer
    auth_mode: str = "dev"
    oidc_issuer: str | None = None                      # e.g. https://accounts.google.com
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_allowed_domains: str = ""                      # comma list, e.g. "nexa.studio"; empty = any verified email
    session_days: int = 14
    bootstrap_admins: str = ""                          # comma list of emails that become admins on first sign-in

    # Secrets for brand connections: "local" stores them encrypted (Fernet, key below) in the database;
    # "aws" keeps them in AWS Secrets Manager. Generate a key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secrets_backend: str = "local"
    secrets_key: str | None = None
    secrets_aws_prefix: str = "studio"
    # library links: never fetch private/internal addresses (cloud metadata, the cluster). Tests only may allow them.
    library_allow_private_hosts: bool = False

    # Workers
    worker_root: Path = Path("/tmp/studio-worker")
    worker_poll_seconds: float = 1.0
    worker_heartbeat_seconds: float = 5.0
    job_stale_seconds: int = 60
    job_max_attempts: int = 3
    vs_bin: Path = REPO_ROOT / "plugins" / "video-studio" / "bin" / "vs"
    whisper_model_dir: Path | None = None               # folder holding faster-whisper-<size>/ models (baked into images)

    # Claude engine: the video-studio plugin running in the Claude Agent SDK (Claude Code as a library) on workers.
    # Auth is any way Claude Code accepts: ANTHROPIC_API_KEY, or CLAUDE_CODE_USE_BEDROCK / CLAUDE_CODE_USE_VERTEX
    # with that cloud's credentials in the worker's environment.
    anthropic_api_key: str | None = None
    agent_model: str = "claude-opus-5-5"
    agent_fallback_model: str | None = None
    agent_effort: str | None = None                     # low | medium | high | xhigh | max (unset: model default)
    agent_max_turns: int = 80                           # tool round-trips per message before Claude stops and reports
    agent_turn_budget_usd: float = 5.0                  # hard cap per message; the thread total is shown to editors
    agent_approval_timeout_s: int = 1800                # an unanswered approval is denied after this
    agent_plugin_dir: Path = REPO_ROOT / "plugins" / "video-studio"
    claude_cli_path: str | None = None                  # the `claude` binary; unset uses the SDK's bundled CLI

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def admin_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.bootstrap_admins.split(",") if e.strip()}

    @property
    def allowed_domains(self) -> set[str]:
        return {d.strip().lower() for d in self.oidc_allowed_domains.split(",") if d.strip()}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.auth_mode == "dev":
        raise RuntimeError("AUTH_MODE=dev is not allowed in production: configure OIDC")
    if s.is_production and s.secrets_backend == "local" and not s.secrets_key:
        raise RuntimeError("set SECRETS_KEY (or SECRETS_BACKEND=aws) in production")
    if s.is_production and s.library_allow_private_hosts:
        raise RuntimeError("LIBRARY_ALLOW_PRIVATE_HOSTS is for tests only")
    if s.agent_turn_budget_usd <= 0:
        raise RuntimeError("AGENT_TURN_BUDGET_USD must be positive")
    if s.is_production and (len(s.secret_key) < 32 or "change-me" in s.secret_key):
        raise RuntimeError("set SECRET_KEY to 32+ random characters in production")
    return s
