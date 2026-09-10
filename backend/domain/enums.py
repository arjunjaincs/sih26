"""
PRAMAAN domain enumerations.

All enums live here so they can be imported by domain, infra, and API layers
without creating circular dependencies.
"""

from enum import Enum


class AssessmentState(str, Enum):
    """Lifecycle states of an Assessment."""

    CREATED = "created"
    INGESTING = "ingesting"
    ANALYZING = "analyzing"
    COMPLETE = "complete"
    FAILED = "failed"


class AssessmentType(str, Enum):
    """Whether this assessment uses live analysis or demo fixtures."""

    LIVE = "live"
    # DEMO is reserved for future use; not implemented in V1.


class AssetType(str, Enum):
    """Broad classification of an ingested asset."""

    DATASET = "dataset"
    MODEL = "model"
    IMAGE = "image"
    INFERENCE_BUNDLE = "inference_bundle"


class DatasetFormat(str, Enum):
    """Supported dataset annotation formats."""

    IMAGE_DIR = "image_dir"  # Plain directory of images, no annotations
    COCO_JSON = "coco_json"  # COCO format with a JSON annotation file


class ModelFramework(str, Enum):
    """Framework/serialization format of a model artifact."""

    PYTORCH = "pytorch"
    ONNX = "onnx"
    TORCHSCRIPT = "torchscript"
    UNKNOWN = "unknown"


class AccessLevel(str, Enum):
    """
    What level of internal access PRAMAAN has to a model.

    BLACK_BOX  — only input/output access (query model, observe predictions)
    GRAY_BOX   — limited internals (e.g., some activation hooks)
    WHITE_BOX  — full access (weights, gradients, architecture)
    """

    BLACK_BOX = "black_box"
    GRAY_BOX = "gray_box"
    WHITE_BOX = "white_box"


class RiskLevel(str, Enum):
    """
    Estimated threat level given observed evidence.

    NONE    — no evidence of threat after applicable analysis
    LOW     — weak evidence; unlikely to be meaningful
    MEDIUM  — notable evidence; warrants investigation
    HIGH    — strong evidence of a significant problem
    CRITICAL — compelling evidence of a severe threat
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def as_int(self) -> int:
        """Ordinal for comparison (higher = more severe)."""
        return {
            RiskLevel.NONE: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4,
        }[self]

    @classmethod
    def max(cls, a: "RiskLevel", b: "RiskLevel") -> "RiskLevel":
        """Return whichever risk level is higher."""
        return a if a.as_int() >= b.as_int() else b


class ConfidenceLevel(str, Enum):
    """
    Degree of trust in the risk estimate.

    LOW      — limited evidence, partial coverage, or poor-quality analysis
    MODERATE — reasonable evidence; some limitations apply
    HIGH     — strong, thorough evidence base

    IMPORTANT: LOW confidence does NOT mean the asset is safe.
    LOW confidence means we did not gather enough evidence to know.
    """

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class Severity(str, Enum):
    """Potential impact of a finding if the risk is real."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingCategory(str, Enum):
    """Broad category of a finding."""

    DATA_INTEGRITY = "data_integrity"
    MODEL_INTEGRITY = "model_integrity"
    INFERENCE_PROVENANCE = "inference_provenance"
    DISTRIBUTION_DRIFT = "distribution_drift"
    COVERAGE = "coverage"


class EvidenceType(str, Enum):
    """Nature of an evidence item."""

    MEASUREMENT = "measurement"
    COMPARISON = "comparison"
    ANOMALY = "anomaly"
    HASH_MISMATCH = "hash_mismatch"
    HASH_MATCH = "hash_match"
    STATISTICAL_TEST = "statistical_test"
    CLUSTER = "cluster"


class DetectorStatus(str, Enum):
    """Outcome of running a single detector."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"          # Not applicable for this asset/access level
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"  # Dependency missing or access insufficient


class AuditEventType(str, Enum):
    """Types of events recorded in the audit chain."""

    GENESIS = "genesis"
    ASSESSMENT_CREATED = "assessment_created"
    ASSET_REGISTERED = "asset_registered"
    INGESTION_STARTED = "ingestion_started"
    INGESTION_COMPLETE = "ingestion_complete"
    ANALYSIS_STARTED = "analysis_started"
    DETECTOR_STARTED = "detector_started"
    DETECTOR_COMPLETE = "detector_complete"
    FINDING_GENERATED = "finding_generated"
    ASSESSMENT_COMPLETE = "assessment_complete"
    ASSESSMENT_FAILED = "assessment_failed"
    PROVENANCE_CREATED = "provenance_created"
    PROVENANCE_VERIFIED = "provenance_verified"
    PROVENANCE_TAMPERED = "provenance_tampered"
    AUDIT_VERIFIED = "audit_verified"      # Chain integrity verification run
