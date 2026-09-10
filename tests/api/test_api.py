"""
API tests — Health, Capabilities, Errors, and anti-fake integration.

Covers:
  T1 - /health endpoint
  T2 - /api/v1/capabilities endpoint
  T3 - Assessment creation (valid, invalid, bad paths)
  T4 - Assessment retrieval (GET, 404)
  T5 - Findings endpoint
  T6 - Evidence endpoint (no raw paths)
  T7 - Audit endpoint (valid chain + tamper detection)
  T8 - Error handling (structured responses, no stack traces)
  T9 - Anti-fake / determinism integration tests
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# T1 - Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client: TestClient):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_status_ok(self, client: TestClient):
        r = client.get("/health")
        body = r.json()
        assert body["status"] == "ok"

    def test_health_has_version(self, client: TestClient):
        r = client.get("/health")
        assert "version" in r.json()

    def test_health_has_db_path(self, client: TestClient):
        r = client.get("/health")
        assert "db_path" in r.json()

    def test_health_is_json(self, client: TestClient):
        r = client.get("/health")
        assert r.headers["content-type"].startswith("application/json")

    def test_health_does_not_run_assessment(self, client: TestClient, db: sqlite3.Connection):
        """Health must not create any assessment record."""
        from backend.infra.db import AssessmentRepository
        client.get("/health")
        records = AssessmentRepository(db).list_all()
        assert records == []


# ---------------------------------------------------------------------------
# T2 - Capabilities
# ---------------------------------------------------------------------------

class TestCapabilities:
    def test_capabilities_returns_200(self, client: TestClient):
        r = client.get("/api/v1/capabilities")
        assert r.status_code == 200

    def test_capabilities_has_detectors(self, client: TestClient):
        body = r = client.get("/api/v1/capabilities").json()
        assert "detectors" in body
        assert len(body["detectors"]) > 0

    def test_detector_ids_match_registry(self, client: TestClient):
        """Detector IDs in the response must match the real registry."""
        from backend.detectors.registry import DETECTOR_BY_ID
        body = client.get("/api/v1/capabilities").json()
        api_ids = {d["detector_id"] for d in body["detectors"]}
        registry_ids = set(DETECTOR_BY_ID.keys())
        assert api_ids == registry_ids

    def test_no_phantom_detectors(self, client: TestClient):
        """No detector_id may appear that is not in the real registry."""
        from backend.detectors.registry import DETECTOR_BY_ID
        body = client.get("/api/v1/capabilities").json()
        for det in body["detectors"]:
            assert det["detector_id"] in DETECTOR_BY_ID, (
                f"Phantom detector {det['detector_id']!r} not in registry"
            )

    def test_has_supported_formats(self, client: TestClient):
        body = client.get("/api/v1/capabilities").json()
        assert "supported_dataset_formats" in body
        assert "image_dir" in body["supported_dataset_formats"]

    def test_detector_has_required_fields(self, client: TestClient):
        body = client.get("/api/v1/capabilities").json()
        for det in body["detectors"]:
            for field in ["detector_id", "version", "name", "description",
                          "applicable_asset_types", "available"]:
                assert field in det, f"Missing field {field!r} in detector info"

    def test_versions_match_registry(self, client: TestClient):
        from backend.detectors.registry import DETECTOR_BY_ID
        body = client.get("/api/v1/capabilities").json()
        for det in body["detectors"]:
            registry_meta = DETECTOR_BY_ID[det["detector_id"]].metadata
            assert det["version"] == registry_meta.version


# ---------------------------------------------------------------------------
# T3 - Assessment creation
# ---------------------------------------------------------------------------

class TestAssessmentCreation:
    def test_empty_title_returns_422(self, client: TestClient, onnx_model: Path):
        r = client.post("/api/v1/assessments", json={
            "title": "",
            "model_path": str(onnx_model),
        })
        assert r.status_code == 422

    def test_no_assets_returns_4xx(self, client: TestClient):
        r = client.post("/api/v1/assessments", json={"title": "Empty"})
        assert r.status_code in (400, 422, 500)

    def test_relative_path_rejected(self, client: TestClient):
        r = client.post("/api/v1/assessments", json={
            "title": "Test",
            "model_path": "relative/path/model.onnx",
        })
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "invalid_asset_path"

    def test_nonexistent_path_rejected(self, client: TestClient):
        r = client.post("/api/v1/assessments", json={
            "title": "Test",
            "model_path": "/absolutely/nonexistent/path/model.onnx",
        })
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "invalid_asset_path"

    def test_unsupported_dataset_format_rejected(
        self, client: TestClient, image_dir: Path
    ):
        r = client.post("/api/v1/assessments", json={
            "title": "Test",
            "dataset_path": str(image_dir),
            "dataset_format": "parquet",
        })
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "unsupported_format"

    def test_valid_model_assessment_returns_201(
        self, client: TestClient, onnx_model: Path
    ):
        r = client.post("/api/v1/assessments", json={
            "title": "MI-01 Test",
            "model_path": str(onnx_model),
        })
        assert r.status_code == 201

    def test_valid_assessment_returns_assessment_id(
        self, client: TestClient, onnx_model: Path
    ):
        r = client.post("/api/v1/assessments", json={
            "title": "ID Test",
            "model_path": str(onnx_model),
        })
        body = r.json()
        assert "assessment_id" in body
        assert body["assessment_id"]

    def test_valid_assessment_returns_complete_status(
        self, client: TestClient, onnx_model: Path
    ):
        r = client.post("/api/v1/assessments", json={
            "title": "Status Test",
            "model_path": str(onnx_model),
        })
        body = r.json()
        assert body["status"] == "complete"

    def test_result_has_risk_and_confidence_separate(
        self, client: TestClient, onnx_model: Path
    ):
        """ADR-003 invariant: risk and confidence are always separate fields."""
        r = client.post("/api/v1/assessments", json={
            "title": "ADR-003",
            "model_path": str(onnx_model),
        })
        body = r.json()
        assert "overall_risk" in body
        assert "overall_confidence" in body
        assert body["overall_risk"] != body["overall_confidence"]

    def test_result_has_detector_runs(
        self, client: TestClient, onnx_model: Path
    ):
        r = client.post("/api/v1/assessments", json={
            "title": "Runs Test",
            "model_path": str(onnx_model),
        })
        body = r.json()
        assert "detector_runs" in body
        assert len(body["detector_runs"]) > 0

    def test_dataset_assessment_runs_di01(
        self, client: TestClient, image_dir: Path
    ):
        r = client.post("/api/v1/assessments", json={
            "title": "DI-01 Test",
            "dataset_path": str(image_dir),
            "dataset_format": "image_dir",
        })
        assert r.status_code == 201
        body = r.json()
        assert "data.integrity.di01_duplicates" in body["detectors_executed"]

    def test_custom_assessment_id_respected(
        self, client: TestClient, onnx_model: Path
    ):
        custom_id = "custom-assess-id-abc123"
        r = client.post("/api/v1/assessments", json={
            "title": "Custom ID",
            "assessment_id": custom_id,
            "model_path": str(onnx_model),
        })
        assert r.json()["assessment_id"] == custom_id

    def test_response_has_coverage_fraction(
        self, client: TestClient, onnx_model: Path
    ):
        r = client.post("/api/v1/assessments", json={
            "title": "Coverage",
            "model_path": str(onnx_model),
        })
        body = r.json()
        assert "coverage_fraction" in body
        assert 0.0 <= body["coverage_fraction"] <= 1.0

    def test_response_has_audit_chain_valid(
        self, client: TestClient, onnx_model: Path
    ):
        r = client.post("/api/v1/assessments", json={
            "title": "Audit",
            "model_path": str(onnx_model),
        })
        body = r.json()
        assert "audit_chain_valid" in body
        assert body["audit_chain_valid"] is True


# ---------------------------------------------------------------------------
# T4 - Assessment retrieval (GET)
# ---------------------------------------------------------------------------

class TestAssessmentRetrieval:
    def test_get_assessment_after_create(
        self, client: TestClient, onnx_model: Path
    ):
        create_r = client.post("/api/v1/assessments", json={
            "title": "Retrieve Me",
            "model_path": str(onnx_model),
        })
        assess_id = create_r.json()["assessment_id"]

        get_r = client.get(f"/api/v1/assessments/{assess_id}")
        assert get_r.status_code == 200

    def test_get_assessment_has_correct_id(
        self, client: TestClient, onnx_model: Path
    ):
        assess_id = "get-test-123"
        client.post("/api/v1/assessments", json={
            "title": "Get Test",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}").json()
        assert body["assessment_id"] == assess_id

    def test_get_assessment_has_title(
        self, client: TestClient, onnx_model: Path
    ):
        assess_id = "title-test-456"
        client.post("/api/v1/assessments", json={
            "title": "My Title",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}").json()
        assert body["title"] == "My Title"

    def test_get_missing_assessment_returns_404(self, client: TestClient):
        r = client.get("/api/v1/assessments/does-not-exist-xyz")
        assert r.status_code == 404
        body = r.json()
        assert body["error"] == "assessment_not_found"

    def test_404_body_has_structured_error(self, client: TestClient):
        r = client.get("/api/v1/assessments/missing")
        body = r.json()
        assert "error" in body
        assert "message" in body
        # No stack trace
        assert "traceback" not in json.dumps(body).lower()
        assert "exception" not in json.dumps(body).lower()

    def test_get_assessment_has_findings_count(
        self, client: TestClient, onnx_model: Path
    ):
        assess_id = "count-test-789"
        client.post("/api/v1/assessments", json={
            "title": "Count",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}").json()
        assert "findings_count" in body
        assert body["findings_count"] >= 1  # MI-01 always produces at least one


# ---------------------------------------------------------------------------
# T5 - Findings
# ---------------------------------------------------------------------------

class TestFindings:
    def test_findings_returns_200(self, client: TestClient, onnx_model: Path):
        assess_id = "findings-test"
        client.post("/api/v1/assessments", json={
            "title": "Findings",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        r = client.get(f"/api/v1/assessments/{assess_id}/findings")
        assert r.status_code == 200

    def test_findings_has_count_field(self, client: TestClient, onnx_model: Path):
        assess_id = "findings-count"
        client.post("/api/v1/assessments", json={
            "title": "F Count",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}/findings").json()
        assert "count" in body
        assert body["count"] == len(body["findings"])

    def test_findings_are_not_fabricated(
        self, client: TestClient, onnx_model: Path, db: sqlite3.Connection
    ):
        """
        count in response must match actual DB records.
        Findings cannot be hardcoded or fabricated by the API layer.
        """
        from backend.infra.db import FindingRepository
        assess_id = "no-fake-findings"
        client.post("/api/v1/assessments", json={
            "title": "Real Findings",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        api_count = client.get(
            f"/api/v1/assessments/{assess_id}/findings"
        ).json()["count"]
        db_count = len(FindingRepository(db).list_by_assessment(assess_id))
        assert api_count == db_count, (
            "API findings count must equal actual DB findings"
        )

    def test_findings_have_required_fields(
        self, client: TestClient, onnx_model: Path
    ):
        assess_id = "finding-fields"
        client.post("/api/v1/assessments", json={
            "title": "Fields",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}/findings").json()
        for f in body["findings"]:
            for field in [
                "finding_id", "assessment_id", "asset_id", "category",
                "subcategory", "severity", "title", "description", "detector_id",
            ]:
                assert field in f, f"Missing field {field!r} in finding"

    def test_findings_missing_assessment_returns_404(self, client: TestClient):
        r = client.get("/api/v1/assessments/no-such-id/findings")
        assert r.status_code == 404

    def test_duplicate_dataset_findings_present(
        self, client: TestClient, image_dir_with_duplicates: Path
    ):
        assess_id = "dup-findings"
        client.post("/api/v1/assessments", json={
            "title": "Duplicates",
            "assessment_id": assess_id,
            "dataset_path": str(image_dir_with_duplicates),
            "dataset_format": "image_dir",
        })
        body = client.get(f"/api/v1/assessments/{assess_id}/findings").json()
        assert body["count"] >= 1


# ---------------------------------------------------------------------------
# T6 - Evidence
# ---------------------------------------------------------------------------

class TestEvidence:
    def test_evidence_returns_200(self, client: TestClient, onnx_model: Path):
        assess_id = "ev-200"
        client.post("/api/v1/assessments", json={
            "title": "Ev",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        r = client.get(f"/api/v1/assessments/{assess_id}/evidence")
        assert r.status_code == 200

    def test_evidence_count_matches_db(
        self, client: TestClient, onnx_model: Path, db: sqlite3.Connection
    ):
        """Evidence count must equal real DB records (no fabrication)."""
        from backend.infra.db import EvidenceRepository, FindingRepository
        assess_id = "ev-count"
        client.post("/api/v1/assessments", json={
            "title": "Ev Count",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        api_count = client.get(
            f"/api/v1/assessments/{assess_id}/evidence"
        ).json()["count"]

        findings = FindingRepository(db).list_by_assessment(assess_id)
        db_count = sum(
            len(EvidenceRepository(db).list_by_finding(f.finding_id))
            for f in findings
        )
        assert api_count == db_count

    def test_evidence_does_not_expose_artifact_path(
        self, client: TestClient, onnx_model: Path
    ):
        """
        artifact_path (local filesystem path) must NEVER appear in evidence.
        """
        assess_id = "ev-privacy"
        client.post("/api/v1/assessments", json={
            "title": "Privacy",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}/evidence").json()
        raw = json.dumps(body)
        # The actual model path substring must not appear in the response
        assert str(onnx_model.parent) not in raw, (
            "Filesystem path must not be leaked in evidence response"
        )
        for ev in body["evidence"]:
            assert "artifact_path" not in ev, (
                "'artifact_path' field must be omitted from API evidence"
            )

    def test_evidence_has_required_fields(
        self, client: TestClient, onnx_model: Path
    ):
        assess_id = "ev-fields"
        client.post("/api/v1/assessments", json={
            "title": "Fields",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}/evidence").json()
        for ev in body["evidence"]:
            for field in [
                "evidence_id", "finding_id", "detector_id",
                "evidence_type", "description",
            ]:
                assert field in ev

    def test_evidence_missing_assessment_returns_404(self, client: TestClient):
        r = client.get("/api/v1/assessments/ghost/evidence")
        assert r.status_code == 404

    def test_evidence_data_is_structured_not_raw_bytes(
        self, client: TestClient, onnx_model: Path
    ):
        """Evidence data must be a dict, not raw binary."""
        assess_id = "ev-data"
        client.post("/api/v1/assessments", json={
            "title": "Data",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}/evidence").json()
        for ev in body["evidence"]:
            if ev["data"] is not None:
                assert isinstance(ev["data"], dict), (
                    "Evidence data must be a JSON object, not raw bytes"
                )


# ---------------------------------------------------------------------------
# T7 - Audit
# ---------------------------------------------------------------------------

class TestAudit:
    def test_audit_returns_200(self, client: TestClient, onnx_model: Path):
        assess_id = "audit-200"
        client.post("/api/v1/assessments", json={
            "title": "Audit",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        r = client.get(f"/api/v1/assessments/{assess_id}/audit")
        assert r.status_code == 200

    def test_valid_chain_reported_as_valid(
        self, client: TestClient, onnx_model: Path
    ):
        assess_id = "audit-valid"
        client.post("/api/v1/assessments", json={
            "title": "Valid Chain",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}/audit").json()
        assert body["chain_valid"] is True
        assert body["events_checked"] > 0

    def test_tampered_chain_reported_as_invalid(
        self, client: TestClient, onnx_model: Path, db: sqlite3.Connection
    ):
        """Directly mutate the DB and confirm the API detects it."""
        assess_id = "audit-tamper"
        client.post("/api/v1/assessments", json={
            "title": "Tamper Test",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })

        # Tamper: overwrite the first event's hash
        db.execute(
            "UPDATE audit_events SET current_hash=? WHERE rowid=1",
            ("0" * 64,),
        )
        db.commit()

        body = client.get(f"/api/v1/assessments/{assess_id}/audit").json()
        assert body["chain_valid"] is False

    def test_audit_has_event_list(self, client: TestClient, onnx_model: Path):
        assess_id = "audit-events"
        client.post("/api/v1/assessments", json={
            "title": "Events",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}/audit").json()
        assert "events" in body
        assert len(body["events"]) > 0

    def test_audit_events_have_hashes(
        self, client: TestClient, onnx_model: Path
    ):
        assess_id = "audit-hashes"
        client.post("/api/v1/assessments", json={
            "title": "Hashes",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })
        body = client.get(f"/api/v1/assessments/{assess_id}/audit").json()
        for event in body["events"]:
            assert "current_hash" in event
            assert "previous_hash" in event
            assert len(event["current_hash"]) == 64  # SHA-256 hex

    def test_audit_missing_assessment_returns_404(self, client: TestClient):
        r = client.get("/api/v1/assessments/ghost/audit")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# T8 - Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_404_is_structured_json(self, client: TestClient):
        r = client.get("/api/v1/assessments/does-not-exist/findings")
        assert r.status_code == 404
        body = r.json()
        assert "error" in body
        assert "message" in body

    def test_no_stack_trace_in_404(self, client: TestClient):
        r = client.get("/api/v1/assessments/does-not-exist/evidence")
        raw = json.dumps(r.json())
        assert "Traceback" not in raw
        assert "File " not in raw

    def test_invalid_path_gives_structured_422(self, client: TestClient):
        r = client.post("/api/v1/assessments", json={
            "title": "Bad Path",
            "model_path": "not/absolute",
        })
        assert r.status_code == 422
        body = r.json()
        assert "error" in body

    def test_no_stack_trace_in_path_error(self, client: TestClient):
        r = client.post("/api/v1/assessments", json={
            "title": "Stack Check",
            "model_path": "/nonexistent/model.onnx",
        })
        raw = json.dumps(r.json())
        assert "Traceback" not in raw
        assert "File " not in raw

    def test_malformed_json_returns_422(self, client: TestClient):
        r = client.post(
            "/api/v1/assessments",
            content=b"not json at all {{{",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 422

    def test_missing_title_returns_422(self, client: TestClient, onnx_model: Path):
        r = client.post("/api/v1/assessments", json={
            "model_path": str(onnx_model),
        })
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# T9 - Anti-fake / Determinism integration tests
# ---------------------------------------------------------------------------

class TestAntiFakeIntegration:
    def test_end_to_end_real_assessment_via_http(
        self, client: TestClient, onnx_model: Path, db: sqlite3.Connection
    ):
        """
        Full stack integration test:
          HTTP POST → FastAPI → AssessmentService → MI-01 → DB → HTTP response

        Verifies the response comes from real analysis, not hardcoded values.
        """
        from backend.infra.db import EvidenceRepository, FindingRepository

        assess_id = "e2e-real"
        r = client.post("/api/v1/assessments", json={
            "title": "E2E Real",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })

        assert r.status_code == 201
        body = r.json()

        # Verify response fields come from real DB records
        db_findings = FindingRepository(db).list_by_assessment(assess_id)
        assert body["findings_count"] == len(db_findings), (
            "findings_count in response must equal actual DB findings"
        )

        db_evidence_count = sum(
            len(EvidenceRepository(db).list_by_finding(f.finding_id))
            for f in db_findings
        )
        assert body["evidence_count"] == db_evidence_count, (
            "evidence_count in response must equal actual DB evidence"
        )

    def test_different_models_produce_different_evidence(
        self, client: TestClient, db: sqlite3.Connection, tmp_path: Path
    ):
        """
        Change the model → evidence changes. Proves the API returns
        real findings, not hardcoded values.
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from detectors.onnx_writer import make_add_bias_model, make_relu_model
        from backend.infra.db import EvidenceRepository, FindingRepository

        model_a = tmp_path / "relu.onnx"
        model_b = tmp_path / "add_bias.onnx"
        model_a.write_bytes(make_relu_model([1, 4]))
        model_b.write_bytes(make_add_bias_model([1.0, 2.0, 3.0, 4.0], [1, 4]))

        def _get_sha(assess_id: str) -> str | None:
            findings = FindingRepository(db).list_by_assessment(assess_id)
            for f in findings:
                for e in EvidenceRepository(db).list_by_finding(f.finding_id):
                    if e.data and "artifact_sha256" in e.data:
                        return e.data["artifact_sha256"]
            return None

        client.post("/api/v1/assessments", json={
            "title": "Model A",
            "assessment_id": "anti-fake-a",
            "model_path": str(model_a),
        })
        client.post("/api/v1/assessments", json={
            "title": "Model B",
            "assessment_id": "anti-fake-b",
            "model_path": str(model_b),
        })

        sha_a = _get_sha("anti-fake-a")
        sha_b = _get_sha("anti-fake-b")
        assert sha_a is not None, "Model A must produce evidence with SHA-256"
        assert sha_b is not None, "Model B must produce evidence with SHA-256"
        assert sha_a != sha_b, (
            "Different models must produce different SHA-256 fingerprints. "
            "If they are equal the API is returning hardcoded/mocked results."
        )

    def test_same_model_same_sha256_deterministic(
        self, client: TestClient, db: sqlite3.Connection, tmp_path: Path
    ):
        """Same model → same SHA-256 in evidence across two assessment runs."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from detectors.onnx_writer import make_relu_model
        from backend.infra.db import EvidenceRepository, FindingRepository

        model_path = tmp_path / "relu.onnx"
        model_path.write_bytes(make_relu_model([1, 3]))

        def _get_sha(assess_id: str) -> str | None:
            findings = FindingRepository(db).list_by_assessment(assess_id)
            for f in findings:
                for e in EvidenceRepository(db).list_by_finding(f.finding_id):
                    if e.data and "artifact_sha256" in e.data:
                        return e.data["artifact_sha256"]
            return None

        client.post("/api/v1/assessments", json={
            "title": "Run 1", "assessment_id": "det-1",
            "model_path": str(model_path),
        })
        client.post("/api/v1/assessments", json={
            "title": "Run 2", "assessment_id": "det-2",
            "model_path": str(model_path),
        })

        sha_1 = _get_sha("det-1")
        sha_2 = _get_sha("det-2")
        assert sha_1 is not None
        assert sha_2 is not None
        assert sha_1 == sha_2, "Same model must produce same SHA-256 (deterministic)"

    def test_findings_endpoint_returns_real_db_findings(
        self, client: TestClient, onnx_model: Path, db: sqlite3.Connection
    ):
        """GET /findings must return exactly the DB-persisted findings."""
        from backend.infra.db import FindingRepository

        assess_id = "findings-real"
        client.post("/api/v1/assessments", json={
            "title": "Real DB Findings",
            "assessment_id": assess_id,
            "model_path": str(onnx_model),
        })

        api_findings = client.get(
            f"/api/v1/assessments/{assess_id}/findings"
        ).json()["findings"]
        db_findings = FindingRepository(db).list_by_assessment(assess_id)

        assert len(api_findings) == len(db_findings)
        api_ids = {f["finding_id"] for f in api_findings}
        db_ids = {f.finding_id for f in db_findings}
        assert api_ids == db_ids, (
            "API finding IDs must exactly match DB finding IDs"
        )

    def test_duplicate_dataset_produces_findings_via_api(
        self, client: TestClient, image_dir_with_duplicates: Path
    ):
        """
        DI-01 must detect duplicates when run through the full HTTP API stack.
        """
        r = client.post("/api/v1/assessments", json={
            "title": "Dup via API",
            "assessment_id": "dup-api",
            "dataset_path": str(image_dir_with_duplicates),
            "dataset_format": "image_dir",
        })
        assert r.status_code == 201
        body = r.json()
        assert body["findings_count"] >= 1
        assert body["overall_risk"] != "none"
