"""
PRAMAAN v1 — Training & Data Integrity Corpus Test Suite.

Validates the reproducible training/data integrity corpus across:
  Test A: Corpus generator determinism (same seed -> identical byte digests)
  Test B: Manifest schema and path integrity
  Test C: Sample SHA-256 digest correctness against disk bytes
  Test D: Ground truth isolation (never in input/ or ZIP archive)
  Test E-M: Per-scenario detector validation (01 through 09)
  Test N: Real API E2E upload and assessment execution
  Test O: Repeat assessment reproducibility
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_db
from backend.domain.entities import Assessment, DatasetFormat
from backend.domain.enums import RiskLevel, Severity
from backend.infra.crypto import hash_file
from backend.infra.db import AssessmentRepository, open_db
from backend.infra.ingestion import ingest_image_directory, register_dataset
from backend.tools.corpus_generator import (
    DEFAULT_CORPUS_ROOT,
    generate_corpus,
    validate_scenario_against_detectors,
)


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    """Isolated database connection for corpus testing."""
    return open_db(tmp_path / "corpus_test.db")


@pytest.fixture
def api_client(test_db: sqlite3.Connection) -> TestClient:
    """FastAPI TestClient with isolated test database."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: test_db
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def corpus_root() -> Path:
    """Ensure corpus is generated and return its root directory."""
    root = DEFAULT_CORPUS_ROOT
    if not (root / "corpus_manifest.json").is_file():
        generate_corpus(root, master_seed=42)
    return root


# ===========================================================================
# Test A: Generator Determinism
# ===========================================================================

class TestCorpusDeterminism:
    """Verify that the corpus generator is strictly deterministic under identical seeds."""

    def test_generator_deterministic_output(self, tmp_path: Path):
        run1_dir = tmp_path / "run1"
        run2_dir = tmp_path / "run2"

        manifest1 = generate_corpus(run1_dir, master_seed=12345)
        manifest2 = generate_corpus(run2_dir, master_seed=12345)

        assert manifest1["total_images"] == manifest2["total_images"]
        assert manifest1["total_scenarios"] == manifest2["total_scenarios"]

        # Check byte-for-byte identity of all images in Scenario 01 and Scenario 06
        for scen in ["01_clean_baseline", "06_recurring_pattern", "09_mixed_scenario"]:
            imgs1 = sorted(list((run1_dir / f"scenarios/{scen}/input/images").glob("*.png")))
            imgs2 = sorted(list((run2_dir / f"scenarios/{scen}/input/images").glob("*.png")))
            assert len(imgs1) == len(imgs2)
            for f1, f2 in zip(imgs1, imgs2):
                assert f1.name == f2.name
                assert hash_file(f1) == hash_file(f2)


# ===========================================================================
# Test B & C: Manifest Integrity & SHA-256 Digest Verification
# ===========================================================================

class TestManifestIntegrity:
    """Verify manifest schemas, path references, and hash digests against actual disk bytes."""

    def test_corpus_manifest_schema(self, corpus_root: Path):
        cm_path = corpus_root / "corpus_manifest.json"
        assert cm_path.is_file()
        cm = json.loads(cm_path.read_text(encoding="utf-8"))

        assert cm["manifest_version"] == "1.0.0"
        assert cm["total_scenarios"] == 9
        assert cm["total_images"] > 0
        assert len(cm["scenarios"]) == 9

    def test_scenario_manifests_and_hashes(self, corpus_root: Path):
        scenarios_dir = corpus_root / "scenarios"
        for s_dir in sorted(scenarios_dir.iterdir()):
            if not s_dir.is_dir():
                continue

            manifest_path = s_dir / "input" / "dataset_manifest.json"
            meta_path = s_dir / "input" / "metadata.json"
            assert manifest_path.is_file(), f"Missing dataset_manifest in {s_dir.name}"
            assert meta_path.is_file(), f"Missing metadata.json in {s_dir.name}"

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            images_dir = s_dir / "input" / "images"
            assert images_dir.is_dir()

            # Verify every declared sample exists and hash matches byte content
            for sample in manifest["samples"]:
                img_path = images_dir / sample["file_name"]
                assert img_path.is_file(), f"Sample file not found: {img_path}"
                computed_sha256 = hash_file(img_path)
                assert computed_sha256 == sample["sha256"], f"Digest mismatch on {img_path.name}"


# ===========================================================================
# Test D: Ground Truth Isolation
# ===========================================================================

class TestGroundTruthIsolation:
    """Verify that ground truth metadata is strictly isolated and never leaked into inputs or ZIPs."""

    def test_ground_truth_never_in_input_directory(self, corpus_root: Path):
        scenarios_dir = corpus_root / "scenarios"
        for s_dir in scenarios_dir.iterdir():
            if not s_dir.is_dir():
                continue
            input_dir = s_dir / "input"
            # No ground truth files inside input
            assert not (input_dir / "ground_truth.json").exists()
            assert not (input_dir / "ground_truth").exists()
            for p in input_dir.rglob("*"):
                assert "ground_truth" not in p.name.lower()

    def test_ground_truth_never_in_zip_archive(self, corpus_root: Path):
        scenarios_dir = corpus_root / "scenarios"
        for s_dir in scenarios_dir.iterdir():
            if not s_dir.is_dir():
                continue
            zip_candidates = list(s_dir.glob("*.zip"))
            assert len(zip_candidates) == 1
            z_path = zip_candidates[0]

            with zipfile.ZipFile(z_path, "r") as zf:
                for entry in zf.namelist():
                    assert "ground_truth" not in entry.lower()
                    assert "expected" not in entry.lower()


# ===========================================================================
# Tests E through M: Per-Scenario Detection & Orthogonality
# ===========================================================================

class TestScenarioDetectionMatrix:
    """Verify actual detector behavior matches qualitative expectations for all 9 scenarios."""

    def test_scenario_01_clean_baseline(self, corpus_root: Path):
        res = validate_scenario_against_detectors(corpus_root / "scenarios/01_clean_baseline")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        dets = res["detector_results"]
        for name, data in dets.items():
            assert data["findings_count"] == 0, f"{name} unexpectedly flagged clean baseline"
            assert data["risk"] == "none"

    def test_scenario_02_exact_duplicate(self, corpus_root: Path):
        res = validate_scenario_against_detectors(corpus_root / "scenarios/02_exact_duplicate")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        dets = res["detector_results"]
        assert dets["di01_duplicates"]["findings_count"] > 0
        assert dets["di02_label_integrity"]["findings_count"] == 0
        assert dets["di03_trigger_anomaly"]["findings_count"] == 0
        assert dets["di04_ood_distribution"]["findings_count"] == 0
        assert dets["di05_contributor_risk"]["findings_count"] == 0

    def test_scenario_03_near_duplicate(self, corpus_root: Path):
        res = validate_scenario_against_detectors(corpus_root / "scenarios/03_near_duplicate")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        dets = res["detector_results"]
        assert dets["di01_duplicates"]["findings_count"] > 0
        assert dets["di02_label_integrity"]["findings_count"] == 0
        assert dets["di03_trigger_anomaly"]["findings_count"] == 0
        assert dets["di04_ood_distribution"]["findings_count"] == 0
        assert dets["di05_contributor_risk"]["findings_count"] == 0

    def test_scenario_04_label_flip(self, corpus_root: Path):
        res = validate_scenario_against_detectors(corpus_root / "scenarios/04_label_flip")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        dets = res["detector_results"]
        assert dets["di02_label_integrity"]["findings_count"] >= 1
        assert dets["di02_label_integrity"]["risk"] == "high"
        # DI-01 legitimately sees the perceptual near duplicate
        assert dets["di03_trigger_anomaly"]["findings_count"] == 0
        assert dets["di04_ood_distribution"]["findings_count"] == 0
        assert dets["di05_contributor_risk"]["findings_count"] == 0

    def test_scenario_05_systematic_mislabelling(self, corpus_root: Path):
        res = validate_scenario_against_detectors(corpus_root / "scenarios/05_systematic_mislabelling")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        dets = res["detector_results"]
        assert dets["di02_label_integrity"]["findings_count"] >= 2
        assert dets["di02_label_integrity"]["risk"] == "high"
        assert dets["di03_trigger_anomaly"]["findings_count"] == 0
        assert dets["di04_ood_distribution"]["findings_count"] == 0
        assert dets["di05_contributor_risk"]["findings_count"] == 0

    def test_scenario_06_recurring_pattern(self, corpus_root: Path):
        res = validate_scenario_against_detectors(corpus_root / "scenarios/06_recurring_pattern")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        dets = res["detector_results"]
        assert dets["di03_trigger_anomaly"]["findings_count"] >= 1
        assert dets["di03_trigger_anomaly"]["risk"] == "high"
        assert dets["di01_duplicates"]["findings_count"] == 0
        assert dets["di02_label_integrity"]["findings_count"] == 0
        assert dets["di04_ood_distribution"]["findings_count"] == 0
        assert dets["di05_contributor_risk"]["findings_count"] == 0

    def test_scenario_07_ood_distribution(self, corpus_root: Path):
        res = validate_scenario_against_detectors(corpus_root / "scenarios/07_ood_distribution")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        dets = res["detector_results"]
        assert dets["di04_ood_distribution"]["findings_count"] >= 1
        assert dets["di04_ood_distribution"]["risk"] in ("medium", "high")
        assert dets["di01_duplicates"]["findings_count"] == 0
        assert dets["di02_label_integrity"]["findings_count"] == 0
        assert dets["di03_trigger_anomaly"]["findings_count"] == 0
        assert dets["di05_contributor_risk"]["findings_count"] == 0

    def test_scenario_08_contributor_concentration(self, corpus_root: Path):
        res = validate_scenario_against_detectors(corpus_root / "scenarios/08_contributor_concentration")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        dets = res["detector_results"]
        assert dets["di05_contributor_risk"]["findings_count"] >= 1
        assert dets["di05_contributor_risk"]["risk"] == "high"
        assert dets["di01_duplicates"]["findings_count"] > 0
        assert dets["di02_label_integrity"]["findings_count"] > 0
        assert dets["di03_trigger_anomaly"]["findings_count"] == 0
        assert dets["di04_ood_distribution"]["findings_count"] == 0

    def test_scenario_09_mixed_scenario(self, corpus_root: Path):
        res = validate_scenario_against_detectors(corpus_root / "scenarios/09_mixed_scenario")
        assert res["passed"] is True, f"Failures: {res['failures']}"
        dets = res["detector_results"]
        # All 5 detectors fire simultaneously in Scenario 09
        assert dets["di01_duplicates"]["findings_count"] > 0
        assert dets["di02_label_integrity"]["findings_count"] > 0
        assert dets["di03_trigger_anomaly"]["findings_count"] > 0
        assert dets["di04_ood_distribution"]["findings_count"] > 0
        assert dets["di05_contributor_risk"]["findings_count"] > 0


# ===========================================================================
# Test N: Real API E2E Assessment Execution
# ===========================================================================

class TestCorpusApiE2E:
    """Verify end-to-end execution of a real assessment via HTTP API upload."""

    def test_api_upload_and_assessment_e2e(self, api_client: TestClient, corpus_root: Path):
        zip_path = corpus_root / "scenarios/09_mixed_scenario/scenario_09_mixed_scenario.zip"
        assert zip_path.is_file(), f"Scenario 09 ZIP not found: {zip_path}"

        # 1. Upload ZIP via /api/v1/uploads
        with open(zip_path, "rb") as f:
            up_res = api_client.post(
                "/api/v1/uploads",
                files={"file": (zip_path.name, f.read(), "application/zip")},
                data={"asset_type": "dataset"},
            )
        assert up_res.status_code == 201, f"Upload failed: {up_res.text}"
        ds_asset_id = up_res.json()["asset_id"]
        assert ds_asset_id

        # 2. Run assessment referencing dataset_asset_id
        asmt_res = api_client.post(
            "/api/v1/assessments",
            json={
                "title": "E2E Corpus Scenario 09 Assessment",
                "dataset_asset_id": ds_asset_id,
            },
        )
        assert asmt_res.status_code == 201, f"Assessment failed: {asmt_res.text}"
        data = asmt_res.json()

        assert data["title"] == "E2E Corpus Scenario 09 Assessment"
        assert data["overall_risk"].upper() in ("HIGH", "CRITICAL")
        assert data["findings_count"] > 0

        # Check detector runs
        ran_detector_ids = {r["detector_id"] for r in data["detector_runs"] if r.get("ran")}
        assert any("di01" in did for did in ran_detector_ids)
        assert any("di02" in did for did in ran_detector_ids)
        assert any("di03" in did for did in ran_detector_ids)
        assert any("di04" in did for did in ran_detector_ids)
        assert any("di05" in did for did in ran_detector_ids)

        # 3. Fetch assessment by ID
        get_res = api_client.get(f"/api/v1/assessments/{data['assessment_id']}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["assessment_id"] == data["assessment_id"]
        assert get_data["findings_count"] == data["findings_count"]


# ===========================================================================
# Test O: Repeat Assessment Reproducibility
# ===========================================================================

class TestRepeatAssessmentReproducibility:
    """Verify that assessing the same dataset twice yields identical findings and risk."""

    def test_repeat_assessment_identical_findings(self, api_client: TestClient, corpus_root: Path):
        zip_path = corpus_root / "scenarios/01_clean_baseline/scenario_01_clean_baseline.zip"
        assert zip_path.is_file()

        with open(zip_path, "rb") as f:
            zip_bytes = f.read()

        # Run Assessment 1
        up1 = api_client.post(
            "/api/v1/uploads",
            files={"file": ("scen01_run1.zip", zip_bytes, "application/zip")},
            data={"asset_type": "dataset"},
        )
        assert up1.status_code == 201
        asmt1 = api_client.post(
            "/api/v1/assessments",
            json={"title": "Repeat Test Run 1", "dataset_asset_id": up1.json()["asset_id"]},
        )
        assert asmt1.status_code == 201
        data1 = asmt1.json()

        # Run Assessment 2
        up2 = api_client.post(
            "/api/v1/uploads",
            files={"file": ("scen01_run2.zip", zip_bytes, "application/zip")},
            data={"asset_type": "dataset"},
        )
        assert up2.status_code == 201
        asmt2 = api_client.post(
            "/api/v1/assessments",
            json={"title": "Repeat Test Run 2", "dataset_asset_id": up2.json()["asset_id"]},
        )
        assert asmt2.status_code == 201
        data2 = asmt2.json()

        assert data1["findings_count"] == data2["findings_count"] == 0
        assert data1["overall_risk"].upper() == data2["overall_risk"].upper() == "NONE"
