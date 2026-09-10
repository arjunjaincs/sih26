"""
GET /api/v1/capabilities

Exposes what PRAMAAN can actually analyse in the current offline environment.
All information is derived from the live detector registry — no hardcoded names.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.schemas import CapabilitiesResponse, DetectorCapabilitySchema
from backend.detectors.base import DetectorContext
from backend.detectors.registry import ALL_DETECTORS
from backend.domain.enums import DatasetFormat

router = APIRouter(prefix="/api/v1", tags=["capabilities"])

_PRAMAAN_VERSION = "1.0.0"

# Supported model file extensions (used by MI-01)
_SUPPORTED_MODEL_FORMATS = [".onnx", ".pt", ".pth", ".ts"]


def _check_available(detector) -> bool:
    """
    Run a minimal can_run() pre-flight check with a stub context.

    Returns True if the detector reports it can run.
    This surfaces dependency availability (e.g. onnx not installed).
    """
    from backend.infra.db import open_db
    import tempfile, os
    # Use an in-memory SQLite for the availability check — no real assets.
    ctx = DetectorContext(
        assessment_id="__capability_check__",
        asset_id="__none__",
        conn=None,
    )
    try:
        result = detector.can_run(ctx)
        return result.ok
    except Exception:
        return False


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    summary="List available PRAMAAN analysis capabilities",
)
def capabilities() -> CapabilitiesResponse:
    """
    Returns the detectors actually registered in the current installation.

    - detector IDs, versions, descriptions
    - which asset types each detector can analyse
    - whether each detector's runtime dependencies are satisfied
    - supported dataset and model formats

    The UI uses this endpoint to decide which analysis options to offer.
    """
    detector_schemas = [
        DetectorCapabilitySchema(
            detector_id=d.metadata.detector_id,
            version=d.metadata.version,
            name=d.metadata.name,
            description=d.metadata.description,
            applicable_asset_types=sorted(d.metadata.applicable_asset_types),
            available=_check_available(d),
        )
        for d in ALL_DETECTORS
    ]

    return CapabilitiesResponse(
        detectors=detector_schemas,
        supported_dataset_formats=[fmt.value for fmt in DatasetFormat],
        supported_model_formats=_SUPPORTED_MODEL_FORMATS,
        pramaan_version=_PRAMAAN_VERSION,
    )
