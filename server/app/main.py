"""FastAPI entrypoint for FreeCADAI SaaS."""

from fastapi import FastAPI

from server.app.api.admin import auth_router as admin_auth_router
from server.app.api.admin import billing_router
from server.app.api.admin import router as admin_router
from server.app.api.console import auth_router as console_auth_router
from server.app.api.console import public_router as console_public_router
from server.app.api.console import router as console_router
from server.app.api.plugin import router as plugin_router
from server.app.core.config import settings
from server.app.core.redis import redis_ping
from server.app.db.migrations import migrate_database
from server.app.db.session import SessionLocal
from server.app.services.assets import backfill_script_assets
from server.app.services.auth import ensure_default_admin
from server.app.services.default_templates import ensure_default_templates

# Import models so create_all can discover them in the phase 4 prototype.
from server.app.models import entities  # noqa: F401


app = FastAPI(title=settings.app_name, version="0.4.0")
app.include_router(plugin_router)
app.include_router(billing_router)
app.include_router(admin_auth_router)
app.include_router(admin_router)
app.include_router(console_auth_router)
app.include_router(console_public_router)
app.include_router(console_router)


@app.get("/")
def root():
    return {
        "ok": True,
        "service": settings.app_name,
        "message": "FreeCADAI SaaS is running.",
        "health": "/health",
        "docs": "/docs",
        "admin": "/admin",
        "plugin_base": "/api/v1/plugin",
        "admin_base": "/api/v1/admin",
        "console_base": "/api/v1/console",
    }


@app.on_event("startup")
def startup():
    if settings.auto_migrate:
        migrate_database()
    db = SessionLocal()
    try:
        ensure_default_admin(db)
        ensure_default_templates(db)
        backfill_script_assets(db)
        db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"ok": True, "service": settings.app_name, "redis": redis_ping()}
