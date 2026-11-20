import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import storage
from .config import get_settings
from .db import engine
from .events import _redis
from .routers import admin, agent, assets, auth, brands, connections, jobs, lessons, library, projects, reviews, workspace

logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","log":"%(name)s","msg":"%(message)s"}')
settings = get_settings()


@asynccontextmanager
async def lifespan(_app):
    if settings.s3_create_bucket:
        storage.ensure_bucket()
    yield


app = FastAPI(title=f"{settings.app_name} API", version="0.1.0", docs_url=f"{settings.api_prefix}/docs",
              openapi_url=f"{settings.api_prefix}/openapi.json", redoc_url=None, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.public_url], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, brands, projects, assets, jobs, reviews, connections, library, lessons, agent, admin, workspace):
    app.include_router(r.router, prefix=settings.api_prefix)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


@app.get(f"{settings.api_prefix}/healthz", tags=["health"])
def healthz():
    return {"ok": True}


@app.get(f"{settings.api_prefix}/readyz", tags=["health"])
def readyz():
    checks = {}
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"error: {e.__class__.__name__}"
    try:
        _redis().ping()
        checks["redis"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"error: {e.__class__.__name__}"
    try:
        storage.client().head_bucket(Bucket=storage.bucket())
        checks["storage"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["storage"] = f"error: {e.__class__.__name__}"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"ok": ok, **checks}, status_code=200 if ok else 503)
