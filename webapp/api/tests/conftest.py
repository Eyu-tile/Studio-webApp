import os

os.environ.update({
    "STUDIO_ENV_FILE": "none", "ENV": "test", "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://studio:studio@localhost:5432/studio_test"),
    "S3_ENDPOINT_URL": "http://127.0.0.1:9011", "S3_ACCESS_KEY_ID": "test", "S3_SECRET_ACCESS_KEY": "test",
    "S3_BUCKET": "studio-test", "S3_CREATE_BUCKET": "true", "WORKER_ROOT": "/tmp/studio-test-worker", "AUTH_MODE": "dev", "BOOTSTRAP_ADMINS": "admin@example.com",
    "PUBLIC_URL": "http://localhost:3000", "SECRETS_KEY": "PI5rulZQPo_8m92ftc4VHBplQXwjsnZkUBs2qkOoY0U=", "LIBRARY_ALLOW_PRIVATE_HOSTS": "true"})

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from moto.server import ThreadedMotoServer  # noqa: E402
from sqlalchemy import text  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def s3():
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=9011)
    server.start()
    yield
    server.stop()


@pytest.fixture(scope="session", autouse=True)
def schema(s3):
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean(schema):
    from app.db import engine
    with engine.begin() as c:
        c.execute(text("TRUNCATE agent_transcript, agent_approvals, agent_messages, agent_threads, audit_events, secret_values, connect_links, connections, library_clips, library_sources, lessons, notes, versions, jobs, assets, projects, brand_members, brands, "
                       "auth_sessions, users RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def app():
    from app.main import app
    return app


def client_for(app, email, name=""):
    c = TestClient(app, headers={"X-Requested-With": "studio"})
    c.__enter__()
    r = c.post("/api/auth/dev-login", json={"email": email, "name": name})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def admin(app):
    return client_for(app, "admin@example.com", "Admin")


@pytest.fixture
def make_user(app, admin):
    def make(email):
        return client_for(app, email)
    return make
