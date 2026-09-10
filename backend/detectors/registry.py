"""
PRAMAAN detector registry.

Explicit list of all available detectors.
Per ADR-004: no dynamic loading, no entry points — just imports.

To add a new detector:
  1. Create the class in backend/detectors/<domain>/<name>.py
  2. Add an import and instance here.
"""

from __future__ import annotations

from backend.detectors.base import Detector
from backend.detectors.data.di01_duplicates import DI01DuplicateDetector

# All available detectors — ordered by typical execution priority.
ALL_DETECTORS: list[Detector] = [
    DI01DuplicateDetector(),
]

# Lookup by detector_id for quick access.
DETECTOR_BY_ID: dict[str, Detector] = {
    d.metadata.detector_id: d for d in ALL_DETECTORS
}
