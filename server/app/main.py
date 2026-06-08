"""FastAPI entrypoint for FreeCADAI SaaS."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from server.app.api.admin import auth_router as admin_auth_router
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
app.include_router(admin_auth_router)
app.include_router(admin_router)

STATIC_DIR = Path(__file__).resolve().parent / "static"


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


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse(
        (STATIC_DIR / "admin.html").read_text(encoding="utf-8"),
        media_type="text/html; charset=utf-8",
    )


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(
        (STATIC_DIR / "login.html").read_text(encoding="utf-8"),
        media_type="text/html; charset=utf-8",
    )


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
