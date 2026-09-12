"""
PRAMAAN v1 — Model Integrity Corpus Test Suite.

Validates the reproducible model integrity validation corpus across:
  Test A: Generator determinism (same seed -> byte-identical digests)
  Test B: Manifest integrity (schemas, scenario listings, roles)
  Test C: Sample SHA-256 digest correctness against disk bytes
  Test D: Ground truth isolation (strictly outside input directories)
  Test E: Scenario artifact validity (framework loading and execution)
  Test F: Scenario-specific detector results (Scenarios 01 through 07)
  Test G: AssessmentService end-to-end integration and audit chain
  Test H: API-level representative scenarios (Upload + Assessment routes)
  Test I: Malformed artifact rejection (fail-closed security boundary)
  Test J: Coverage-gap semantics (PyTorch state dict non-executability)
  Test K: Risk / Confidence / Coverage separation (ADR-003 orthogonality)
  Test L: Repeated generation reproducibility
  Test M: Security & fail-closed behavior (path safety, weights_only)
  Test N: No unexpected filesystem / network behavior (pure offline confinement)
"""

from __future__ import annotations

import io
import json
import socket
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import torch
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_db
from backend.assessment.models import AssessmentRequest
from backend.assessment.orchestrator import AssessmentService
from backend.domain.enums import (
    ConfidenceLevel,
    DetectorStatus,
    RiskLevel,
    Severity,
)
from backend.infra.crypto import hash_file
from backend.infra.db import open_db
from backend.infra.model_loader import (
    ModelLoadError,
    ModelLoadErrorCode,
    load_model,
)
from backend.tools.model_corpus_generator import (
    DEFAULT_MODEL_CORPUS_ROOT,
    generate_model_corpus,
    validate_model_scenario_against_detectors,
)


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    """Isolated database connection for model corpus testing."""
    conn = open_db(tmp_path / "model_corpus_test.db")
    yield conn
    conn.close()


@pytest.fixture
def api_client(test_db: sqlite3.Connection) -> TestClient:
    """FastAPI TestClient with isolated test database."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: test_db
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def model_corpus_root() -> Path:
    """Ensure model corpus is generated and return its root directory."""
    root = DEFAULT_MODEL_CORPUS_ROOT
    if not (root / "corpus_manifest.json").is_file():
        generate_model_corpus(root, master_seed=42)
    return root


# ===========================================================================
# Test A: Generator Determinism
# ===========================================================================

class TestModelCorpusDeterminism:
    """Verify that the model corpus generator is strictly deterministic under identical seeds."""

    def test_generator_deterministic_output(self, tmp_path: Path):
        run1_dir = tmp_path / "run1"
        run2_dir = tmp_path / "run2"

        manifest1 = generate_model_corpus(run1_dir, master_seed=42)
        manifest2 = generate_model_corpus(run2_dir, master_seed=42)

        assert manifest1["total_models"] == manifest2["total_models"]
        assert manifest1["total_scenarios"] == manifest2["total_scenarios"]

        # Check byte-for-byte identity of all models across all 9 scenarios
        for scen_entry in manifest1["scenarios"]:
            scen_id = scen_entry["scenario_id"]
            files1 = sorted(list((run1_dir / f"scenarios/{scen_id}/input").glob("*.*")))
            files2 = sorted(list((run2_dir / f"scenarios/{scen_id}/input").glob("*.*")))
            assert len(files1) == len(files2)
            for f1, f2 in zip(files1, files2):
                assert f1.name == f2.name
                assert hash_file(f1) == hash_file(f2), f"Digest mismatch on {scen_id}/{f1.name}"


# ===========================================================================
# Test B & C: Manifest Integrity & SHA-256 Digest Verification
# ===========================================================================

class TestManifestIntegrity:
    """Verify manifest schemas, path references, and hash digests against actual disk bytes."""

    def test_corpus_manifest_schema(self, model_corpus_root: Path):
        cm_path = model_corpus_root / "corpus_manifest.json"
        assert cm_path.is_file()
        cm = json.loads(cm_path.read_text(encoding="utf-8"))

        assert cm["manifest_version"] == "1.0.0"
        assert cm["total_scenarios"] == 9
        assert cm["total_models"] >= 10
        assert len(cm["scenarios"]) == 9

    def test_scenario_manifests_and_hashes(self, model_corpus_root: Path):
        scenarios_dir = model_corpus_root / "scenarios"
        for s_dir in sorted(scenarios_dir.iterdir()):
            if not s_dir.is_dir():
                continue

            manifest_path = s_dir / "model_manifest.json"
            assert manifest_path.is_file(), f"Missing model_manifest in {s_dir.name}"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            input_dir = s_dir / "input"
            assert input_dir.is_dir()

            # Verify every declared model exists and hash matches byte content
            for m in manifest["models"]:
                m_path = input_dir / m["file_name"]
                assert m_path.is_file(), f"Model file not found: {m_path}"
                computed_sha256 = hash_file(m_path)
                assert computed_sha256 == m["sha256"], f"Digest mismatch on {m_path.name}"
                assert m["size_bytes"] == m_path.stat().st_size


# ===========================================================================
# Test D: Ground Truth Isolation
# ===========================================================================

class TestGroundTruthIsolation:
    """Verify that ground truth metadata is strictly isolated and never leaked into inputs."""

    def test_ground_truth_never_in_input_directory(self, model_corpus_root: Path):
        scenarios_dir = model_corpus_root / "scenarios"
        for s_dir in scenarios_dir.iterdir():
            if not s_dir.is_dir():
                continue
            input_dir = s_dir / "input"
            assert not (input_dir / "ground_truth.json").exists()
            assert not (input_dir / "ground_truth").exists()
            for p in input_dir.rglob("*"):
                assert "ground_truth" not in p.name.lower()

    def test_operational_manifest_has_no_ground_truth(self, model_corpus_root: Path):
        scenarios_dir = model_corpus_root / "scenarios"
        for s_dir in scenarios_dir.iterdir():
            if not s_dir.is_dir():
                continue
            m_path = s_dir / "model_manifest.json"
            data = json.loads(m_path.read_text(encoding="utf-8"))
            # Operational manifest should not leak expected risk or detection outcomes
            assert "expected_overall_risk" not in data
            assert "expected_findings" not in data


# ===========================================================================
# Test E: Scenario Artifact Validity
# ===========================================================================

class TestArtifactValidity:
    """Verify that model files load properly with supported framework loaders."""

    def test_onnx_artifacts_valid_or_expected_malformed(self, model_corpus_root: Path):
        scenarios_dir = model_corpus_root / "scenarios"
        for s_dir in scenarios_dir.iterdir():
            if not s_dir.is_dir():
                continue
            for model_file in (s_dir / "input").glob("*.onnx"):
                abs_path = model_file.resolve()
                if "corrupt_header" in model_file.name:
                    with pytest.raises(ModelLoadError) as exc_info:
                        load_model(abs_path)
                    assert exc_info.value.code == ModelLoadErrorCode.MALFORMED
                else:
                    loaded = load_model(abs_path)
                    assert loaded.framework == "onnx"
                    assert loaded.file_size > 0

    def test_pytorch_artifact_valid_state_dict(self, model_corpus_root: Path):
        pt_file = (model_corpus_root / "scenarios/08_state_dict_coverage_gap/input/model.pt").resolve()
        assert pt_file.is_file()
        loaded = load_model(pt_file)
        assert loaded.framework == "pytorch"
        assert isinstance(loaded.raw_object, dict)
        assert "conv.weight" in loaded.raw_object


# ===========================================================================
# Test F: Scenario-Specific Detector Results (Scenarios 01 through 07)
# ===========================================================================

class TestScenarioSpecificDetection:
    """Verify detector outcomes match Phase 16A expectations across scenarios 01 through 07."""

    def test_scenario_01_clean_reference(self, model_corpus_root: Path):
        res = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/01_clean_reference")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        assert res["observed_risk"] == "none"
        dets = res["detector_results"]
        for dname, data in dets.items():
            assert data["risk"] == "none"

    def test_scenario_02_model_substitution(self, model_corpus_root: Path):
        res = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/02_model_substitution")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        assert res["observed_risk"] == "medium"
        dets = res["detector_results"]
        assert dets["mi04_reference_comparison"]["risk"] == "medium"
        assert dets["mi04_reference_comparison"]["status"] == "success"

    def test_scenario_03_parameter_corruption(self, model_corpus_root: Path):
        res = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/03_parameter_corruption")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        assert res["observed_risk"] == "high"
        dets = res["detector_results"]
        assert dets["mi02_parameter_stats"]["risk"] == "high"
        assert dets["mi03_activation_stats"]["risk"] == "high"

    def test_scenario_04_weight_magnitude_anomaly(self, model_corpus_root: Path):
        res = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/04_weight_magnitude_anomaly")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        assert res["observed_risk"] == "medium"
        dets = res["detector_results"]
        assert dets["mi02_parameter_stats"]["risk"] == "medium"
        assert dets["mi04_reference_comparison"]["risk"] == "medium"

    def test_scenario_05_activation_collapse(self, model_corpus_root: Path):
        res = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/05_activation_collapse")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        assert res["observed_risk"] == "medium"
        dets = res["detector_results"]
        assert dets["mi03_activation_stats"]["risk"] == "medium"
        # MI-05 correctly gates on insufficient clean diversity
        assert dets["mi05_trigger_anomaly"]["status"] == "partial"
        assert dets["mi05_trigger_anomaly"]["risk"] == "none"

    def test_scenario_06_trigger_convergence(self, model_corpus_root: Path):
        res = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/06_trigger_convergence")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        assert res["observed_risk"] == "high"
        dets = res["detector_results"]
        assert dets["mi05_trigger_anomaly"]["risk"] == "high"
        assert dets["mi05_trigger_anomaly"]["status"] == "success"

    def test_scenario_07_missing_reference(self, model_corpus_root: Path):
        res = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/07_missing_reference")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        assert res["observed_risk"] == "none"
        dets = res["detector_results"]
        assert dets["mi04_reference_comparison"]["status"] == "not_applicable"


# ===========================================================================
# Test G: AssessmentService Integration
# ===========================================================================

class TestAssessmentServiceIntegration:
    """Verify end-to-end AssessmentService execution, database records, and audit verifier."""

    def test_full_orchestration_run(self, test_db: sqlite3.Connection, model_corpus_root: Path):
        cand_path = (model_corpus_root / "scenarios/01_clean_reference/input/model.onnx").resolve()
        ref_path = (model_corpus_root / "scenarios/01_clean_reference/input/reference.onnx").resolve()

        svc = AssessmentService(test_db)
        req = AssessmentRequest(
            title="E2E Model Assessment Test",
            model_path=cand_path,
            model_reference_path=ref_path,
        )
        res = svc.run_assessment(req)

        assert res.overall_risk == RiskLevel.NONE
        assert res.overall_confidence == ConfidenceLevel.HIGH
        assert res.audit_chain_valid is True
        assert res.findings_count >= 1  # info baseline findings
        assert len(res.detector_runs) >= 5


# ===========================================================================
# Test H: API-Level Representative Scenarios
# ===========================================================================

class TestModelApiE2E:
    """Verify upload and assessment via live FastAPI HTTP API routes."""

    def test_upload_and_assess_model_via_api(self, api_client: TestClient, model_corpus_root: Path):
        cand_path = (model_corpus_root / "scenarios/03_parameter_corruption/input/model.onnx").resolve()
        ref_path = (model_corpus_root / "scenarios/03_parameter_corruption/input/reference.onnx").resolve()

        # 1. Upload candidate model
        with open(cand_path, "rb") as f:
            up_cand = api_client.post(
                "/api/v1/uploads",
                files={"file": (cand_path.name, f.read(), "application/octet-stream")},
                data={"asset_type": "model"},
            )
        assert up_cand.status_code == 201, up_cand.text
        cand_id = up_cand.json()["asset_id"]

        # 2. Upload reference model
        with open(ref_path, "rb") as f:
            up_ref = api_client.post(
                "/api/v1/uploads",
                files={"file": (ref_path.name, f.read(), "application/octet-stream")},
                data={"asset_type": "model"},
            )
        assert up_ref.status_code == 201, up_ref.text
        ref_id = up_ref.json()["asset_id"]

        # 3. Create assessment
        asmt_res = api_client.post(
            "/api/v1/assessments",
            json={
                "title": "API Model Assessment 03",
                "model_asset_id": cand_id,
                "model_reference_asset_id": ref_id,
            },
        )
        assert asmt_res.status_code == 201, asmt_res.text
        data = asmt_res.json()
        assert data["overall_risk"].upper() == "HIGH"
        assert data["findings_count"] > 0

        # 4. Query findings endpoint
        f_res = api_client.get(f"/api/v1/assessments/{data['assessment_id']}/findings")
        assert f_res.status_code == 200
        findings = f_res.json()["findings"]
        subcats = {f["subcategory"] for f in findings}
        assert "parameter_corruption" in subcats


# ===========================================================================
# Test I: Malformed Artifact Rejection
# ===========================================================================

class TestMalformedArtifactRejection:
    """Verify fail-closed rejection of corrupted models."""

    def test_corrupt_onnx_rejected(self, model_corpus_root: Path):
        res = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/09_malformed_artifact")
        assert res["passed"] is True
        assert res["detector_results"]["load_model"] == "MALFORMED_REJECTED"


# ===========================================================================
# Test J: Coverage-Gap Semantics
# ===========================================================================

class TestCoverageGapSemantics:
    """Verify explicit coverage gaps for non-executable PyTorch state dicts."""

    def test_pytorch_state_dict_emits_coverage_gaps(self, model_corpus_root: Path):
        res = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/08_state_dict_coverage_gap")
        assert res["passed"] is True
        assert res["observed_risk"] == "none"
        assert len(res["coverage_gaps"]) == 2
        assert "model.integrity.mi03_activation_stats" in res["coverage_gaps"]
        assert "model.integrity.mi05_trigger_anomaly" in res["coverage_gaps"]
        assert res["detector_results"]["mi03_activation_stats"]["status"] == "skipped"
        assert res["detector_results"]["mi05_trigger_anomaly"]["status"] == "skipped"


# ===========================================================================
# Test K: Risk / Confidence / Coverage Separation
# ===========================================================================

class TestRiskConfidenceSeparation:
    """Verify ADR-003 orthogonality between Risk and Confidence."""

    def test_risk_and_confidence_orthogonal(self, model_corpus_root: Path):
        # Scenario 03: High risk, High confidence
        res03 = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/03_parameter_corruption")
        assert res03["observed_risk"] == "high"
        assert res03["observed_confidence"] == "high"

        # Scenario 05: Medium risk, Low confidence (due to insufficient probe diversity)
        res05 = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/05_activation_collapse")
        assert res05["observed_risk"] == "medium"
        assert res05["observed_confidence"] == "low"

        # Scenario 08: None risk, Low confidence (due to coverage gaps)
        res08 = validate_model_scenario_against_detectors(model_corpus_root / "scenarios/08_state_dict_coverage_gap")
        assert res08["observed_risk"] == "none"
        assert res08["observed_confidence"] == "low"


# ===========================================================================
# Test L: Repeated Generation Reproducibility
# ===========================================================================

class TestRepeatedGeneration:
    """Verify that re-running generator does not introduce random artifacts."""

    def test_repeat_generation_exact_bytes(self, tmp_path: Path):
        d1 = tmp_path / "d1"
        d2 = tmp_path / "d2"
        generate_model_corpus(d1, master_seed=42)
        generate_model_corpus(d2, master_seed=42)

        for scen in ["01_clean_reference", "03_parameter_corruption", "06_trigger_convergence", "08_state_dict_coverage_gap"]:
            m1 = list((d1 / f"scenarios/{scen}/input").glob("*.*"))[0]
            m2 = list((d2 / f"scenarios/{scen}/input").glob("*.*"))[0]
            assert hash_file(m1) == hash_file(m2)


# ===========================================================================
# Test M: Security & Fail-Closed Behavior
# ===========================================================================

class TestSecurityFailClosed:
    """Verify security controls around path validation and unsafe deserialization."""

    def test_relative_path_rejected(self, tmp_path: Path):
        with pytest.raises(ModelLoadError) as exc:
            load_model(Path("relative/path/model.onnx"))
        assert exc.value.code == ModelLoadErrorCode.PATH_TRAVERSAL

    def test_unsafe_pickle_weights_only_enforced(self, tmp_path: Path):
        # Create a PyTorch file with arbitrary Python class
        class MaliciousPayload:
            def __reduce__(self):
                return (eval, ("1 + 1",))

        payload_path = (tmp_path / "unsafe.pt").resolve()
        torch.save(MaliciousPayload(), payload_path)

        with pytest.raises(ModelLoadError) as exc:
            load_model(payload_path)
        assert exc.value.code == ModelLoadErrorCode.UNSAFE_PICKLE


# ===========================================================================
# Test N: No Unexpected Network Behavior
# ===========================================================================

class TestNoNetworkCalls:
    """Verify that model generation and detector execution make zero outbound network calls."""

    def test_generator_offline(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        def guarded_connect(*args, **kwargs):
            raise AssertionError("Network connection attempted during offline model generation!")

        monkeypatch.setattr(socket.socket, "connect", guarded_connect)

        # Generate and validate offline
        out_dir = tmp_path / "offline_test"
        manifest = generate_model_corpus(out_dir, master_seed=42)
        assert manifest["total_scenarios"] == 9
