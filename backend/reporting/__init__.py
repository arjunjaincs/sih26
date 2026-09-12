"""
PRAMAAN v1 Assurance Report Engine.

Generates offline, human-readable, tamper-evident PDF assurance reports
from assessment results, findings, evidence, audit chains, and provenance manifests.
"""

from backend.reporting.extractor import (
    extract_report_data_from_db,
    extract_report_data_from_result,
)
from backend.reporting.generator import generate_assessment_report_pdf
from backend.reporting.models import AssuranceReportData

__all__ = [
    "AssuranceReportData",
    "extract_report_data_from_db",
    "extract_report_data_from_result",
    "generate_assessment_report_pdf",
]
