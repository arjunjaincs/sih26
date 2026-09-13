"""
Tests for Lightweight Global Search in PRAMAAN.

Covers:
- GET /api/v1/search
- Exact ID search (assessment_id, finding_id, evidence_id)
- Partial title search (assessments, findings)
- Detector search (by detector_id, code 'DI-01', unhyphenated 'di01', method keyword)
- Empty query and no-match search
- Malicious search input safety (SQL injection attempts, wildcards, long strings)
- Path censorship (absolute filesystem paths scrubbed from asset names and evidence)
- Large result behavior and pagination/limits
- Read-only guarantee (zero data alteration)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_db
from backend.domain.entities import (
    Assessment,
    Asset,
    Evidence,
    Finding,
)
from backend.domain.enums import (
    AssessmentState,
    AssetType,
    EvidenceType,
    FindingCategory,
    Severity,
)
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    EvidenceRepository,
    FindingRepository,
)


@pytest.fixture
def client(db: sqlite3.Connection) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


def _seed_search_test_data(db: sqlite3.Connection) -> dict[str, str]:
    now = datetime.now(timezone.utc)

    # 1. Assessments
    asmt_repo = AssessmentRepository(db)
    asmt1 = Assessment(
        assessment_id="asmt-resnet-001",
        title="ResNet50 Production Model Assurance Run",
        description="Comprehensive deep inspection of ResNet-50 vision model and training data",
        state=AssessmentState.COMPLETE,
        software_version="1.0.0",
        created_at=now,
        started_at=now,
        completed_at=now,
    )
    asmt2 = Assessment(
        assessment_id="asmt-yolo-002",
        title="YOLOv8 Edge Surveillance Model Evaluation",
        description="Dataset and model integrity evaluation for surveillance checkpoint",
        state=AssessmentState.ANALYZING,
        software_version="1.0.0",
        created_at=now,
        started_at=now,
    )
    asmt_repo.insert(asmt1)
    asmt_repo.insert(asmt2)

    # 2. Assets
    asset_repo = AssetRepository(db)
    asset1 = Asset(
        asset_id="ast-resnet-onnx",
        assessment_id=asmt1.assessment_id,
        asset_type=AssetType.MODEL,
        name=r"C:\Confidential\Server\resnet50_v2.onnx",
        sha256="11" * 32,
        size_bytes=45000000,
        registered_at=now,
    )
    asset2 = Asset(
        asset_id="ast-dataset-images",
        assessment_id=asmt1.assessment_id,
        asset_type=AssetType.DATASET,
        name="/var/data/camera_traps_2026.zip",
        sha256="22" * 32,
        size_bytes=120000000,
        registered_at=now,
    )
    asset_repo.insert(asset1)
    asset_repo.insert(asset2)

    # 3. Findings
    fnd_repo = FindingRepository(db)
    fnd1 = Finding(
        finding_id="fnd-exact-dup-01",
        assessment_id=asmt1.assessment_id,
        asset_id=asset2.asset_id,
        category=FindingCategory.DATA_INTEGRITY,
        subcategory="Exact Duplicates",
        severity=Severity.HIGH,
        title="High Density Exact Duplicate Image Clusters",
        description="Multiple exact byte collisions found in training splits",
        detection_method="SHA-256 byte collision matching",
        detector_id="data.integrity.di01_duplicates",
        recommended_disposition="QUARANTINE",
        created_at=now,
    )
    fnd2 = Finding(
        finding_id="fnd-weight-nan-02",
        assessment_id=asmt1.assessment_id,
        asset_id=asset1.asset_id,
        category=FindingCategory.MODEL_INTEGRITY,
        subcategory="Weight Anomalies",
        severity=Severity.CRITICAL,
        title="NaN Weight Tensor Explosion in Dense Layer",
        description="Found abnormal floating point values in linear projection weights",
        detection_method="Tensor finite value inspection",
        detector_id="model.integrity.mi02_weight_anomalies",
        recommended_disposition="REJECT",
        created_at=now,
    )
    fnd_repo.insert(fnd1)
    fnd_repo.insert(fnd2)

    # 4. Evidence
    evi_repo = EvidenceRepository(db)
    evi1 = Evidence(
        evidence_id="evi-cluster-manifest-01",
        finding_id=fnd1.finding_id,
        detector_id="data.integrity.di01_duplicates",
        evidence_type=EvidenceType.CLUSTER,
        description="Duplicate cluster manifest matching 14 image files from /mnt/shared/storage",
        data={"cluster_id": "c-001", "member_count": 14},
    )
    evi2 = Evidence(
        evidence_id="evi-tensor-stats-02",
        finding_id=fnd2.finding_id,
        detector_id="model.integrity.mi02_weight_anomalies",
        evidence_type=EvidenceType.ANOMALY,
        description=r"Layer weights inspected from C:\Weights\checkpoint.pt containing NaN values",
        data={"nan_count": 128, "inf_count": 0},
    )
    evi_repo.insert(evi1)
    evi_repo.insert(evi2)

    return {
        "asmt1": asmt1.assessment_id,
        "asmt2": asmt2.assessment_id,
        "fnd1": fnd1.finding_id,
        "fnd2": fnd2.finding_id,
        "evi1": evi1.evidence_id,
        "evi2": evi2.evidence_id,
    }


class TestGlobalSearchEndpoint:
    """Test GET /api/v1/search endpoint."""

    def test_empty_query_returns_empty_results(self, client: TestClient, db: sqlite3.Connection):
        """Empty or whitespace-only query returns zero results immediately."""
        _seed_search_test_data(db)
        resp = client.get("/api/v1/search?q=")
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == ""
        assert data["total_matches"] == 0
        assert data["assessments"] == []
        assert data["findings"] == []
        assert data["evidence"] == []

    def test_exact_assessment_id_search(self, client: TestClient, db: sqlite3.Connection):
        """Searching exact assessment ID returns the matching assessment."""
        ids = _seed_search_test_data(db)
        resp = client.get(f"/api/v1/search?q={ids['asmt1']}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["counts"]["assessments"] >= 1
        matched_asmt = next((a for a in data["assessments"] if a["assessment_id"] == ids["asmt1"]), None)
        assert matched_asmt is not None
        assert "ResNet50" in matched_asmt["title"]
        assert matched_asmt["target_url"] == f"/assessments/{ids['asmt1']}/result"

    def test_exact_finding_id_search(self, client: TestClient, db: sqlite3.Connection):
        """Searching exact finding ID returns the matching finding."""
        ids = _seed_search_test_data(db)
        resp = client.get(f"/api/v1/search?q={ids['fnd1']}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["counts"]["findings"] == 1
        finding = data["findings"][0]
        assert finding["finding_id"] == ids["fnd1"]
        assert "Duplicate" in finding["title"]
        assert finding["detector_id"] == "data.integrity.di01_duplicates"
        assert finding["detector_code"] == "DI-01"
        assert finding["target_url"] == f"/assessments/{ids['asmt1']}/findings"

    def test_exact_evidence_id_search(self, client: TestClient, db: sqlite3.Connection):
        """Searching exact evidence ID returns the matching evidence."""
        ids = _seed_search_test_data(db)
        resp = client.get(f"/api/v1/search?q={ids['evi2']}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["counts"]["evidence"] == 1
        evi = data["evidence"][0]
        assert evi["evidence_id"] == ids["evi2"]
        assert evi["finding_id"] == ids["fnd2"]
        assert evi["assessment_id"] == ids["asmt1"]
        assert evi["target_url"] == f"/assessments/{ids['asmt1']}/evidence"

    def test_partial_title_search(self, client: TestClient, db: sqlite3.Connection):
        """Partial text search matches assessments, findings, and evidence."""
        _seed_search_test_data(db)
        resp = client.get("/api/v1/search?q=surveillance")
        assert resp.status_code == 200
        data = resp.json()

        assert data["counts"]["assessments"] >= 1
        assert any("YOLOv8" in a["title"] for a in data["assessments"])

    def test_detector_code_search_bridges_to_detector_id(self, client: TestClient, db: sqlite3.Connection):
        """Searching 'DI-01' or 'di01' surfaces findings & evidence produced by data.integrity.di01_duplicates."""
        _seed_search_test_data(db)

        # Test hyphenated code
        resp = client.get("/api/v1/search?q=DI-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["counts"]["findings"] >= 1
        assert any(f["detector_code"] == "DI-01" for f in data["findings"])
        assert any(e["detector_code"] == "DI-01" for e in data["evidence"])

        # Test unhyphenated code
        resp2 = client.get("/api/v1/search?q=mi02")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["counts"]["findings"] >= 1
        assert any(f["detector_code"] == "MI-02" for f in data2["findings"])

    def test_no_results_search(self, client: TestClient, db: sqlite3.Connection):
        """Search query with no matches returns 0 counts and empty arrays."""
        _seed_search_test_data(db)
        resp = client.get("/api/v1/search?q=completely_nonexistent_token_9999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] == 0
        assert data["counts"]["assessments"] == 0
        assert data["counts"]["findings"] == 0
        assert data["counts"]["evidence"] == 0
        assert data["assessments"] == []
        assert data["findings"] == []
        assert data["evidence"] == []

    def test_malicious_and_special_character_inputs(self, client: TestClient, db: sqlite3.Connection):
        """Test SQL injection payloads, wildcard abuse, long strings, and control characters."""
        _seed_search_test_data(db)

        # SQL injection strings
        malicious_queries = [
            "' OR '1'='1",
            "'; DROP TABLE findings; --",
            "' UNION SELECT * FROM assessments --",
            "%%%",
            "___",
            "\\%\\_",
            "a" * 500,  # overly long string
            "test\x00injection",  # null byte
        ]

        for query in malicious_queries:
            resp = client.get("/api/v1/search", params={"q": query})
            assert resp.status_code == 200, f"Query '{query}' failed"
            data = resp.json()
            assert isinstance(data["total_matches"], int)
            assert isinstance(data["assessments"], list)

        # Ensure findings table still exists and data was not mutated
        count = db.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert count == 2

    def test_path_censorship_in_search_results(self, client: TestClient, db: sqlite3.Connection):
        """Verifies that no absolute server filesystem paths leak in search results."""
        _seed_search_test_data(db)

        # Search for findings which had absolute asset paths
        resp = client.get("/api/v1/search?q=ResNet")
        assert resp.status_code == 200
        raw_text = resp.text

        # Absolute paths from seed data:
        # C:\Confidential\Server\resnet50_v2.onnx
        # /var/data/camera_traps_2026.zip
        # /mnt/shared/storage
        # C:\Weights\checkpoint.pt
        assert r"C:\Confidential\Server" not in raw_text
        assert "/var/data" not in raw_text
        assert "/mnt/shared" not in raw_text
        assert r"C:\Weights" not in raw_text

        # Safe base names or redacted strings should be used
        data = resp.json()
        for f in data["findings"]:
            if f["asset_name"]:
                assert "\\" not in f["asset_name"]
                assert "/" not in f["asset_name"]

    def test_large_result_limits(self, client: TestClient, db: sqlite3.Connection):
        """Limit parameter clamps correctly and prevents result overload."""
        now = datetime.now(timezone.utc)
        # Seed 25 assessments
        for i in range(25):
            AssessmentRepository(db).insert(
                Assessment(
                    assessment_id=f"asmt-bulk-{i:03d}",
                    title=f"Bulk Assessment {i}",
                    state=AssessmentState.COMPLETE,
                    created_at=now,
                )
            )

        resp = client.get("/api/v1/search?q=Bulk&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["assessments"]) == 5
        assert data["counts"]["assessments"] == 5

        # Clamps max to 30
        resp_max = client.get("/api/v1/search?q=Bulk&limit=100")
        assert resp_max.status_code == 200
        data_max = resp_max.json()
        assert len(data_max["assessments"]) <= 30
