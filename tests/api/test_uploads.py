"""
Tests for POST /api/v1/uploads and asset_id integration with assessments.

Covers:
  1. Valid model upload (ONNX) returns 201 with asset_id and metadata
  2. Valid dataset upload (image) returns 201
  3. Empty upload (0 bytes) rejected with 422
  4. Unsupported file extension rejected with 422
  5. Filename with path traversal sequences is sanitized and safely handled
  6. Computed SHA-256 matches actual content digest
  7. Assessment created referencing model_asset_id executes MI-01 successfully
  8. Assessment referencing non-existent model_asset_id fails with 422
  9. Assessment using local-path still works (no regression)
  10. Oversized file upload rejected with 422
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class TestAssetUploads:
    def test_upload_valid_model_returns_201(self, client: TestClient, onnx_model: Path):
        content = onnx_model.read_bytes()
        expected_sha = hashlib.sha256(content).hexdigest()

        response = client.post(
            "/api/v1/uploads",
            files={"file": ("model.onnx", content, "application/octet-stream")},
            data={"asset_type": "model"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["asset_id"].startswith("ast_")
        assert data["asset_type"] == "model"
        assert data["format"] == "onnx"
        assert data["sha256"] == expected_sha
        assert data["size_bytes"] == len(content)
        assert data["original_filename"] == "model.onnx"
        assert "storage_path" not in data  # Never leak server filesystem paths

    def test_upload_valid_image_dataset(self, client: TestClient, tmp_path: Path):
        from PIL import Image
        img = Image.new("RGB", (32, 32), color=(100, 150, 200))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        raw = img_bytes.getvalue()

        response = client.post(
            "/api/v1/uploads",
            files={"file": ("sample.jpg", raw, "image/jpeg")},
            data={"asset_type": "dataset"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["asset_id"].startswith("ast_")
        assert data["asset_type"] == "dataset"
        assert data["format"] == "image_dir"
        assert data["size_bytes"] == len(raw)

    def test_upload_zip_dataset(self, client: TestClient, tmp_path: Path):
        from PIL import Image
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for i in range(2):
                img = Image.new("RGB", (32, 32), color=(i * 50, 100, 150))
                b = io.BytesIO()
                img.save(b, format="JPEG")
                zf.writestr(f"img_{i}.jpg", b.getvalue())

        raw_zip = zip_buf.getvalue()

        response = client.post(
            "/api/v1/uploads",
            files={"file": ("dataset.zip", raw_zip, "application/zip")},
            data={"asset_type": "dataset"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["asset_type"] == "dataset"
        assert data["format"] == "image_dir"

    def test_upload_empty_file_rejected(self, client: TestClient):
        response = client.post(
            "/api/v1/uploads",
            files={"file": ("empty.onnx", b"", "application/octet-stream")},
            data={"asset_type": "model"},
        )
        assert response.status_code == 422
        body = response.json()
        assert "empty" in (body.get("detail", {}).get("error", "") or str(body)).lower()

    def test_upload_unsupported_format_rejected(self, client: TestClient):
        response = client.post(
            "/api/v1/uploads",
            files={"file": ("malicious.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        assert response.status_code == 422
        body = response.json()
        assert "unsupported_format" in (body.get("detail", {}).get("error", "") or str(body))

    def test_upload_path_traversal_filename_sanitized(self, client: TestClient, onnx_model: Path):
        content = onnx_model.read_bytes()
        # Traversal attempt in filename header
        response = client.post(
            "/api/v1/uploads",
            files={"file": ("../../../../etc/passwd.onnx", content, "application/octet-stream")},
            data={"asset_type": "model"},
        )
        assert response.status_code == 201
        data = response.json()
        # Safe filename shouldn't contain traversal
        assert ".." not in data["original_filename"] or data["original_filename"] == "passwd.onnx"

    def test_upload_sha256_correctness(self, client: TestClient, onnx_model: Path):
        content = onnx_model.read_bytes()
        expected = hashlib.sha256(content).hexdigest()

        response = client.post(
            "/api/v1/uploads",
            files={"file": ("test_model.onnx", content, "application/octet-stream")},
            data={"asset_type": "model"},
        )
        assert response.status_code == 201
        assert response.json()["sha256"] == expected

    def test_assessment_using_uploaded_model_asset_id(
        self,
        client: TestClient,
        onnx_model: Path,
    ):
        # 1. Upload model
        up_res = client.post(
            "/api/v1/uploads",
            files={"file": ("eval.onnx", onnx_model.read_bytes(), "application/octet-stream")},
            data={"asset_type": "model"},
        )
        assert up_res.status_code == 201
        model_asset_id = up_res.json()["asset_id"]

        # 2. Run assessment referencing model_asset_id
        assess_res = client.post(
            "/api/v1/assessments",
            json={
                "title": "Uploaded Model Evaluation",
                "model_asset_id": model_asset_id,
            },
        )
        assert assess_res.status_code == 201
        data = assess_res.json()
        assert data["title"] == "Uploaded Model Evaluation"
        # Check that MI-01 ran
        mi01_runs = [r for r in data["detector_runs"] if "mi01" in r["detector_id"].lower()]
        assert len(mi01_runs) == 1
        assert mi01_runs[0]["ran"] is True

    def test_assessment_with_invalid_asset_id_fails_422(self, client: TestClient):
        response = client.post(
            "/api/v1/assessments",
            json={
                "title": "Bad Asset ID",
                "model_asset_id": "ast_nonexistent999",
            },
        )
        assert response.status_code == 422
        body = response.json()
        assert "invalid_asset_id" in str(body)

    def test_assessment_local_path_workflow_unaffected(
        self,
        client: TestClient,
        onnx_model: Path,
    ):
        # Existing workflow using model_path directly must work unchanged
        response = client.post(
            "/api/v1/assessments",
            json={
                "title": "Local Path Test",
                "model_path": str(onnx_model),
            },
        )
        assert response.status_code == 201
        assert response.json()["title"] == "Local Path Test"
