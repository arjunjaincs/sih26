"""
Tests for Machine-Readable Structured JSON Assessment Export.

Covers:
- GET /api/v1/assessments/{assessment_id}/export/json
- Attachment header and Content-Type verification
- Complete assessment export with findings, evidence, battery, and assets
- Clean assessment export (zero findings, empty gaps)
- Missing/invalid assessment (404)
- Path censorship and secret scrubbing (no absolute paths or API keys)
- Provenance and audit verification status inclusion
- Elimination of raw binary artifacts
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_db
from backend.audit.hashing import compute_event_hash, compute_payload_digest
from backend.domain.entities import (
    Assessment,
    Asset,
    AuditEvent,
    Dataset,
    DetectorResult,
    Evidence,
    Finding,
    ModelArtifact,
    ProvenanceManifest,
    Sample,
)
from backend.domain.enums import (
    AccessLevel,
    AssessmentState,
    AssetType,
    AuditEventType,
    DatasetFormat,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    ModelFramework,
    Severity,
)
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    AuditPayloadRepository,
    AuditRepository,
    DatasetRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    ModelArtifactRepository,
    ProvenanceRepository,
    SampleRepository,
)


@pytest.fixture
def client(db: sqlite3.Connection) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def _seed_full_assessment(db: sqlite3.Connection, asmt_id: str = "asmt-export-001") -> str:
    """Seed an assessment with model, dataset, findings, evidence, provenance, and audit."""
    now = datetime.now(timezone.utc)
    conn = db

    # 1. Assessment
    AssessmentRepository(conn).insert(
        Assessment(
            assessment_id=asmt_id,
            title="E2E Machine-Readable Export Validation",
            state=AssessmentState.COMPLETE,
            software_version="1.0.0",
            created_at=now,
            started_at=now,
            completed_at=now,
        )
    )

    # 2. Assets
    asset_repo = AssetRepository(conn)
    model_asset = Asset(
        asset_id="ast-model-01",
        assessment_id=asmt_id,
        asset_type=AssetType.MODEL,
        name="resnet50_quantized.onnx",
        sha256="aa" * 32,
        size_bytes=24500000,
        registered_at=now,
    )
    dataset_asset = Asset(
        asset_id="ast-ds-01",
        assessment_id=asmt_id,
        asset_type=AssetType.DATASET,
        name="training_imagery_v1",
        sha256="bb" * 32,
        size_bytes=150000000,
        registered_at=now,
    )
    asset_repo.insert(model_asset)
    asset_repo.insert(dataset_asset)

    ModelArtifactRepository(conn).insert(
        ModelArtifact(
            model_id=model_asset.asset_id,
            assessment_id=asmt_id,
            framework=ModelFramework.ONNX,
            access_level=AccessLevel.WHITE_BOX,
            source_path="models/resnet50_quantized.onnx",
            declared_sha256=model_asset.sha256,
        )
    )
    DatasetRepository(conn).insert(
        Dataset(
            dataset_id=dataset_asset.asset_id,
            assessment_id=asmt_id,
            format=DatasetFormat.IMAGE_DIR,
            source_path="datasets/training_imagery",
            sample_count=150,
            class_names=["vehicle", "infrastructure"],
        )
    )

    # 3. Detector results
    det_repo = DetectorResultRepository(conn)
    det_repo.insert(
        DetectorResult(
            result_id="res-01",
            assessment_id=asmt_id,
            asset_id=dataset_asset.asset_id,
            detector_id="data.integrity.di01_duplicates",
            detector_version="1.0.0",
            status=DetectorStatus.SUCCESS,
            findings_count=1,
            evidence_count=1,
            created_at=now,
        )
    )
    det_repo.insert(
        DetectorResult(
            result_id="res-02",
            assessment_id=asmt_id,
            asset_id=model_asset.asset_id,
            detector_id="model.integrity.mi01_fingerprint",
            detector_version="1.0.0",
            status=DetectorStatus.SUCCESS,
            findings_count=1,
            evidence_count=1,
            created_at=now,
        )
    )

    # 4. Findings & Evidence
    finding_repo = FindingRepository(conn)
    evidence_repo = EvidenceRepository(conn)

    f1 = Finding(
        finding_id="fnd-001",
        assessment_id=asmt_id,
        asset_id=dataset_asset.asset_id,
        category=FindingCategory.DATA_INTEGRITY,
        subcategory="perceptual_duplicates",
        severity=Severity.HIGH,
        title="Exact and Near-Duplicate Training Pairs Detected",
        description="Hash collision cluster of 4 images identified in training partition.",
        detection_method="Perceptual Hashing",
        detector_id="data.integrity.di01_duplicates",
        limitations=["Hamming distance cutoff = 10"],
        recommended_disposition="Deduplicate training split prior to fine-tuning.",
        created_at=now,
    )
    finding_repo.insert(f1)

    ev1 = Evidence(
        evidence_id="ev-001",
        finding_id=f1.finding_id,
        detector_id=f1.detector_id,
        evidence_type=EvidenceType.CLUSTER,
        description="Duplicate cluster 1 telemetry",
        data={"cluster_id": 1, "sample_count": 4, "hamming_distance": 2},
    )
    evidence_repo.insert(ev1)

    # 5. Provenance Manifest
    prov_repo = ProvenanceRepository(conn)
    pm = ProvenanceManifest(
        manifest_id="man-001",
        assessment_id=asmt_id,
        input_sha256="11" * 32,
        model_sha256=model_asset.sha256,
        output_sha256="22" * 32,
        preprocessing_config={"resize": [224, 224], "norm_mean": [0.485, 0.456, 0.406]},
        inference_config={"batch_size": 1, "device": "cuda:0"},
        timestamp_utc=now.isoformat(),
        nonce="nonce_test_xyz123",
        sequence=1,
        digest="33" * 32,
        signature="ed25519_sig_valid_hex",
    )
    prov_repo.insert(pm)

    # 6. Audit Chain & Payloads
    audit_repo = AuditRepository(conn)
    payload_repo = AuditPayloadRepository(conn)

    prev_hash = "0" * 64
    for i, etype in enumerate(
        [
            AuditEventType.ASSESSMENT_CREATED,
            AuditEventType.ASSET_REGISTERED,
            AuditEventType.ANALYSIS_STARTED,
            AuditEventType.ASSESSMENT_COMPLETE,
        ]
    ):
        event_id = f"evt-export-{i:03d}"
        iso_ts = f"2026-09-13T00:0{i}:00Z"
        payload = {"step": i}
        if etype == AuditEventType.ASSESSMENT_COMPLETE:
            payload.update({
                "overall_risk": "HIGH",
                "overall_confidence": "HIGH",
                "coverage_fraction": 0.91,
            })
        payload_digest = compute_payload_digest(payload)
        evt = AuditEvent(
            event_id=event_id,
            assessment_id=asmt_id,
            event_type=etype,
            actor="system",
            timestamp_utc=iso_ts,
            payload_digest=payload_digest,
            previous_hash=prev_hash,
            current_hash="",
        )
        evt.current_hash = compute_event_hash(evt)
        audit_repo.append(evt)
        payload_repo.insert(event_id, payload)
        prev_hash = evt.current_hash

    return asmt_id


class TestAssessmentJsonExport:
    """Test machine-readable structured JSON export endpoint."""

    def test_export_complete_assessment_json_structure(self, client: TestClient, db: sqlite3.Connection):
        """Exporting completed assessment returns valid JSON with all required assurance sections."""
        asmt_id = _seed_full_assessment(db, "asmt-full-01")

        res = client.get(f"/api/v1/assessments/{asmt_id}/export/json")
        assert res.status_code == 200
        assert "application/json" in res.headers["content-type"]
        assert "attachment" in res.headers["content-disposition"]
        assert "pramaan_assurance_export_" in res.headers["content-disposition"]

        data = res.json()

        # Top-level contract
        assert data["export_format"] == "pramaan_assurance_export"
        assert data["export_schema_version"] == "1.0.0"
        assert data["pramaan_version"] == "1.0.0"
        assert "T" in data["exported_at_utc"]

        # Assessment metadata
        asmt = data["assessment"]
        assert asmt["assessment_id"] == asmt_id
        assert asmt["title"] == "E2E Machine-Readable Export Validation"
        assert asmt["status"] == "complete"
        assert asmt["overall_risk"] == "HIGH"
        assert asmt["overall_confidence"] == "HIGH"
        assert asmt["coverage_fraction"] == 0.91

        # Disposition
        assert "recommended_disposition" in data["disposition"]
        assert "rationale" in data["disposition"]

        # Assets
        assert len(data["assets"]) == 2
        asset_names = [a["name"] for a in data["assets"]]
        assert "resnet50_quantized.onnx" in asset_names
        assert "training_imagery_v1" in asset_names

        # Battery
        assert data["battery"]["total_detectors"] == 11
        assert data["battery"]["executed_count"] >= 2
        assert len(data["battery"]["detectors"]) == 11

        # Findings & Evidence references
        assert len(data["findings"]) >= 1
        finding = data["findings"][0]
        assert finding["finding_id"] == "fnd-001"
        assert finding["severity"] == "high"
        assert len(finding["evidence"]) == 1
        ev = finding["evidence"][0]
        assert ev["evidence_id"] == "ev-001"
        assert ev["data"]["cluster_id"] == 1

        # Provenance
        assert data["provenance"]["has_provenance"] is True
        assert data["provenance"]["manifest_id"] == "man-001"
        assert data["provenance"]["signature_status"] == "VERIFIED"
        assert data["provenance"]["replay_status"] == "CLEAN"

        # Audit
        assert data["audit"]["chain_valid"] is True
        assert data["audit"]["events_checked"] == 4
        assert len(data["audit"]["events"]) == 4

    def test_export_clean_assessment(self, client: TestClient, db: sqlite3.Connection):
        """Clean assessment with zero findings exports successfully with NONE risk."""
        now = datetime.now(timezone.utc)
        asmt_id = "asmt-clean-01"
        AssessmentRepository(db).insert(
            Assessment(
                assessment_id=asmt_id,
                title="Clean Assessment Run",
                state=AssessmentState.COMPLETE,
                software_version="1.0.0",
                created_at=now,
            )
        )

        res = client.get(f"/api/v1/assessments/{asmt_id}/export/json")
        assert res.status_code == 200
        data = res.json()
        assert data["assessment"]["overall_risk"] == "NONE"
        assert len(data["findings"]) == 0
        assert len(data["coverage_gaps"]) == 0

    def test_export_nonexistent_assessment_returns_404(self, client: TestClient):
        """Exporting non-existent assessment returns standard 404."""
        res = client.get("/api/v1/assessments/asmt-missing-999/export/json")
        body = res.json()
        assert body["error"] == "assessment_not_found"

    def test_export_path_censorship_and_secret_scrubbing(self, client: TestClient, db: sqlite3.Connection):
        """Absolute server paths and API keys are censored/scrubbed from exported JSON."""
        now = datetime.now(timezone.utc)
        asmt_id = "asmt-sec-01"

        AssessmentRepository(db).insert(
            Assessment(
                assessment_id=asmt_id,
                title="Evaluation of C:\\Users\\Admin\\Confidential\\ProjectAlpha",
                state=AssessmentState.COMPLETE,
                created_at=now,
            )
        )

        asset_repo = AssetRepository(db)
        asset_repo.insert(
            Asset(
                asset_id="ast-sec-01",
                assessment_id=asmt_id,
                asset_type=AssetType.DATASET,
                name="/home/developer/secrets/dataset.zip",
                sha256="cc" * 32,
                size_bytes=1000,
                registered_at=now,
            )
        )

        # Finding and evidence with embedded secret key and absolute path
        finding_repo = FindingRepository(db)
        evidence_repo = EvidenceRepository(db)

        f = Finding(
            finding_id="fnd-sec-01",
            assessment_id=asmt_id,
            asset_id="ast-sec-01",
            category=FindingCategory.DATA_INTEGRITY,
            subcategory="test",
            severity=Severity.MEDIUM,
            title="Finding in /var/log/secure.log",
            description="Loaded model from C:\\Sensitive\\Weights\\model.pt with key sk-live-99999999999999999999",
            detection_method="Scanner",
            detector_id="DI-01",
            limitations=["Tested on /tmp/scratch_dir"],
            created_at=now,
        )
        finding_repo.insert(f)

        ev = Evidence(
            evidence_id="ev-sec-01",
            finding_id=f.finding_id,
            detector_id=f.detector_id,
            evidence_type=EvidenceType.MEASUREMENT,
            description="Evidence in C:\\Internal\\trace.json",
            data={
                "server_path": "C:\\Windows\\System32\\cmd.exe",
                "api_key": "secret_api_key_value_12345",
                "auth_token": "Bearer sk-token12345678901234567890",
                "valid_metric": 42.5,
            },
        )
        evidence_repo.insert(ev)

        res = client.get(f"/api/v1/assessments/{asmt_id}/export/json")
        assert res.status_code == 200

        raw_json_str = res.text

        # Path checks
        assert "C:\\Users\\Admin" not in raw_json_str
        assert "C:\\Sensitive" not in raw_json_str
        assert "C:\\Internal" not in raw_json_str
        assert "C:\\Windows" not in raw_json_str
        assert "/home/developer/secrets" not in raw_json_str
        assert "/var/log" not in raw_json_str
        assert "/tmp/scratch_dir" not in raw_json_str

        # Secret checks
        assert "secret_api_key_value_12345" not in raw_json_str
        assert "sk-live-99999999999999999999" not in raw_json_str
        assert '"api_key"' not in raw_json_str

        data = res.json()
        assert data["findings"][0]["evidence"][0]["data"]["valid_metric"] == 42.5

    def test_no_raw_artifact_bytes(self, client: TestClient, db: sqlite3.Connection):
        """Export strictly references artifacts and does not embed binary blobs."""
        asmt_id = _seed_full_assessment(db, "asmt-nobytes-01")

        res = client.get(f"/api/v1/assessments/{asmt_id}/export/json")
        assert res.status_code == 200
        data = res.json()

        # All evidence data items must be structured JSON, not base64 or raw byte arrays
        for f in data["findings"]:
            for e in f["evidence"]:
                assert isinstance(e["data"], dict)
                for k, v in e["data"].items():
                    if isinstance(v, str):
                        # Should not be a huge base64 payload
                        assert len(v) < 10000

    def test_export_assessment_with_nan_inf_floats_produces_rfc8259_valid_json(
        self, client: TestClient, db: sqlite3.Connection
    ):
        """Exporting assessment with NaN and Inf floats produces strictly compliant RFC 8259 JSON without unquoted NaN."""
        import math
        asmt_id = _seed_full_assessment(db, "asmt-nan-01")

        # Inject NaN and Inf into an evidence payload
        ev_repo = EvidenceRepository(db)
        e = Evidence(
            finding_id="fnd-001",
            detector_id="model.integrity.mi02_weights",
            evidence_type=EvidenceType.MEASUREMENT,
            description="NaN and Inf float test evidence",
            data={
                "metric_nan": float("nan"),
                "metric_inf": float("inf"),
                "metric_neg_inf": float("-inf"),
                "valid_score": 0.95,
            },
        )
        ev_repo.insert(e)

        res = client.get(f"/api/v1/assessments/{asmt_id}/export/json")
        assert res.status_code == 200

        raw_text = res.text
        # Strict RFC 8259 validation: no raw unquoted NaN or Infinity in output
        assert ": NaN" not in raw_text
        assert ": Infinity" not in raw_text
        assert ": -Infinity" not in raw_text

        # Must parse cleanly with standard json parser
        parsed = json.loads(raw_text)
        assert parsed["assessment"]["assessment_id"] == asmt_id

        # Find the injected evidence and verify non-finite numbers converted to null (None)
        injected = None
        for f in parsed["findings"]:
            for ev in f["evidence"]:
                if ev["description"] == "NaN and Inf float test evidence":
                    injected = ev
                    break
        assert injected is not None
        assert injected["data"]["metric_nan"] is None
        assert injected["data"]["metric_inf"] is None
        assert injected["data"]["metric_neg_inf"] is None
        assert injected["data"]["valid_score"] == 0.95
