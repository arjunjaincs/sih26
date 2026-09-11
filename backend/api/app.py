"""
PRAMAAN FastAPI application factory.

Usage
-----
    # Development server:
    uvicorn backend.api.app:app --reload

    # In tests:
    from backend.api.app import create_app
    app = create_app()
    client = TestClient(app)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.config import settings
from backend.api.errors import register_exception_handlers
from backend.api.routes.assessments import router as assessments_router
from backend.api.routes.capabilities import router as capabilities_router
from backend.api.routes.health import router as health_router
from backend.api.routes.uploads import router as uploads_router

_PRAMAAN_VERSION = "1.0.0"


def create_app() -> FastAPI:
    """
    Build and return the configured FastAPI application.

    Separate from the module-level `app` so tests can create
    isolated instances without side effects.
    """
    application = FastAPI(
        title="PRAMAAN",
        version=_PRAMAAN_VERSION,
        description=(
            "PRAMAAN — Evidence Before Trust. "
            "Offline assurance API for CV models and datasets."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ----------------------------------------------------------------
    # CORS — explicit allowlist, never wildcard in production
    # ----------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept"],
    )

    # ----------------------------------------------------------------
    # Exception handlers (structured JSON errors, no stack traces)
    # ----------------------------------------------------------------
    register_exception_handlers(application)

    # ----------------------------------------------------------------
    # Routes
    # ----------------------------------------------------------------
    application.include_router(health_router)
    application.include_router(capabilities_router)
    application.include_router(assessments_router)
    application.include_router(uploads_router)

    return application


# Module-level app instance for uvicorn
app = create_app()
