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
from backend.detectors.data.di02_label_integrity import DI02LabelIntegrityDetector
from backend.detectors.data.di03_trigger_anomaly import DI03TriggerAnomalyDetector
from backend.detectors.data.di04_ood_distribution import DI04DistributionOODDetector
from backend.detectors.data.di05_contributor_risk import DI05ContributorRiskDetector
from backend.detectors.model.mi01_fingerprint import MI01FingerprintDetector
from backend.detectors.model.mi02_parameter_stats import MI02ParameterStatsDetector
from backend.detectors.model.mi03_activation_stats import MI03ActivationStatsDetector
from backend.detectors.model.mi04_reference_comparison import MI04ReferenceComparisonDetector
from backend.detectors.model.mi05_trigger_anomaly import MI05TriggerAnomalyDetector
from backend.detectors.provenance.pi01_integrity import PI01ProvenanceIntegrityDetector

# All available detectors — ordered by typical execution priority.
ALL_DETECTORS: list[Detector] = [
    DI01DuplicateDetector(),
    DI02LabelIntegrityDetector(),
    DI03TriggerAnomalyDetector(),
    DI04DistributionOODDetector(),
    DI05ContributorRiskDetector(),
    MI01FingerprintDetector(),
    MI02ParameterStatsDetector(),
    MI03ActivationStatsDetector(),
    MI04ReferenceComparisonDetector(),
    MI05TriggerAnomalyDetector(),
    PI01ProvenanceIntegrityDetector(),
]

# Lookup by detector_id for quick access.
DETECTOR_BY_ID: dict[str, Detector] = {
    d.metadata.detector_id: d for d in ALL_DETECTORS
}
