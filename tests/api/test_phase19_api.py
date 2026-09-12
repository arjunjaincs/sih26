"""
Tests for Phase 19 API enhancements:
- Canonical result persistence (GET /api/v1/assessments/{id} returns AssessmentResultSchema)
- History list summary metrics (overall_risk, overall_confidence, coverage_fraction)
- Provenance endpoint (GET /api/v1/assessments/{id}/provenance)
- Demo presets endpoint (GET /api/v1/demos)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_db
from backend.infra.db import open_db


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    return open_db(tmp_path / "phase19_test.db")


@pytest.fixture
def client(test_db: sqlite3.Connection) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: test_db
    return TestClient(app, raise_server_exceptions=False)


class TestCanonicalResultPersistence:
    def test_get_assessment_returns_full_result_schema(
        self, client: TestClient, onnx_model: Path
    ):
        """Verify that GET /assessments/{id} returns full AssessmentResultSchema."""
        create_res = client.post("/api/v1/assessments", json={
            "title": "Full Schema Test",
            "model_path": str(onnx_model),
        })
        assert create_res.status_code == 201
        created_data = create_res.json()
        assess_id = created_data["assessment_id"]

        get_res = client.get(f"/api/v1/assessments/{assess_id}")
        assert get_res.status_code == 200
        persisted_data = get_res.json()

        # Check all core fields that previously disappeared on refresh/history
        assert "overall_risk" in persisted_data
        assert persisted_data["overall_risk"] == created_data["overall_risk"]
        assert "overall_confidence" in persisted_data
        assert persisted_data["overall_confidence"] == created_data["overall_confidence"]
        assert "coverage_fraction" in persisted_data
        assert isinstance(persisted_data["coverage_fraction"], float)
        assert "detector_runs" in persisted_data
        assert len(persisted_data["detector_runs"]) > 0
        assert "coverage_gaps" in persisted_data
        assert "limitations" in persisted_data
        assert "findings_count" in persisted_data
        assert "evidence_count" in persisted_data
        assert persisted_data["status"] == "complete"

    def test_list_assessments_includes_metrics(
        self, client: TestClient, onnx_model: Path
    ):
        """Verify that GET /assessments items include overall_risk, overall_confidence, coverage_fraction."""
        client.post("/api/v1/assessments", json={
            "title": "History Metric Test",
            "model_path": str(onnx_model),
        })

        res = client.get("/api/v1/assessments")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        item = data["assessments"][0]
        assert "overall_risk" in item
        assert "overall_confidence" in item
        assert "coverage_fraction" in item
        assert item["overall_risk"] in ("none", "low", "medium", "high", "critical")

    def test_get_provenance_empty_manifest(
        self, client: TestClient, onnx_model: Path
    ):
        """Verify provenance endpoint returns has_provenance=False when no manifest provided."""
        create_res = client.post("/api/v1/assessments", json={
            "title": "No Provenance Test",
            "model_path": str(onnx_model),
        })
        assess_id = create_res.json()["assessment_id"]

        res = client.get(f"/api/v1/assessments/{assess_id}/provenance")
        assert res.status_code == 200
        data = res.json()
        assert data["assessment_id"] == assess_id
        assert data["has_provenance"] is False
        assert data["manifest"] is None

    def test_list_demos_endpoint(self, client: TestClient):
        """Verify GET /api/v1/demos returns valid presets pointing to existing files."""
        res = client.get("/api/v1/demos")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] > 0
        preset = data["demos"][0]
        assert "id" in preset
        assert "name" in preset
        assert "payload" in preset
        assert "expected_risk" in preset
        assert "expected_confidence" in preset
