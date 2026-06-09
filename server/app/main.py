"""FastAPI entrypoint for FreeCADAI SaaS."""

from fastapi import FastAPI

from server.app.api.admin import auth_router as admin_auth_router
from server.app.api.admin import billing_router
from server.app.api.admin import router as admin_router
from server.app.api.plugin import router as plugin_router
from server.app.core.config import settings
from server.app.core.redis import redis_ping
from server.app.db.migrations import migrate_database
from server.app.db.session import SessionLocal
from server.app.services.auth import ensure_default_admin

# Import models so create_all can discover them in the phase 4 prototype.
from server.app.models import entities  # noqa: F401


app = FastAPI(title=settings.app_name, version="0.4.0")
app.include_router(plugin_router)
app.include_router(billing_router)
app.include_router(admin_auth_router)
app.include_router(admin_router)


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
    }


@app.on_event("startup")
def startup():
    if settings.auto_migrate:
        migrate_database()
    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"ok": True, "service": settings.app_name, "redis": redis_ping()}
