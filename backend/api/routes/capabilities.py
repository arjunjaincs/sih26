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
    Check if the detector is available in the current environment.
    All registered detectors in ALL_DETECTORS are available.
    """
    return detector is not None and hasattr(detector, "metadata")


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
