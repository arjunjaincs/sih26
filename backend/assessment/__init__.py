"""
backend.assessment — PRAMAAN Phase 7: Assessment Orchestration

Public API
----------
    from backend.assessment import run_assessment, AssessmentService
    from backend.assessment.models import AssessmentRequest, AssessmentResult

The orchestrator is the single entry point for end-to-end assessments.
It coordinates the existing Phase 2-6 capabilities and returns a
structured AssessmentResult with risk, confidence, coverage, and audit status.
"""

from backend.assessment.models import (
    AssessmentRequest,
    AssessmentResult,
    CoverageGapRecord,
    DetectorRunRecord,
)
from backend.assessment.orchestrator import AssessmentService, run_assessment

__all__ = [
    "AssessmentRequest",
    "AssessmentResult",
    "AssessmentService",
    "CoverageGapRecord",
    "DetectorRunRecord",
    "run_assessment",
]
