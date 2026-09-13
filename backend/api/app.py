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

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.api.config import settings
from backend.api.errors import register_exception_handlers
from backend.api.routes.ai import router as ai_router
from backend.api.routes.assessments import router as assessments_router
from backend.api.routes.capabilities import router as capabilities_router
from backend.api.routes.demos import router as demos_router
from backend.api.routes.health import router as health_router
from backend.api.routes.search import router as search_router
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
    application.include_router(demos_router)
    application.include_router(uploads_router)
    application.include_router(ai_router)
    application.include_router(search_router)

    # ----------------------------------------------------------------
    # Static SPA Serving (Production / Desktop Release Mode)
    # ----------------------------------------------------------------
    frontend_dist_env = os.environ.get("PRAMAAN_FRONTEND_DIST", "")
    frontend_dist_dir = Path(frontend_dist_env).resolve() if frontend_dist_env else None
    if frontend_dist_dir is None or not frontend_dist_dir.is_dir():
        candidate = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
        if candidate.is_dir():
            frontend_dist_dir = candidate

    if frontend_dist_dir and frontend_dist_dir.is_dir():
        from fastapi.staticfiles import StaticFiles
        from starlette.responses import FileResponse

        assets_dir = frontend_dist_dir / "assets"
        if assets_dir.is_dir():
            application.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        fonts_dir = frontend_dist_dir / "fonts"
        if fonts_dir.is_dir():
            application.mount("/fonts", StaticFiles(directory=str(fonts_dir)), name="fonts")

        @application.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
                raise HTTPException(status_code=404, detail="Not Found")
            target = frontend_dist_dir / full_path
            if full_path and target.is_file():
                return FileResponse(target)
            return FileResponse(frontend_dist_dir / "index.html")

    return application


# Module-level app instance for uvicorn
app = create_app()
