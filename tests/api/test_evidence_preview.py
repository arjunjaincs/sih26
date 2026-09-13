"""
Tests for Evidence Preview API endpoints.

Covers:
- GET /api/v1/assessments/{assessment_id}/evidence/{evidence_id}/preview
- GET /api/v1/assessments/{assessment_id}/evidence/{evidence_id}/artifact-file
- GET /api/v1/assessments/{assessment_id}/evidence/{evidence_id}/samples/{sample_id}/preview-file
- Content-type sniffing defense (nosniff header, magic byte validation)
- Path traversal defense (403 on path escape)
- Size limits (10MB image limit, 64KB text truncation)
- Cross-assessment isolation (404 on mismatched IDs)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_blob_store, get_db
from backend.domain.entities import (
    Assessment,
    Asset,
    Dataset,
    Evidence,
    Finding,
    Sample,
)
from backend.domain.enums import (
    AssetType,
    AssessmentState,
    DatasetFormat,
    EvidenceType,
    FindingCategory,
    Severity,
)
from backend.infra.blob_store import BlobStore
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    DatasetRepository,
    EvidenceRepository,
    FindingRepository,
    SampleRepository,
)


@pytest.fixture
def blob_store(tmp_path: Path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")


@pytest.fixture
def configured_client(db: sqlite3.Connection, blob_store: BlobStore) -> TestClient:
    from backend.api.app import create_app
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_blob_store] = lambda: blob_store
    return TestClient(app, raise_server_exceptions=False)


def _seed_assessment(db: sqlite3.Connection, assessment_id: str = "asm-prev-01") -> Assessment:
    repo = AssessmentRepository(db)
    asm = Assessment(
        assessment_id=assessment_id,
        title="Preview Test Assessment",
        state=AssessmentState.COMPLETE,
    )
    repo.insert(asm)
    return asm


def _seed_asset(
    db: sqlite3.Connection,
    assessment_id: str,
    asset_id: str = "asset-dummy-01",
    asset_type: AssetType = AssetType.DATASET,
) -> Asset:
    repo = AssetRepository(db)
    asset = Asset(
        asset_id=asset_id,
        assessment_id=assessment_id,
        asset_type=asset_type,
        name="test_asset",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        size_bytes=1024,
    )
    repo.insert(asset)
    return asset


def _seed_finding(
    db: sqlite3.Connection,
    assessment_id: str,
    asset_id: str = "asset-dummy-01",
    finding_id: str = "fnd-prev-01",
    detector_id: str = "DI-01",
) -> Finding:
    repo = FindingRepository(db)
    finding = Finding(
        finding_id=finding_id,
        assessment_id=assessment_id,
        asset_id=asset_id,
        category=FindingCategory.DATA_INTEGRITY,
        subcategory="duplicates",
        severity=Severity.HIGH,
        title="Duplicate Image Cluster",
        description="Duplicate images found",
        detection_method="Perceptual Hash",
        detector_id=detector_id,
    )
    repo.insert(finding)
    return finding


class TestEvidencePreview:
    """Test safe evidence preview generation and streaming."""

    def test_image_cluster_preview_and_file_streaming(
        self,
        db: sqlite3.Connection,
        configured_client: TestClient,
        image_dir_with_duplicates: Path,
    ):
        """Image duplicate evidence resolves to image_cluster preview and streams image safely."""
        asm = _seed_assessment(db, "asm-img-01")
        _seed_asset(db, asm.assessment_id, "ds-img-01", AssetType.DATASET)
        finding = _seed_finding(db, asm.assessment_id, "ds-img-01", "fnd-img-01", "DI-01")

        # Create dataset and samples
        ds_repo = DatasetRepository(db)
        sample_repo = SampleRepository(db)

        ds = Dataset(
            dataset_id="ds-img-01",
            assessment_id=asm.assessment_id,
            format=DatasetFormat.IMAGE_DIR,
            source_path=str(image_dir_with_duplicates),
            sample_count=2,
        )
        ds_repo.insert(ds)

        file1 = image_dir_with_duplicates / "original.jpg"
        file2 = image_dir_with_duplicates / "duplicate.jpg"

        s1 = Sample(
            sample_id="s-01",
            dataset_id=ds.dataset_id,
            file_name="original.jpg",
            file_size_bytes=file1.stat().st_size,
            sha256=hashlib.sha256(file1.read_bytes()).hexdigest(),
            width=64,
            height=64,
        )
        s2 = Sample(
            sample_id="s-02",
            dataset_id=ds.dataset_id,
            file_name="duplicate.jpg",
            file_size_bytes=file2.stat().st_size,
            sha256=hashlib.sha256(file2.read_bytes()).hexdigest(),
            width=64,
            height=64,
        )
        sample_repo.insert(s1)
        sample_repo.insert(s2)

        ev_repo = EvidenceRepository(db)
        ev = Evidence(
            evidence_id="ev-img-01",
            finding_id=finding.finding_id,
            detector_id="DI-01",
            evidence_type=EvidenceType.CLUSTER,
            description="Duplicate pair detected",
            data={
                "cluster_id": 1,
                "sample_ids": ["s-01", "s-02"],
                "file_names": ["original.jpg", "duplicate.jpg"],
            },
        )
        ev_repo.insert(ev)

        # 1. Fetch preview metadata
        res = configured_client.get(f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/preview")
        assert res.status_code == 200
        body = res.json()
        assert body["evidence_id"] == "ev-img-01"
        assert body["preview_type"] == "image_cluster"
        assert len(body["images"]) == 2
        assert body["images"][0]["file_name"] == "original.jpg"
        assert body["images"][0]["sha256"] == s1.sha256
        assert body["images"][0]["preview_url"].startswith(f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/samples/")

        # Verify no server absolute paths leaked
        raw_json_str = json.dumps(body)
        assert str(image_dir_with_duplicates) not in raw_json_str

        # 2. Stream image preview file
        stream_url = body["images"][0]["preview_url"]
        file_res = configured_client.get(stream_url)
        assert file_res.status_code == 200
        assert file_res.headers["content-type"] == "image/jpeg"
        assert file_res.headers["x-content-type-options"] == "nosniff"
        assert file_res.headers["content-security-policy"] == "default-src 'none'"
        assert file_res.content == file1.read_bytes()

    def test_json_blob_artifact_preview(
        self,
        db: sqlite3.Connection,
        configured_client: TestClient,
        blob_store: BlobStore,
    ):
        """BlobStore JSON artifact preview generates structured json and streams artifact safely."""
        asm = _seed_assessment(db, "asm-json-01")
        _seed_asset(db, asm.assessment_id, "asset-json-01")
        finding = _seed_finding(db, asm.assessment_id, "asset-json-01", "fnd-json-01", "PR-01")

        payload = {"pipeline": "yolo_inference", "confidence_threshold": 0.85, "frames_analyzed": 120}
        raw_bytes = json.dumps(payload).encode("utf-8")
        blob_sha = hashlib.sha256(raw_bytes).hexdigest()
        blob_store.store_bytes(raw_bytes, blob_sha)

        ev_repo = EvidenceRepository(db)
        ev = Evidence(
            evidence_id="ev-json-01",
            finding_id=finding.finding_id,
            detector_id="PR-01",
            evidence_type=EvidenceType.MEASUREMENT,
            description="Provenance configuration dump",
            artifact_sha256=blob_sha,
            data={"summary": "Inference run configuration"},
        )
        ev_repo.insert(ev)

        # 1. Fetch preview
        res = configured_client.get(f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/preview")
        assert res.status_code == 200
        body = res.json()
        assert body["preview_type"] == "json"
        assert body["mime_type"] == "application/json"
        assert body["structured_content"]["pipeline"] == "yolo_inference"
        assert body["text_content"] is not None

        # 2. Stream artifact file
        file_res = configured_client.get(f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/artifact-file")
        assert file_res.status_code == 200
        assert "charset=utf-8" in file_res.headers["content-type"]
        assert file_res.headers["x-content-type-options"] == "nosniff"
        assert file_res.content == raw_bytes

    def test_unsupported_binary_artifact_preview(
        self,
        db: sqlite3.Connection,
        configured_client: TestClient,
        blob_store: BlobStore,
    ):
        """Binary model weights (.onnx / .pt) return clean unsupported card and refuse stream."""
        asm = _seed_assessment(db, "asm-bin-01")
        _seed_asset(db, asm.assessment_id, "asset-bin-01", AssetType.MODEL)
        finding = _seed_finding(db, asm.assessment_id, "asset-bin-01", "fnd-bin-01", "MI-01")

        # Binary content that is not UTF-8 and not image magic bytes
        raw_bin = b"\x08\x03\x12\x05model\x1a\x02\x08\x01\xff\xfe\xaa\xbb\xcc\xdd\x00\x01"
        blob_sha = hashlib.sha256(raw_bin).hexdigest()
        blob_store.store_bytes(raw_bin, blob_sha)

        ev_repo = EvidenceRepository(db)
        ev = Evidence(
            evidence_id="ev-bin-01",
            finding_id=finding.finding_id,
            detector_id="MI-01",
            evidence_type=EvidenceType.MEASUREMENT,
            description="Binary weights layer inspection",
            artifact_sha256=blob_sha,
            data={"num_layers": 12, "weights_format": "ONNX"},
        )
        ev_repo.insert(ev)

        res = configured_client.get(f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/preview")
        assert res.status_code == 200
        body = res.json()
        assert body["preview_type"] == "unsupported"
        assert "cannot be previewed inline" in body["unsupported_reason"]
        assert body["structured_content"] == {"num_layers": 12, "weights_format": "ONNX"}

        # Attempting to stream binary file should return 422
        stream_res = configured_client.get(f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/artifact-file")
        assert stream_res.status_code == 422
        assert stream_res.json()["detail"]["error"] == "unsupported_preview_format"

    def test_text_artifact_bounded_truncation(
        self,
        db: sqlite3.Connection,
        configured_client: TestClient,
        blob_store: BlobStore,
    ):
        """Large text artifacts (> 64KB) are cleanly truncated in preview metadata."""
        asm = _seed_assessment(db, "asm-txt-01")
        _seed_asset(db, asm.assessment_id, "asset-txt-01")
        finding = _seed_finding(db, asm.assessment_id, "asset-txt-01", "fnd-txt-01", "AUD-01")

        large_text = "LOG LINE: Normal system telemetry event\n" * 2000  # ~80KB
        raw_bytes = large_text.encode("utf-8")
        blob_sha = hashlib.sha256(raw_bytes).hexdigest()
        blob_store.store_bytes(raw_bytes, blob_sha)

        ev_repo = EvidenceRepository(db)
        ev = Evidence(
            evidence_id="ev-txt-01",
            finding_id=finding.finding_id,
            detector_id="AUD-01",
            evidence_type=EvidenceType.MEASUREMENT,
            description="Large execution log dump",
            artifact_sha256=blob_sha,
            data={},
        )
        ev_repo.insert(ev)

        res = configured_client.get(f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/preview")
        assert res.status_code == 200
        body = res.json()
        assert body["preview_type"] == "structured_text"
        assert body["truncated"] is True
        assert len(body["text_content"]) == 65536

    def test_path_traversal_protection(
        self,
        db: sqlite3.Connection,
        configured_client: TestClient,
        tmp_path: Path,
    ):
        """Malicious sample filename attempting path traversal is rejected with 403."""
        asm = _seed_assessment(db, "asm-trav-01")
        _seed_asset(db, asm.assessment_id, "ds-trav-01", AssetType.DATASET)
        finding = _seed_finding(db, asm.assessment_id, "ds-trav-01", "fnd-trav-01", "DI-01")

        ds_dir = tmp_path / "valid_ds"
        ds_dir.mkdir()

        ds_repo = DatasetRepository(db)
        ds = Dataset(
            dataset_id="ds-trav-01",
            assessment_id=asm.assessment_id,
            format=DatasetFormat.IMAGE_DIR,
            source_path=str(ds_dir),
            sample_count=1,
        )
        ds_repo.insert(ds)

        # Craft malicious sample with path traversal in file_name
        sample_repo = SampleRepository(db)
        evil_sample = Sample(
            sample_id="s-evil-01",
            dataset_id=ds.dataset_id,
            file_name="../../secret.png",
            file_size_bytes=128,
            sha256="abc",
        )
        sample_repo.insert(evil_sample)

        ev_repo = EvidenceRepository(db)
        ev = Evidence(
            evidence_id="ev-trav-01",
            finding_id=finding.finding_id,
            detector_id="DI-01",
            evidence_type=EvidenceType.ANOMALY,
            description="Traversal attempt",
            data={"sample_ids": ["s-evil-01"]},
        )
        ev_repo.insert(ev)

        # 1. Preview resolution does not include the malicious sample
        prev_res = configured_client.get(f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/preview")
        assert prev_res.status_code == 200
        assert prev_res.json()["images"] == []  # Filtered out safely

        # 2. Direct file stream attempt returns 403 Forbidden
        file_res = configured_client.get(
            f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/samples/{evil_sample.sample_id}/preview-file"
        )
        assert file_res.status_code == 403
        assert file_res.json()["detail"]["error"] == "path_traversal"

    def test_cross_assessment_isolation(
        self,
        db: sqlite3.Connection,
        configured_client: TestClient,
    ):
        """Evidence from Assessment A cannot be accessed under Assessment B."""
        asm1 = _seed_assessment(db, "asm-iso-01")
        asm2 = _seed_assessment(db, "asm-iso-02")
        _seed_asset(db, asm1.assessment_id, "asset-iso-01")
        finding1 = _seed_finding(db, asm1.assessment_id, "asset-iso-01", "fnd-iso-01")

        ev_repo = EvidenceRepository(db)
        ev1 = Evidence(
            evidence_id="ev-iso-01",
            finding_id=finding1.finding_id,
            detector_id="DI-01",
            evidence_type=EvidenceType.CLUSTER,
            description="Isolated evidence",
            data={},
        )
        ev_repo.insert(ev1)

        # Accessing ev1 under asm2 must return 404
        res = configured_client.get(f"/api/v1/assessments/{asm2.assessment_id}/evidence/{ev1.evidence_id}/preview")
        assert res.status_code == 404
        assert res.json()["detail"]["error"] == "evidence_not_found"

    def test_unreferenced_sample_access_denied(
        self,
        db: sqlite3.Connection,
        configured_client: TestClient,
        image_dir_with_duplicates: Path,
    ):
        """Requesting sample file that is not part of the evidence data is rejected with 404."""
        asm = _seed_assessment(db, "asm-unref-01")
        _seed_asset(db, asm.assessment_id, "ds-unref-01", AssetType.DATASET)
        finding = _seed_finding(db, asm.assessment_id, "ds-unref-01", "fnd-unref-01")

        ds_repo = DatasetRepository(db)
        sample_repo = SampleRepository(db)
        ds = Dataset(
            dataset_id="ds-unref-01",
            assessment_id=asm.assessment_id,
            format=DatasetFormat.IMAGE_DIR,
            source_path=str(image_dir_with_duplicates),
            sample_count=1,
        )
        ds_repo.insert(ds)

        file1 = image_dir_with_duplicates / "original.jpg"
        s_target = Sample(
            sample_id="s-unref-01",
            dataset_id=ds.dataset_id,
            file_name="original.jpg",
            file_size_bytes=file1.stat().st_size,
            sha256="abc",
        )
        sample_repo.insert(s_target)

        # Evidence only references s-other-99
        ev_repo = EvidenceRepository(db)
        ev = Evidence(
            evidence_id="ev-unref-01",
            finding_id=finding.finding_id,
            detector_id="DI-01",
            evidence_type=EvidenceType.ANOMALY,
            description="Unref evidence",
            data={"sample_ids": ["s-other-99"]},
        )
        ev_repo.insert(ev)

        res = configured_client.get(
            f"/api/v1/assessments/{asm.assessment_id}/evidence/{ev.evidence_id}/samples/{s_target.sample_id}/preview-file"
        )
        assert res.status_code == 404
        assert res.json()["detail"]["error"] == "sample_not_in_evidence"
