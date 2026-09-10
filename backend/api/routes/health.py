"""
GET /health

Returns a small deterministic response confirming the local PRAMAAN
service is reachable. Does NOT run any assessment logic.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.config import settings
from backend.api.schemas import HealthResponse

router = APIRouter(tags=["health"])

_PRAMAAN_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health_check() -> HealthResponse:
    """
    Returns 200 with a minimal status payload when the service is available.

    Does not hit the database or run any analysis. Safe to call from
    load-balancers or monitoring probes.
    """
    return HealthResponse(
        status="ok",
        version=_PRAMAAN_VERSION,
        db_path=str(settings.db_path),
    )
