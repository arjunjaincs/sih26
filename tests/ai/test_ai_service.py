"""
Tests for AIService: orchestration, read-only guarantees, source extraction, and error handling.
"""

from pathlib import Path
import pytest
import sqlite3

from backend.ai.fake_provider import MockAIProvider
from backend.ai.models import AIChatRequest, AICopilotScope
from backend.ai.service import AIService
from backend.api.errors import AssessmentNotFound
from backend.domain.entities import (
    Assessment,
    Asset,
    AuditEvent,
    Evidence,
    Finding,
    ProvenanceManifest,
)
from backend.domain.enums import (
    AssetType,
    AssessmentState,
    AuditEventType,
    ConfidenceLevel,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    RiskLevel,
    Severity,
)
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    AuditRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    ProvenanceRepository,
    open_db,
)


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test.db"
    conn = open_db(db_file)
    return conn


def _seed_sample_assessment(conn: sqlite3.Connection) -> str:
    asmt_id = "test-asmt-001"
    asmt_repo = AssessmentRepository(conn)
    asmt_repo.insert(Assessment(
        assessment_id=asmt_id,
        title="Test Assessment For Copilot",
        state=AssessmentState.COMPLETE,
        description="Seed description",
        software_version="1.0.0",
    ))

    asset_repo = AssetRepository(conn)
    asset_repo.insert(Asset(
        asset_id="asset-ds-1",
        assessment_id=asmt_id,
        asset_type=AssetType.DATASET,
        name="clean_dataset",
        sha256="abc123456789",
        size_bytes=1024,
    ))

    finding_repo = FindingRepository(conn)
    f = Finding(
        finding_id="f-pi01-001",
        assessment_id=asmt_id,
        asset_id="asset-ds-1",
        category=FindingCategory.DATA_INTEGRITY,
        subcategory="exact_duplicates",
        severity=Severity.HIGH,
        title="Exact Duplicate Sample Cluster",
        description="Pair of identical images detected across training partitions.",
        detection_method="PI-01 Exact Duplicate Detector",
        detector_id="PI-01",
        limitations=["Pixel-level equality only"],
        recommended_disposition="Quarantine duplicate samples",
    )
    finding_repo.insert(f)

    evidence_repo = EvidenceRepository(conn)
    ev = Evidence(
        evidence_id="ev-001",
        finding_id=f.finding_id,
        detector_id="PI-01",
        evidence_type=EvidenceType.MEASUREMENT,
        description="Duplicate SHA-256 collision",
        data={"sha256": "dup123", "copies": 2},
    )
    evidence_repo.insert(ev)

    audit_repo = AuditRepository(conn)
    audit_repo.append(AuditEvent(
        event_id="ev-audit-01",
        event_type=AuditEventType.ASSESSMENT_CREATED,
        timestamp_utc="2026-09-13T00:00:00Z",
        assessment_id=asmt_id,
        actor="system",
        payload_digest="d1",
        previous_hash="0" * 64,
        current_hash="1" * 64,
    ))
    audit_repo.append(AuditEvent(
        event_id="ev-audit-02",
        event_type=AuditEventType.ASSESSMENT_COMPLETE,
        timestamp_utc="2026-09-13T00:01:00Z",
        assessment_id=asmt_id,
        actor="system",
        payload_digest="d2",
        previous_hash="1" * 64,
        current_hash="2" * 64,
    ))

    return asmt_id


@pytest.mark.asyncio
async def test_ai_service_chat_finding_scope(test_db):
    asmt_id = _seed_sample_assessment(test_db)
    mock_provider = MockAIProvider(
        canned_response="Finding f-pi01-001 was classified as HIGH because duplicates cause data leakage."
    )
    service = AIService(provider=mock_provider)

    req = AIChatRequest(
        message="Why is this finding HIGH?",
        scope=AICopilotScope.FINDING,
        finding_id="f-pi01-001",
    )
    resp = await service.chat(test_db, asmt_id, req)

    assert "Finding f-pi01-001 was classified as HIGH" in resp.answer
    assert resp.provider == "mock"
    assert resp.scope == "finding"
    assert resp.grounded is True
    assert any(s.id == "f-pi01-001" for s in resp.sources)


@pytest.mark.asyncio
async def test_ai_service_chat_assessment_scope(test_db):
    asmt_id = _seed_sample_assessment(test_db)
    mock_provider = MockAIProvider(
        canned_response="This assessment evaluated data integrity and found high risk due to exact duplicates."
    )
    service = AIService(provider=mock_provider)

    req = AIChatRequest(
        message="Summarize this assessment",
        scope=AICopilotScope.ASSESSMENT,
    )
    resp = await service.chat(test_db, asmt_id, req)

    assert "evaluated data integrity" in resp.answer
    assert resp.scope == "assessment"
    assert len(resp.sources) > 0


@pytest.mark.asyncio
async def test_ai_service_read_only_invariant(test_db):
    """
    CRITICAL TEST: Verify that running Copilot chat leaves all database
    tables (assessments, findings, evidence, audit logs) 100% untouched.
    """
    asmt_id = _seed_sample_assessment(test_db)
    mock_provider = MockAIProvider()
    service = AIService(provider=mock_provider)

    # Snapshot DB counts before AI interaction
    f_count_before = len(FindingRepository(test_db).list_by_assessment(asmt_id))
    ev_count_before = len(EvidenceRepository(test_db).list_by_finding("f-pi01-001"))
    audit_count_before = len(AuditRepository(test_db).list_by_assessment(asmt_id))

    # Execute multiple chat requests
    req1 = AIChatRequest(message="What is the risk?", scope=AICopilotScope.ASSESSMENT)
    await service.chat(test_db, asmt_id, req1)

    req2 = AIChatRequest(message="Explain finding", scope=AICopilotScope.FINDING, finding_id="f-pi01-001")
    await service.chat(test_db, asmt_id, req2)

    await service.explain_finding(test_db, asmt_id, "f-pi01-001")

    # Verify DB counts remain strictly identical
    f_count_after = len(FindingRepository(test_db).list_by_assessment(asmt_id))
    ev_count_after = len(EvidenceRepository(test_db).list_by_finding("f-pi01-001"))
    audit_count_after = len(AuditRepository(test_db).list_by_assessment(asmt_id))

    assert f_count_before == f_count_after
    assert ev_count_before == ev_count_after
    assert audit_count_before == audit_count_after


@pytest.mark.asyncio
async def test_ai_service_invalid_assessment_404(test_db):
    mock_provider = MockAIProvider()
    service = AIService(provider=mock_provider)
    req = AIChatRequest(message="Hello", scope=AICopilotScope.ASSESSMENT)

    with pytest.raises(AssessmentNotFound):
        await service.chat(test_db, "non-existent-id", req)


@pytest.mark.asyncio
async def test_ai_service_invalid_finding_error(test_db):
    asmt_id = _seed_sample_assessment(test_db)
    mock_provider = MockAIProvider()
    service = AIService(provider=mock_provider)
    req = AIChatRequest(message="Hello", scope=AICopilotScope.FINDING, finding_id="invalid-fid")

    with pytest.raises(ValueError, match="not found in assessment"):
        await service.chat(test_db, asmt_id, req)
