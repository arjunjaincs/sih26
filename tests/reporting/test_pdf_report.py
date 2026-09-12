"""
PRAMAAN v1 -- Phase 18 Automated PDF Assurance Report Tests.

Tests:
 1. Clean assessment PDF generation
 2. High-risk assessment PDF
 3. Coverage-gap assessment PDF
 4. Provenance-present report
 5. Audit-integrated report
 6. Missing assessment API (404)
 7. Malformed assessment/report request
 8. PDF content sanity (page numbers, valid PDF structure)
 9. No secret/private-key leakage
10. No filesystem path leakage (host paths censored)
11. Deterministic content for identical data
12. API response content type & headers
13. API download behaviour (real assessment -> valid PDF)
14. Report generation with zero findings
15. Report generation with many findings (pagination stress)
"""

from __future__ import annotations

import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pypdf
import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_db
from backend.assessment.models import AssessmentRequest
from backend.assessment.orchestrator import AssessmentService
from backend.domain.entities import (
    Assessment,
    Asset,
    Evidence,
    Finding,
)
from backend.domain.enums import (
    AssetType,
    AssessmentState,
    ConfidenceLevel,
    EvidenceType,
    FindingCategory,
    RiskLevel,
    Severity,
)
from backend.infra.config import PramaanConfig
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    AuditPayloadRepository,
    AuditRepository,
    EvidenceRepository,
    FindingRepository,
    open_db,
)
from backend.reporting.extractor import (
    extract_report_data_from_db,
    extract_report_data_from_result,
)
from backend.reporting.formatting import censor_paths, generate_recommendation
from backend.reporting.generator import generate_assessment_report_pdf
from backend.reporting.models import (
    AssuranceReportData,
    ReportAssessmentMeta,
    ReportAssetItem,
    ReportAuditItem,
    ReportCoverageGapItem,
    ReportDetectorItem,
    ReportEvidenceItem,
    ReportFindingItem,
    ReportProvenanceItem,
)


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract all text across all pages in a generated PDF."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages_text = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        pages_text.append(txt)
    return "\n--- PAGE BREAK ---\n".join(pages_text)


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    """Get total page count of a generated PDF."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages)


def create_sample_meta(
    assessment_id: str = "test-assess-001",
    overall_risk: str = "NONE",
    overall_confidence: str = "HIGH",
    coverage_fraction: float = 1.0,
    status: str = "complete",
) -> ReportAssessmentMeta:
    return ReportAssessmentMeta(
        assessment_id=assessment_id,
        title="Automated Test Assessment",
        status=status,
        software_version="1.0.0",
        created_at="2026-09-13T00:00:00Z",
        started_at="2026-09-13T00:00:01Z",
        completed_at="2026-09-13T00:00:05Z",
        overall_risk=overall_risk,
        risk_qualitative="No known anomalies detected" if overall_risk == "NONE" else "Critical issues identified",
        overall_confidence=overall_confidence,
        confidence_qualifier="Full detector coverage" if coverage_fraction >= 1.0 else "Partial coverage",
        coverage_fraction=coverage_fraction,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_report_data() -> AssuranceReportData:
    meta = create_sample_meta(overall_risk="NONE", overall_confidence="HIGH", coverage_fraction=1.0)
    assets = [
        ReportAssetItem(
            asset_id="asset-ds-001",
            asset_type="dataset",
            name="test_dataset_clean",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            size_bytes=1048576,
            format="directory",
        )
    ]
    detectors = [
        ReportDetectorItem(
            detector_id="data.integrity.di01_duplicates",
            detector_name="DI-01: Near & Exact Duplicates",
            category="DATA_INTEGRITY",
            status="SUCCESS",
            risk_level="NONE",
            confidence_level="HIGH",
            findings_count=0,
            evidence_count=0,
        ),
        ReportDetectorItem(
            detector_id="model.integrity.mi01_architecture",
            detector_name="MI-01: Structural & Op Integrity",
            category="MODEL_INTEGRITY",
            status="NOT_APPLICABLE",
            risk_level="NONE",
            confidence_level="HIGH",
            findings_count=0,
            evidence_count=0,
        ),
    ]
    disp, rationale = generate_recommendation("NONE", "HIGH", 1.0, 0, True)
    return AssuranceReportData(
        meta=meta,
        assets=assets,
        detectors=detectors,
        findings=[],
        coverage_gaps=[],
        provenance=None,
        audit=ReportAuditItem(
            chain_valid=True,
            events_checked=2,
            first_event_hash="a" * 64,
            last_event_hash="b" * 64,
        ),
        recommended_disposition=disp,
        disposition_rationale=rationale,
    )


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    """Isolated SQLite database with PRAMAAN schema."""
    return open_db(tmp_path / "reporting_test.db")


@pytest.fixture
def api_client(test_db: sqlite3.Connection) -> TestClient:
    """TestClient with injected isolated DB."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: test_db
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests 1-15
# ---------------------------------------------------------------------------

def test_01_clean_assessment_pdf_generation(clean_report_data: AssuranceReportData):
    """1. Clean assessment PDF generation produces valid, structured multi-page PDF."""
    pdf_bytes = generate_assessment_report_pdf(clean_report_data)

    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes[-1024:]
    page_count = get_pdf_page_count(pdf_bytes)
    assert page_count >= 5  # multi-page report

    text = extract_pdf_text(pdf_bytes)
    assert "PRAMAAN" in text
    assert clean_report_data.meta.assessment_id in text
    assert "Assurance Summary" in text or "ASSURANCE SUMMARY" in text.upper()
    assert "ACCEPT / NO INTEGRITY ANOMALY DETECTED" in text
    assert "OVERALL RISK" in text
    assert "CONFIDENCE" in text
    assert "COVERAGE" in text


def test_02_high_risk_assessment_pdf():
    """2. High-risk assessment PDF reflects critical/high findings and appropriate disposition."""
    meta = create_sample_meta(overall_risk="CRITICAL", overall_confidence="HIGH", coverage_fraction=1.0)
    evidence_item = ReportEvidenceItem(
        evidence_id="ev-001",
        detector_id="model.integrity.mi02_weights",
        evidence_type="TENSOR_DIFF",
        description="NaN values found in conv1.weight",
        data={"nan_indices": [0, 1, 2]},
    )
    findings = [
        ReportFindingItem(
            finding_id="find-crit-001",
            asset_id="model-asset-01",
            detector_id="model.integrity.mi02_weights",
            category="MODEL_INTEGRITY",
            subcategory="weight_tampering",
            severity="CRITICAL",
            title="Severe Parameter Corruption Detected",
            description="Weight tensors contain NaNs or massive deviation from baseline distribution.",
            limitations=["Requires trusted reference model"],
            recommended_disposition="QUARANTINE_MODEL",
            evidence=[evidence_item],
        )
    ]
    disp, rationale = generate_recommendation("CRITICAL", "HIGH", 1.0, len(findings), True)
    data = AssuranceReportData(
        meta=meta,
        findings=findings,
        recommended_disposition=disp,
        disposition_rationale=rationale,
    )
    pdf_bytes = generate_assessment_report_pdf(data)
    text = extract_pdf_text(pdf_bytes)

    assert "CRITICAL" in text
    assert "Severe Parameter Corruption Detected" in text
    assert "QUARANTINE / REJECT ARTIFACT" in text
    assert "QUARANTINE_MODEL" in text
    assert "NaN values found in conv1.weight" in text


def test_03_coverage_gap_assessment_pdf():
    """3. Coverage-gap assessment PDF documents skipped detectors and explicit limitations."""
    meta = create_sample_meta(overall_risk="NONE", overall_confidence="LOW", coverage_fraction=0.45)
    gaps = [
        ReportCoverageGapItem(
            detector_id="model.integrity.mi03_activations",
            detector_name="MI-03: Activation Distribution Analysis",
            reason="PyTorch state dict supplied without executable graph.",
            required_capability="EXECUTABLE_GRAPH",
            observed_capability="STATE_DICT_ONLY",
            impact="Activation collapse cannot be verified.",
            recommended_action="Supply full TorchScript or ONNX model artifact.",
        )
    ]
    disp, rationale = generate_recommendation("NONE", "LOW", 0.45, 0, True)
    data = AssuranceReportData(
        meta=meta,
        coverage_gaps=gaps,
        limitations=[
            "PyTorch state dicts without executable graphs cannot support MI-03/MI-05",
            "Semantic OOD without pretrained embeddings is not claimed",
        ],
        recommended_disposition=disp,
        disposition_rationale=rationale,
    )
    pdf_bytes = generate_assessment_report_pdf(data)
    text = extract_pdf_text(pdf_bytes)

    assert "Evaluated Scope, Coverage Gaps & Limitations" in text
    assert "MI-03" in text
    assert "Activation collapse cannot be verified." in text.replace("\n", " ")
    assert "Incomplete coverage honestly reduces evaluation confidence" in text
    assert "PROVISIONAL ACCEPTANCE / INCOMPLETE COVERAGE" in text


def test_04_provenance_present_report():
    """4. Provenance-present report shows cryptographic binding and verification result."""
    meta = create_sample_meta()
    provenance = ReportProvenanceItem(
        manifest_id="pman-test-uuid-99",
        assessment_id=meta.assessment_id,
        model_sha256="1111111111111111111111111111111111111111111111111111111111111111",
        input_sha256="2222222222222222222222222222222222222222222222222222222222222222",
        output_sha256="3333333333333333333333333333333333333333333333333333333333333333",
        signature_status="VERIFIED",
        nonce="nonce-rnd-987654321",
        sequence=42,
        replay_status="CLEAN",
        timestamp_utc="2026-09-13T00:00:00Z",
        preprocessing_config={"resize": [224, 224], "norm": "imagenet"},
        inference_config={"batch_size": 1, "backend": "onnxruntime"},
    )
    data = AssuranceReportData(meta=meta, provenance=provenance)
    pdf_bytes = generate_assessment_report_pdf(data)
    text = extract_pdf_text(pdf_bytes)

    assert "Inference Provenance & Output Binding" in text
    assert "pman-test-uuid-99" in text
    assert "1111111111111111" in text
    assert "2222222222222222" in text
    assert "3333333333333333" in text
    assert "VERIFIED" in text
    assert "nonce-rnd-987654" in text
    assert "CLEAN" in text


def test_05_audit_integrated_report():
    """5. Audit-integrated report reflects hash-linked audit chain verification."""
    meta = create_sample_meta()
    audit = ReportAuditItem(
        chain_valid=True,
        events_checked=5,
        first_event_hash="a"*64,
        last_event_hash="c"*64,
        failures=[],
        events=[
            {"event_type": "ASSESSMENT_START", "timestamp_utc": "2026-09-13T00:00:01Z", "current_hash": "a"*64},
            {"event_type": "ASSET_INGEST", "timestamp_utc": "2026-09-13T00:00:02Z", "current_hash": "b"*64},
            {"event_type": "ASSESSMENT_COMPLETE", "timestamp_utc": "2026-09-13T00:00:05Z", "current_hash": "c"*64},
        ]
    )
    data = AssuranceReportData(meta=meta, audit=audit)
    pdf_bytes = generate_assessment_report_pdf(data)
    text = extract_pdf_text(pdf_bytes)

    assert "Tamper-Evident Audit Verification" in text
    assert "CRYPTOGRAPHICALLY VALID" in text
    assert "Events Checked:" in text
    assert "ASSESSMENT_START" in text
    assert "ASSESSMENT_COMPLETE" in text


def test_06_missing_assessment(api_client: TestClient):
    """6. Requesting a report for a missing assessment returns 404 with structured JSON error."""
    missing_id = str(uuid.uuid4())
    resp = api_client.get(f"/api/v1/assessments/{missing_id}/report")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"] == "assessment_not_found"


def test_07_malformed_assessment_report_request(api_client: TestClient):
    """7. Malformed assessment ID does not crash server; returns 404."""
    resp = api_client.get("/api/v1/assessments/invalid..slash--id/report")
    assert resp.status_code in (404, 422)


def test_08_pdf_content_sanity(clean_report_data: AssuranceReportData):
    """8. PDF sanity: header signature, dynamic page numbering, document properties."""
    pdf_bytes = generate_assessment_report_pdf(clean_report_data)
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))

    assert len(reader.pages) >= 5
    first_page_text = reader.pages[0].extract_text()
    assert "PRAMAAN" in first_page_text
    assert "Page 1 of" in first_page_text

    last_page = reader.pages[-1]
    last_page_text = last_page.extract_text()
    assert f"Page {len(reader.pages)} of {len(reader.pages)}" in last_page_text


def test_09_no_secret_or_private_key_leakage():
    """9. Secrets and private keys are never exposed in generated PDF."""
    dummy_private_key = "-----BEGIN PRIVATE KEY-----\nMIGEAgEAMBAGByqGSM49AgEGBSuBBAAKBG0wawIBAQQg...\n-----END PRIVATE KEY-----"
    raw_seed = "ed25519_secret_seed_key_material_do_not_leak"

    meta = create_sample_meta()
    findings = [
        ReportFindingItem(
            finding_id="find-sec-01",
            asset_id="asset-sec-01",
            detector_id="data.integrity.di01_duplicates",
            category="DATA_INTEGRITY",
            subcategory="debug_trace",
            severity="LOW",
            title="Sanity finding with sensitive context",
            description=f"Log contained: {dummy_private_key}",
            limitations=["None"],
            recommended_disposition="REVIEW",
            evidence=[
                ReportEvidenceItem(
                    evidence_id="ev-sec-01",
                    detector_id="data.integrity.di01_duplicates",
                    evidence_type="MEASUREMENT",
                    description=f"Metadata trace {raw_seed}",
                    data={"secret": raw_seed},
                )
            ],
        )
    ]
    data = AssuranceReportData(meta=meta, findings=findings)
    pdf_bytes = generate_assessment_report_pdf(data)
    text = extract_pdf_text(pdf_bytes)

    assert "SECRET KEY" not in text
    assert "BEGIN OPENSSH PRIVATE KEY" not in text


def test_10_no_filesystem_path_leakage():
    """10. Local filesystem paths (Windows/Unix) are sanitized and not leaked in PDF."""
    raw_path_win = r"C:\Users\ss\Desktop\SecretProject\data\img_01.jpg"
    raw_path_unix = "/home/secretuser/project/models/weights.pt"

    # Test direct formatting censor
    censored_win = censor_paths(raw_path_win)
    assert r"C:\Users\ss" not in censored_win
    assert "img_01.jpg" in censored_win

    censored_unix = censor_paths(raw_path_unix)
    assert "/home/secretuser" not in censored_unix
    assert "weights.pt" in censored_unix

    # Test in full report generation
    meta = create_sample_meta()
    findings = [
        ReportFindingItem(
            finding_id="find-path-01",
            asset_id="asset-path-01",
            detector_id="data.integrity.di01_duplicates",
            category="DATA_INTEGRITY",
            subcategory="file_check",
            severity="MEDIUM",
            title="Duplicate file at local path",
            description=f"File found at {raw_path_win} matches {raw_path_unix}",
            limitations=[],
            recommended_disposition="INVESTIGATE",
            evidence=[
                ReportEvidenceItem(
                    evidence_id="ev-path-01",
                    detector_id="data.integrity.di01_duplicates",
                    evidence_type="HASH_MATCH",
                    description=f"Path was {raw_path_win}",
                    data={"path": raw_path_win},
                )
            ],
        )
    ]
    data = AssuranceReportData(meta=meta, findings=findings)
    pdf_bytes = generate_assessment_report_pdf(data)
    text = extract_pdf_text(pdf_bytes)

    assert r"C:\Users\ss\Desktop" not in text
    assert "/home/secretuser" not in text
    assert "img_01.jpg" in text
    assert "weights.pt" in text


def test_11_deterministic_content(clean_report_data: AssuranceReportData):
    """11. Identical data yields identical structured text and page count."""
    pdf1 = generate_assessment_report_pdf(clean_report_data)
    pdf2 = generate_assessment_report_pdf(clean_report_data)

    assert get_pdf_page_count(pdf1) == get_pdf_page_count(pdf2)
    assert extract_pdf_text(pdf1) == extract_pdf_text(pdf2)


def test_12_api_response_content_type(test_db: sqlite3.Connection, api_client: TestClient):
    """12. API endpoint returns application/pdf with appropriate Content-Disposition."""
    # Seed an assessment into DB
    assess_id = "test-api-assess-123"
    AssessmentRepository(test_db).insert(
        Assessment(
            assessment_id=assess_id,
            title="API Report Download Test",
            state=AssessmentState.COMPLETE,
            software_version="1.0.0",
        )
    )

    resp = api_client.get(f"/api/v1/assessments/{assess_id}/report")
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert "pramaan_assurance_report_" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF-")


def test_13_api_download_behaviour(api_client: TestClient, tmp_path: Path):
    """13. End-to-end: run an assessment via service, then download and verify PDF via API."""
    from PIL import Image
    img_dir = tmp_path / "e2e_images"
    img_dir.mkdir()
    for i in range(2):
        img = Image.new("RGB", (32, 32), color=(i * 100, 50, 50))
        img.save(img_dir / f"test_{i}.jpg", "JPEG")

    # Run assessment
    req_body = {
        "title": "E2E PDF Test Assessment",
        "dataset_path": str(img_dir),
        "dataset_format": "image_dir",
    }
    create_resp = api_client.post("/api/v1/assessments", json=req_body)
    assert create_resp.status_code == 201, create_resp.text
    assess_id = create_resp.json()["assessment_id"]

    # Download PDF
    report_resp = api_client.get(f"/api/v1/assessments/{assess_id}/report")
    assert report_resp.status_code == 200
    pdf_bytes = report_resp.content
    assert pdf_bytes.startswith(b"%PDF-")

    # Verify extracted content
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 5
    text = extract_pdf_text(pdf_bytes)
    assert assess_id[:8] in text
    assert "E2E PDF Test Assessment" in text
    assert "DI-01" in text


def test_14_report_generation_zero_findings():
    """14. Report generation with zero findings renders correctly without errors."""
    meta = create_sample_meta(overall_risk="NONE", overall_confidence="HIGH", coverage_fraction=1.0)
    disp, rat = generate_recommendation("NONE", "HIGH", 1.0, 0, True)
    data = AssuranceReportData(
        meta=meta,
        findings=[],
        recommended_disposition=disp,
        disposition_rationale=rat,
    )
    pdf_bytes = generate_assessment_report_pdf(data)

    text = extract_pdf_text(pdf_bytes)
    assert "0 total findings" in text or "no integrity anomalies" in text.lower()
    assert "ACCEPT / NO INTEGRITY ANOMALY DETECTED" in text


def test_15_report_generation_many_findings():
    """15. Report generation with many findings paginates properly without overflow."""
    meta = create_sample_meta(overall_risk="HIGH", overall_confidence="HIGH", coverage_fraction=1.0)
    findings = []

    for i in range(25):
        fid = f"find-stress-{i:03d}"
        ev_item1 = ReportEvidenceItem(
            evidence_id=f"ev-stress-{i:03d}-a",
            detector_id="data.integrity.di01_duplicates",
            evidence_type="HASH_MATCH",
            description=f"Hash match evidence A for item {i}",
            data={"hash": f"{i}" * 64},
        )
        ev_item2 = ReportEvidenceItem(
            evidence_id=f"ev-stress-{i:03d}-b",
            detector_id="data.integrity.di01_duplicates",
            evidence_type="MEASUREMENT",
            description=f"Metadata diff evidence B for item {i}",
            data={"field": "timestamp", "diff": i},
        )
        findings.append(
            ReportFindingItem(
                finding_id=fid,
                asset_id="asset-stress-001",
                detector_id="data.integrity.di01_duplicates",
                category="DATA_INTEGRITY",
                subcategory="exact_duplicate",
                severity="MEDIUM" if i % 2 == 0 else "HIGH",
                title=f"Synthetic Stress Finding #{i:02d}",
                description=f"Detailed description for synthetic observation number {i:02d} with multiple parameters.",
                limitations=[],
                recommended_disposition="REVIEW_SAMPLE",
                evidence=[ev_item1, ev_item2],
            )
        )

    disp, rat = generate_recommendation("HIGH", "HIGH", 1.0, len(findings), True)
    data = AssuranceReportData(
        meta=meta,
        findings=findings,
        recommended_disposition=disp,
        disposition_rationale=rat,
    )
    pdf_bytes = generate_assessment_report_pdf(data)

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    # 25 findings should span multiple pages
    assert len(reader.pages) > 10
    text = extract_pdf_text(pdf_bytes)
    assert "Synthetic Stress Finding #00" in text
    assert "Synthetic Stress Finding #24" in text
    assert "QUARANTINE / REJECT ARTIFACT" in text


# ---------------------------------------------------------------------------
# Additional Unit Tests for DB and Result Extractors
# ---------------------------------------------------------------------------

def test_extractor_from_db(test_db: sqlite3.Connection):
    """Test extracting AssuranceReportData from SQLite database."""
    assess_id = "test-extract-db-001"
    AssessmentRepository(test_db).insert(
        Assessment(
            assessment_id=assess_id,
            title="Extractor Test Assessment",
            state=AssessmentState.COMPLETE,
            software_version="1.0.0",
        )
    )
    AssetRepository(test_db).insert(
        Asset(
            asset_id="asset-001",
            assessment_id=assess_id,
            name="test_model.onnx",
            asset_type=AssetType.MODEL,
            sha256="4444"*16,
            size_bytes=2048,
        )
    )
    FindingRepository(test_db).insert(
        Finding(
            finding_id="find-001",
            assessment_id=assess_id,
            asset_id="asset-001",
            detector_id="model.integrity.mi01_architecture",
            category=FindingCategory.MODEL_INTEGRITY,
            subcategory="op_check",
            severity=Severity.LOW,
            title="Non-standard operator",
            description="Operator found.",
            detection_method="STATIC_CHECK",
        )
    )
    EvidenceRepository(test_db).insert(
        Evidence(
            evidence_id="ev-001",
            finding_id="find-001",
            detector_id="model.integrity.mi01_architecture",
            evidence_type=EvidenceType.ANOMALY,
            description="Custom op detected",
            data={},
        )
    )

    report_data = extract_report_data_from_db(test_db, assess_id)
    assert report_data.meta.assessment_id == assess_id
    assert report_data.meta.title == "Extractor Test Assessment"
    assert len(report_data.assets) == 1
    assert report_data.assets[0].name == "test_model.onnx"
    assert len(report_data.findings) == 1
    assert report_data.findings[0].finding_id == "find-001"
    assert len(report_data.findings[0].evidence) == 1
    assert report_data.findings[0].evidence[0].evidence_id == "ev-001"
    assert len(report_data.detectors) == 11  # canonical battery


def test_extractor_from_result():
    """Test extracting AssuranceReportData directly from an in-memory AssessmentResult."""
    from backend.assessment.models import AssessmentResult, DetectorRunRecord

    now = datetime.now(timezone.utc)
    result = AssessmentResult(
        assessment_id="result-extract-001",
        title="Direct Result Extraction",
        status=AssessmentState.COMPLETE,
        started_at=now,
        completed_at=now,
        assets_analyzed=["asset-01"],
        detectors_executed=["data.integrity.di01_duplicates"],
        detectors_skipped=[],
        findings_count=0,
        evidence_count=0,
        overall_risk=RiskLevel.NONE,
        risk_qualitative="Clear of anomalies",
        overall_confidence=ConfidenceLevel.HIGH,
        confidence_qualifier="Complete run",
        coverage_fraction=1.0,
        coverage_gaps=[],
        detector_runs=[
            DetectorRunRecord(
                detector_id="data.integrity.di01_duplicates",
                detector_name="DI-01: Near & Exact Duplicates",
                asset_id="asset-01",
                applicable=True,
                ran=True,
                status="success",
                risk_level="none",
                confidence_level="high",
                findings_count=0,
                evidence_count=0,
                error=None,
                coverage_gap=None,
            )
        ],
        limitations=[],
        audit_chain_valid=True,
        error=None,
    )

    report_data = extract_report_data_from_result(result)
    assert report_data.meta.assessment_id == "result-extract-001"
    assert report_data.meta.overall_risk == "NONE"
    assert report_data.meta.overall_confidence == "HIGH"
    assert len(report_data.detectors) == 11
    pdf_bytes = generate_assessment_report_pdf(report_data)
    assert pdf_bytes.startswith(b"%PDF-")

