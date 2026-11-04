from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    dashboard, devices, health, notifications, owner, projects, recordings, renders, research, runs, scripts, system,
    analytics, ops, publishing, thumbnails, youtube,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import OriginCheckMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title="HELL UPLOADS API", version="0.1.0",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None, openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(OriginCheckMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"],
    )
    for r in (health.router, owner.router, projects.router, research.router, runs.router, devices.router, recordings.router, scripts.router, renders.router, thumbnails.router, youtube.router, publishing.router, analytics.router, ops.router, notifications.router, dashboard.router, system.router):
        app.include_router(r)
    return app


app = create_app()
