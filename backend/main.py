from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings

logger = logging.getLogger(__name__)


def _register_routers(app: FastAPI) -> None:
    """Attach all domain routers under the /api prefix.

    Each router module is imported individually so that a missing module
    produces a clear ImportError rather than a silent skip.
    """
    from backend.routers.connections import router as connections_router
    from backend.routers.customers import router as customers_router
    from backend.routers.dashboard import router as dashboard_router
    from backend.routers.reports import router as reports_router
    from backend.routers.scans import router as scans_router

    app.include_router(customers_router, prefix="/api")
    app.include_router(connections_router, prefix="/api")
    app.include_router(scans_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")
    app.include_router(dashboard_router, prefix="/api")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Application lifespan handler: set up resources on startup."""
    reports_dir = Path(settings.REPORTS_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Reports directory ensured at %s", reports_dir.resolve())
    yield
    # Teardown logic (if needed) goes here.


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    app = FastAPI(
        title="DevOps Discovery API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_routers(app)

    @app.get("/api/health", tags=["health"])
    async def health_check() -> dict[str, Any]:
        """Liveness probe endpoint."""
        return {"status": "ok"}

    return app


app = create_app()
