"""
API route tests for PRAMAAN Cloud AI Copilot endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from backend.ai.fake_provider import MockAIProvider
from backend.ai.service import ai_service
from backend.api.app import create_app
from pathlib import Path
from backend.domain.entities import Assessment, Asset, Evidence, Finding
from backend.domain.enums import (
    AssetType,
    AssessmentState,
    EvidenceType,
    FindingCategory,
    Severity,
)
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    EvidenceRepository,
    FindingRepository,
    open_db,
)


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_pramaan.db"
    monkeypatch.setenv("PRAMAAN_DB_PATH", str(db_path))
    monkeypatch.setenv("PRAMAAN_AI_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    app = create_app()
    with TestClient(app) as client:
        yield client, db_path


def _seed_assessment(db_path: Path | str) -> tuple[str, str]:
    conn = open_db(Path(db_path))
    with conn:
        asmt_id = "asmt-api-ai-001"
        AssessmentRepository(conn).insert(Assessment(
            assessment_id=asmt_id,
            title="API Test Assessment",
            state=AssessmentState.COMPLETE,
            software_version="1.0.0",
        ))
        AssetRepository(conn).insert(Asset(
            asset_id="asset-1",
            assessment_id=asmt_id,
            asset_type=AssetType.DATASET,
            name="test_data",
            sha256="abc",
            size_bytes=100,
        ))
        f = Finding(
            finding_id="f-api-01",
            assessment_id=asmt_id,
            asset_id="asset-1",
            category=FindingCategory.DATA_INTEGRITY,
            subcategory="exact_duplicates",
            severity=Severity.HIGH,
            title="Duplicate Sample Ingestion",
            description="Two duplicate items detected.",
            detection_method="PI-01 Exact Duplicate Detector",
            detector_id="PI-01",
            limitations=[],
            recommended_disposition="Prune duplicates",
        )
        FindingRepository(conn).insert(f)
        EvidenceRepository(conn).insert(Evidence(
            evidence_id="ev-api-01",
            finding_id="f-api-01",
            detector_id="PI-01",
            evidence_type=EvidenceType.MEASUREMENT,
            description="Duplicate record match",
            data={"match": True},
        ))
        return asmt_id, f.finding_id


def test_get_ai_status_never_returns_key(app_client):
    client, _ = app_client
    resp = client.get("/api/v1/ai/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "model" in data
    assert "status" in data
    assert "has_api_key" in data
    assert "privacy_disclosure" in data
    # Guarantee no key is exposed
    assert "api_key" not in data
    assert "key" not in data


def test_get_ai_models(app_client):
    client, _ = app_client
    resp = client.get("/api/v1/ai/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert isinstance(data["models"], list)
    assert len(data["models"]) > 0
    assert "current_model" in data


def test_test_ai_connection_unconfigured(app_client):
    client, _ = app_client
    resp = client.post("/api/v1/ai/test")
    assert resp.status_code == 200
    data = resp.json()
    assert "ok" in data
    assert "message" in data


def test_chat_ai_not_configured_returns_503(app_client):
    client, db_path = app_client
    asmt_id, _ = _seed_assessment(str(db_path))

    # Real openrouter provider without key is unconfigured
    mock_provider = MockAIProvider(configured=False)
    ai_service.set_provider(mock_provider)

    resp = client.post(
        f"/api/v1/assessments/{asmt_id}/ai/chat",
        json={"message": "Summarize assessment", "scope": "assessment"},
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]["message"].lower()


def test_chat_successful_with_mock_provider(app_client):
    client, db_path = app_client
    asmt_id, finding_id = _seed_assessment(str(db_path))

    mock_provider = MockAIProvider(
        configured=True,
        canned_response="Finding f-api-01 indicates sample redundancy. Evidence EV-01 confirms this.",
    )
    ai_service.set_provider(mock_provider)

    resp = client.post(
        f"/api/v1/assessments/{asmt_id}/ai/chat",
        json={
            "message": "Why is this finding high?",
            "scope": "finding",
            "finding_id": finding_id,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "mock"
    assert data["scope"] == "finding"
    assert data["grounded"] is True
    assert "Finding f-api-01" in data["answer"]
    assert any(s["id"] == finding_id for s in data["sources"])


def test_explain_finding_endpoint(app_client):
    client, db_path = app_client
    asmt_id, finding_id = _seed_assessment(str(db_path))

    mock_provider = MockAIProvider(
        configured=True,
        canned_response="Detailed explanation of finding f-api-01 with recommended remediation.",
    )
    ai_service.set_provider(mock_provider)

    resp = client.post(
        f"/api/v1/assessments/{asmt_id}/findings/{finding_id}/ai/explain",
        json={"user_query": "Explain this in plain language"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "finding"
    assert "Detailed explanation" in data["answer"]


def test_chat_timeout_returns_504(app_client):
    client, db_path = app_client
    asmt_id, _ = _seed_assessment(str(db_path))

    mock_provider = MockAIProvider(configured=True)
    mock_provider.should_timeout = True
    ai_service.set_provider(mock_provider)

    resp = client.post(
        f"/api/v1/assessments/{asmt_id}/ai/chat",
        json={"message": "Summarize", "scope": "assessment"},
    )
    assert resp.status_code == 504
    assert "timed out" in resp.json()["detail"]["message"].lower()


def test_chat_provider_error_returns_502(app_client):
    client, db_path = app_client
    asmt_id, _ = _seed_assessment(str(db_path))

    mock_provider = MockAIProvider(configured=True)
    mock_provider.should_error = True
    mock_provider.error_message = "OpenRouter upstream HTTP 500 internal error"
    ai_service.set_provider(mock_provider)

    resp = client.post(
        f"/api/v1/assessments/{asmt_id}/ai/chat",
        json={"message": "Summarize", "scope": "assessment"},
    )
    assert resp.status_code == 502
    assert "upstream" in resp.json()["detail"]["message"].lower()
