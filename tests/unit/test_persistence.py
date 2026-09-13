"""Tests for blob store and SQLite persistence layer."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

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
    AssessmentType,
    AssetType,
    AuditEventType,
    DatasetFormat,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    ModelFramework,
    RiskLevel,
    Severity,
)
from backend.infra.blob_store import BlobStore
from backend.infra.db import (
    AuditRepository,
    AssetRepository,
    AssessmentRepository,
    DatasetRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    ModelArtifactRepository,
    ProvenanceRepository,
    SampleRepository,
    open_db,
)
from backend.infra.crypto import hash_bytes


# ---------------------------------------------------------------------------
# Blob store tests
# ---------------------------------------------------------------------------

class TestBlobStore:
    def test_store_and_retrieve_bytes(self, blob_store: BlobStore):
        data = b"pramaan evidence bytes"
        sha256 = hash_bytes(data)
        blob_store.store_bytes(data, sha256)
        assert blob_store.retrieve(sha256) == data

    def test_exists_true_after_store(self, blob_store: BlobStore):
        data = b"hello"
        sha256 = hash_bytes(data)
        blob_store.store_bytes(data, sha256)
        assert blob_store.exists(sha256) is True

    def test_exists_false_before_store(self, blob_store: BlobStore):
        sha256 = hash_bytes(b"not stored")
        assert blob_store.exists(sha256) is False

    def test_retrieve_not_found_raises(self, blob_store: BlobStore):
        with pytest.raises(FileNotFoundError):
            blob_store.retrieve("a" * 64)

    def test_identical_content_stored_once(self, blob_store: BlobStore, tmp_path: Path):
        data = b"same content"
        sha256 = hash_bytes(data)
        path1 = blob_store.store_bytes(data, sha256)
        path2 = blob_store.store_bytes(data, sha256)
        assert path1 == path2

    def test_directory_sharding(self, blob_store: BlobStore):
        """Blobs are stored under <aa>/<bb>/<sha256> structure."""
        data = b"sharding test"
        sha256 = hash_bytes(data)
        blob_store.store_bytes(data, sha256)
        expected_path = blob_store.blob_path(sha256)
        assert expected_path.exists()
        parts = expected_path.parts
        # .../<aa>/<bb>/<sha256>
        assert parts[-3] == sha256[:2]
        assert parts[-2] == sha256[2:4]
        assert parts[-1] == sha256

    def test_store_file(self, blob_store: BlobStore, tmp_path: Path):
        data = b"file content"
        sha256 = hash_bytes(data)
        src = tmp_path / "source.bin"
        src.write_bytes(data)
        blob_store.store_file(src, sha256)
        assert blob_store.retrieve(sha256) == data

    def test_short_hash_raises(self, blob_store: BlobStore):
        with pytest.raises(ValueError):
            blob_store.blob_path("ab")  # Too short


# ---------------------------------------------------------------------------
# SQLite schema / open_db
# ---------------------------------------------------------------------------

class TestOpenDb:
    def test_opens_and_creates_tables(self, db: sqlite3.Connection):
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "assessments", "assets", "datasets", "samples",
            "model_artifacts", "findings", "evidence",
            "detector_results", "provenance_manifests", "audit_events",
        }
        assert expected.issubset(tables)

    def test_wal_mode(self, db: sqlite3.Connection):
        mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, db: sqlite3.Connection):
        fk = db.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1


# ---------------------------------------------------------------------------
# Assessment repository
# ---------------------------------------------------------------------------

def _make_assessment(**kwargs) -> Assessment:
    kwargs.setdefault("title", "Test")
    return Assessment(**kwargs)


class TestAssessmentRepository:
    def test_insert_and_get(self, db):
        repo = AssessmentRepository(db)
        a = _make_assessment()
        repo.insert(a)
        retrieved = repo.get(a.assessment_id)
        assert retrieved is not None
        assert retrieved.assessment_id == a.assessment_id
        assert retrieved.title == a.title
        assert retrieved.state == AssessmentState.CREATED

    def test_get_nonexistent(self, db):
        repo = AssessmentRepository(db)
        assert repo.get("nonexistent") is None

    def test_list_all(self, db):
        repo = AssessmentRepository(db)
        a1 = _make_assessment(title="A1")
        a2 = _make_assessment(title="A2")
        repo.insert(a1)
        repo.insert(a2)
        all_items = repo.list_all()
        ids = [x.assessment_id for x in all_items]
        assert a1.assessment_id in ids
        assert a2.assessment_id in ids

    def test_update_state_to_analyzing(self, db):
        repo = AssessmentRepository(db)
        a = _make_assessment()
        repo.insert(a)
        repo.update_state(a.assessment_id, AssessmentState.ANALYZING)
        updated = repo.get(a.assessment_id)
        assert updated.state == AssessmentState.ANALYZING
        assert updated.started_at is not None

    def test_update_state_to_complete(self, db):
        repo = AssessmentRepository(db)
        a = _make_assessment()
        repo.insert(a)
        repo.update_state(a.assessment_id, AssessmentState.COMPLETE)
        updated = repo.get(a.assessment_id)
        assert updated.state == AssessmentState.COMPLETE
        assert updated.completed_at is not None

    def test_update_state_to_failed_with_error(self, db):
        repo = AssessmentRepository(db)
        a = _make_assessment()
        repo.insert(a)
        repo.update_state(a.assessment_id, AssessmentState.FAILED, error="disk full")
        updated = repo.get(a.assessment_id)
        assert updated.state == AssessmentState.FAILED
        assert updated.error == "disk full"


# ---------------------------------------------------------------------------
# Asset repository
# ---------------------------------------------------------------------------

class TestAssetRepository:
    def _setup_assessment(self, db) -> str:
        a = _make_assessment()
        AssessmentRepository(db).insert(a)
        return a.assessment_id

    def test_insert_and_get(self, db):
        aid = self._setup_assessment(db)
        repo = AssetRepository(db)
        asset = Asset(
            assessment_id=aid,
            asset_type=AssetType.DATASET,
            name="test_dataset",
            sha256="a" * 64,
            size_bytes=1024,
        )
        repo.insert(asset)
        retrieved = repo.get(asset.asset_id)
        assert retrieved is not None
        assert retrieved.name == "test_dataset"

    def test_list_by_assessment(self, db):
        aid = self._setup_assessment(db)
        repo = AssetRepository(db)
        for i in range(3):
            repo.insert(Asset(
                assessment_id=aid,
                asset_type=AssetType.MODEL,
                name=f"model_{i}",
                sha256=f"{i:064d}",
                size_bytes=100,
            ))
        assets = repo.list_by_assessment(aid)
        assert len(assets) == 3


# ---------------------------------------------------------------------------
# Sample repository
# ---------------------------------------------------------------------------

class TestSampleRepository:
    def _setup(self, db):
        a = _make_assessment()
        AssessmentRepository(db).insert(a)
        asset = Asset(
            assessment_id=a.assessment_id,
            asset_type=AssetType.DATASET,
            name="ds",
            sha256="d" * 64,
            size_bytes=0,
        )
        AssetRepository(db).insert(asset)
        dataset = Dataset(
            dataset_id=asset.asset_id,
            assessment_id=a.assessment_id,
            format=DatasetFormat.IMAGE_DIR,
            source_path="/data/images",
            sample_count=0,
        )
        DatasetRepository(db).insert(dataset)
        return dataset.dataset_id

    def test_insert_many_and_list(self, db):
        dataset_id = self._setup(db)
        repo = SampleRepository(db)
        samples = [
            Sample(
                dataset_id=dataset_id,
                file_name=f"img{i:03d}.jpg",
                sha256=hash_bytes(f"image{i}".encode()),
                phash=f"{i:016x}",
                dhash=f"{i:016x}",
                width=224,
                height=224,
                file_size_bytes=50_000,
            )
            for i in range(5)
        ]
        repo.insert_many(samples)
        retrieved = repo.list_by_dataset(dataset_id)
        assert len(retrieved) == 5
        file_names = {s.file_name for s in retrieved}
        assert file_names == {f"img{i:03d}.jpg" for i in range(5)}

    def test_count_by_dataset(self, db):
        dataset_id = self._setup(db)
        repo = SampleRepository(db)
        samples = [
            Sample(
                dataset_id=dataset_id,
                file_name=f"img{i}.jpg",
                sha256=hash_bytes(f"cnt{i}".encode()),
                file_size_bytes=1000,
            )
            for i in range(7)
        ]
        repo.insert_many(samples)
        assert repo.count_by_dataset(dataset_id) == 7


# ---------------------------------------------------------------------------
# Finding & Evidence repositories
# ---------------------------------------------------------------------------

class TestFindingAndEvidenceRepository:
    def _setup(self, db):
        a = _make_assessment()
        AssessmentRepository(db).insert(a)
        asset = Asset(
            assessment_id=a.assessment_id,
            asset_type=AssetType.DATASET,
            name="ds",
            sha256="e" * 64,
            size_bytes=0,
        )
        AssetRepository(db).insert(asset)
        return a.assessment_id, asset.asset_id

    def test_insert_and_list_finding(self, db):
        aid, asid = self._setup(db)
        repo = FindingRepository(db)
        f = Finding(
            assessment_id=aid,
            asset_id=asid,
            category=FindingCategory.DATA_INTEGRITY,
            subcategory="duplicate",
            severity=Severity.MEDIUM,
            title="Near-duplicate cluster",
            description="Images X and Y have Hamming distance 3.",
            detection_method="pHash Duplicate Detector v1",
            detector_id="di.phash_duplicates",
        )
        repo.insert(f)
        findings = repo.list_by_assessment(aid)
        assert len(findings) == 1
        assert findings[0].finding_id == f.finding_id
        assert findings[0].source == "LIVE_ANALYSIS"

    def test_insert_and_list_evidence(self, db):
        aid, asid = self._setup(db)
        f = Finding(
            assessment_id=aid,
            asset_id=asid,
            category=FindingCategory.DATA_INTEGRITY,
            subcategory="duplicate",
            severity=Severity.LOW,
            title="Test finding",
            description="Test",
            detection_method="TestDetector",
            detector_id="test",
        )
        FindingRepository(db).insert(f)
        e = Evidence(
            finding_id=f.finding_id,
            detector_id="test",
            evidence_type=EvidenceType.MEASUREMENT,
            description="pHash Hamming distance = 3",
            data={"sample_a": "img1.jpg", "sample_b": "img2.jpg", "distance": 3},
        )
        EvidenceRepository(db).insert(e)
        evidence = EvidenceRepository(db).list_by_finding(f.finding_id)
        assert len(evidence) == 1
        assert evidence[0].data["distance"] == 3

    def test_finding_row_deserialization_case_insensitivity(self, db):
        aid, asid = self._setup(db)
        db.execute(
            """
            INSERT INTO findings
                (finding_id, assessment_id, asset_id, category, subcategory,
                 severity, title, description, detection_method, detector_id,
                 limitations_json, recommended_disposition, source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "test-uppercase-sev-id",
                aid,
                asid,
                "DATA_INTEGRITY",
                "duplicate",
                "HIGH",
                "Adversarial Trigger Finding",
                "Testing case insensitivity",
                "Method",
                "detector.id",
                "[]",
                "FLAG",
                "LIVE_ANALYSIS",
                "2026-09-10T13:00:00Z",
            ),
        )
        db.commit()
        findings = FindingRepository(db).list_by_assessment(aid)
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH
        assert findings[0].category == FindingCategory.DATA_INTEGRITY


# ---------------------------------------------------------------------------
# Audit repository
# ---------------------------------------------------------------------------

class TestAuditRepository:
    def test_initial_last_hash_is_genesis(self, db):
        repo = AuditRepository(db)
        assert repo.last_hash() == AuditRepository.GENESIS_HASH

    def test_append_and_list(self, db):
        repo = AuditRepository(db)
        prev = repo.last_hash()
        current = hash_bytes(f"{prev}event1".encode())
        event = AuditEvent(
            event_type=AuditEventType.GENESIS,
            timestamp_utc="2026-09-10T13:00:00Z",
            actor="system",
            payload_digest=hash_bytes(b"{}"),
            previous_hash=prev,
            current_hash=current,
        )
        repo.append(event)
        events = repo.list_all()
        assert len(events) == 1
        assert events[0].event_id == event.event_id

    def test_last_hash_updates_after_append(self, db):
        repo = AuditRepository(db)
        prev = repo.last_hash()
        current = hash_bytes(f"{prev}data".encode())
        event = AuditEvent(
            event_type=AuditEventType.ASSESSMENT_CREATED,
            timestamp_utc="2026-09-10T13:00:01Z",
            actor="system",
            payload_digest=hash_bytes(b"{}"),
            previous_hash=prev,
            current_hash=current,
        )
        repo.append(event)
        assert repo.last_hash() == current

    def test_no_delete_method_exists(self):
        """The AuditRepository must not expose DELETE capability."""
        repo = AuditRepository.__dict__
        assert "delete" not in repo
        assert "remove" not in repo
        assert "truncate" not in repo

    def test_no_update_method_exists(self):
        """The AuditRepository must not expose UPDATE capability."""
        repo = AuditRepository.__dict__
        assert "update" not in repo
