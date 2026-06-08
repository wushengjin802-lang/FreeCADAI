"""FastAPI entrypoint for FreeCADAI SaaS."""

from fastapi import FastAPI

from server.app.api.plugin import router as plugin_router
from server.app.core.config import settings
from server.app.db.base import Base
from server.app.db.session import engine

# Import models so create_all can discover them in the phase 4 prototype.
from server.app.models import entities  # noqa: F401


app = FastAPI(title=settings.app_name, version="0.4.0")
app.include_router(plugin_router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"ok": True, "service": settings.app_name}
