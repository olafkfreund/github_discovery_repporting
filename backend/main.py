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
    from backend.routers.agent_instructions import router as agent_instructions_router
    from backend.routers.agent_profiles import router as agent_profiles_router
    from backend.routers.connections import router as connections_router
    from backend.routers.customers import router as customers_router
    from backend.routers.dashboard import router as dashboard_router
    from backend.routers.llm_connections import router as llm_connections_router
    from backend.routers.reports import router as reports_router
    from backend.routers.scan_profiles import router as scan_profiles_router
    from backend.routers.scans import router as scans_router

    app.include_router(agent_profiles_router)
    app.include_router(customers_router, prefix="/api")
    app.include_router(connections_router, prefix="/api")
    app.include_router(scans_router, prefix="/api")
    app.include_router(scan_profiles_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(llm_connections_router)
    # Register after the customers router; FastAPI matches /{customer_id}/agent-instructions
    # without shadowing the /customers/ prefix routes since suffixes differ.
    app.include_router(agent_instructions_router)


def _check_weasyprint() -> None:
    """Verify that WeasyPrint's native dependencies are available.

    Called at startup so missing libraries surface immediately in the logs
    rather than silently failing inside a background report-generation task.
    """
    try:
        import weasyprint  # noqa: F401

        logger.info("WeasyPrint available — PDF generation ready.")
    except OSError as exc:
        logger.error(
            "WeasyPrint native libraries NOT available — PDF generation "
            "will fail. Start the server inside 'nix develop' to set "
            "LD_LIBRARY_PATH. Error: %s",
            exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Application lifespan handler: set up resources on startup."""
    reports_dir = Path(settings.REPORTS_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Reports directory ensured at %s", reports_dir.resolve())
    _check_weasyprint()
    yield
    # Teardown logic (if needed) goes here.


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    app = FastAPI(
        title="DevOps Discovery API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS: restrict allowed origins to an explicit allowlist.
    # OWASP A05:2021 — wildcard origins expose the API to cross-origin
    # requests from any domain.  CORS_ORIGINS is a comma-separated env var.
    allowed_origins = [
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
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
