"""
PRAMAAN asset upload routes.

POST /api/v1/uploads -- upload an untrusted asset file (model or dataset)

Security & Design Principles
----------------------------
1. Local-first, offline-first: Bytes are stored in the content-addressed BlobStore.
2. Zero trust: Client-supplied filename is sanitized; path traversal is rejected.
3. Content verification: Format headers and magic bytes are verified; invalid or
   corrupt files fail closed.
4. Archive safety: Zip files are checked for zip-slip, traversal, and decompression bombs
   before safe extraction into an isolated directory.
5. Privacy & isolation: Server-side paths are never returned to the caller. The caller
   receives an asset_id and metadata.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from backend.api.config import settings
from backend.api.deps import BlobStoreDep, UploadRepoDep
from backend.api.schemas import UploadResponse
from backend.domain.enums import AssetType
from backend.infra.blob_store import BlobStore
from backend.infra.db import UploadRecord, UploadRepository
from backend.infra.file_validator import _is_safe_filename
from backend.infra.image_loader import SUPPORTED_FORMATS, ImageLoadError, load_image_metadata

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["uploads"])

_SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_\.\-]+$")
_CHUNK_SIZE = 1024 * 1024  # 1 MB

_MODEL_EXTENSIONS = frozenset({".onnx", ".pt", ".pth", ".ts"})
_DATASET_EXTENSIONS = frozenset({".zip", ".json", ".jpg", ".jpeg", ".png", ".webp", ".bmp"})


def _sanitize_filename(raw_name: str) -> str:
    """
    Sanitize and extract a clean filename, preserving safe extension.
    Rejects path traversal or malicious input.
    """
    if not raw_name:
        return "upload.bin"
    
    # Strip directory components (cross-platform)
    name = Path(raw_name).name.strip()
    # Normalize backslashes
    name = name.split("\\")[-1].split("/")[-1].strip()

    if not name or name in {".", ".."}:
        return "upload.bin"

    if not _is_safe_filename(name) or not _SAFE_FILENAME_RE.match(name):
        # Clean unsafe chars
        stem = Path(name).stem
        suffix = Path(name).suffix.lower()
        cleaned_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", stem)[:64]
        cleaned_suffix = re.sub(r"[^a-zA-Z0-9_\.]", "", suffix)[:10]
        name = f"{cleaned_stem or 'file'}{cleaned_suffix}"

    return name


def _safe_extract_zip(zip_path: Path, target_dir: Path, max_bytes: int, max_files: int = 5000) -> None:
    """
    Extract zip archive with strict zip-slip and bomb protection.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    target_resolved = target_dir.resolve()

    total_uncompressed = 0
    file_count = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        infolist = zf.infolist()
        if len(infolist) > max_files:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "archive_too_many_files", "message": f"Archive contains {len(infolist)} files (limit: {max_files})."}
            )

        for member in infolist:
            # Check for path traversal in archive member
            member_path = member.filename
            if ".." in member_path or member_path.startswith("/") or member_path.startswith("\\"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": "path_traversal", "message": "Archive contains forbidden path traversal sequences."}
                )

            # Prevent zip bombs
            total_uncompressed += member.file_size
            if total_uncompressed > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": "file_too_large", "message": "Uncompressed archive size exceeds limit."}
                )

            # Check target path is strictly inside destination
            dest_file = (target_dir / member_path).resolve()
            if not str(dest_file).startswith(str(target_resolved)):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": "path_traversal", "message": "Archive entry attempts to escape destination directory."}
                )

        # Safe extraction
        for member in infolist:
            dest_file = target_dir / member.filename
            if member.is_dir():
                dest_file.mkdir(parents=True, exist_ok=True)
            else:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest_file, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                file_count += 1

    if file_count == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "empty_archive", "message": "Archive contains no extractable files."}
        )


@router.post(
    "/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an asset file for assessment",
)
async def upload_asset(
    file: Annotated[UploadFile, File(...)],
    asset_type: Annotated[str | None, Form()] = None,
    blob_store: BlobStoreDep = None,
    upload_repo: UploadRepoDep = None,
) -> UploadResponse:
    """
    Accept an uploaded asset file, validate it securely, store it in content-addressed
    storage, and register it for assessment use.
    """
    raw_filename = file.filename or "upload.bin"
    if ".." in raw_filename or "/" in raw_filename or "\\" in raw_filename:
        # Client attempted path traversal in filename
        raw_filename = Path(raw_filename).name

    safe_filename = _sanitize_filename(raw_filename)
    suffix = Path(safe_filename).suffix.lower()

    # Determine asset type if not provided
    inferred_type = asset_type
    if not inferred_type or inferred_type not in {"model", "dataset"}:
        if suffix in _MODEL_EXTENSIONS:
            inferred_type = "model"
        elif suffix in _DATASET_EXTENSIONS:
            inferred_type = "dataset"
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "unsupported_format",
                    "message": f"Unsupported file extension: {suffix!r}. Allowed: .onnx, .pt, .pth, .zip, .json, .jpg, .png",
                },
            )

    # Size limits
    if inferred_type == "model":
        max_bytes = settings.max_model_size_mb * 1024 * 1024
    else:
        max_bytes = settings.max_dataset_size_mb * 1024 * 1024

    # Stream to temporary staging file and compute SHA-256
    staging_dir = settings.blob_dir / "temp"
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_path = staging_dir / f"tmp_{uuid.uuid4().hex}"

    hasher = hashlib.sha256()
    total_bytes = 0

    try:
        with open(temp_path, "wb") as f_out:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "error": "file_too_large",
                            "message": f"Uploaded file exceeds size limit of {max_bytes // (1024*1024)} MB.",
                        },
                    )
                hasher.update(chunk)
                f_out.write(chunk)
    except HTTPException:
        if temp_path.exists():
            temp_path.unlink()
        raise
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink()
        log.exception("Upload stream failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "upload_failed", "message": "Failed to receive uploaded file."},
        ) from exc

    if total_bytes == 0:
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "empty_file", "message": "Uploaded file is empty (0 bytes)."},
        )

    sha256_hex = hasher.hexdigest()
    upload_id = f"ast_{uuid.uuid4().hex[:16]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Content-addressed storage
    blob_dest = blob_store.store_file(temp_path, sha256_hex)

    detected_format: str | None = None
    final_storage_path: Path = blob_dest

    # Content verification and staging by type
    try:
        if inferred_type == "model":
            # Models must be referenced by detectors via a path with valid extension
            models_dir = settings.blob_dir / "models" / upload_id
            models_dir.mkdir(parents=True, exist_ok=True)
            model_staged = models_dir / safe_filename
            shutil.copy2(temp_path, model_staged)
            final_storage_path = model_staged

            if suffix == ".onnx":
                detected_format = "onnx"
            elif suffix in {".pt", ".pth"}:
                detected_format = "pytorch"
            elif suffix == ".ts":
                detected_format = "torchscript"
            else:
                detected_format = "unknown"

        elif inferred_type == "dataset":
            if suffix == ".zip":
                extracted_dir = settings.blob_dir / "extracted" / upload_id
                _safe_extract_zip(temp_path, extracted_dir, max_bytes=max_bytes)

                # Check if it has a COCO JSON file or is image directory
                coco_candidates = list(extracted_dir.glob("*.json")) + list(extracted_dir.glob("*/*.json"))
                if coco_candidates:
                    detected_format = "coco_json"
                    final_storage_path = coco_candidates[0]
                else:
                    detected_format = "image_dir"
                    final_storage_path = extracted_dir

            elif suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                # Single image dataset: place in isolated dir so ingest_image_directory can process it
                img_dir = settings.blob_dir / "extracted" / upload_id
                img_dir.mkdir(parents=True, exist_ok=True)
                img_staged = img_dir / safe_filename
                shutil.copy2(temp_path, img_staged)

                # Validate image integrity
                try:
                    load_image_metadata(img_staged)
                except ImageLoadError as e:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={"error": "corrupt_image", "message": str(e)},
                    )

                detected_format = "image_dir"
                final_storage_path = img_dir

            elif suffix == ".json":
                # Validate JSON structure
                try:
                    with open(temp_path, "r", encoding="utf-8") as jf:
                        jdata = json.load(jf)
                    if isinstance(jdata, dict) and "images" in jdata and "annotations" in jdata:
                        detected_format = "coco_json"
                    else:
                        detected_format = "json"
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={"error": "invalid_json", "message": f"Malformed JSON file: {e}"},
                    )
                
                json_dir = settings.blob_dir / "extracted" / upload_id
                json_dir.mkdir(parents=True, exist_ok=True)
                json_staged = json_dir / safe_filename
                shutil.copy2(temp_path, json_staged)
                final_storage_path = json_staged

    finally:
        if temp_path.exists():
            temp_path.unlink()

    # Record upload in repository
    record = UploadRecord(
        upload_id=upload_id,
        asset_type=inferred_type,
        original_filename=raw_filename,
        safe_filename=safe_filename,
        sha256=sha256_hex,
        size_bytes=total_bytes,
        content_type=file.content_type,
        storage_path=str(final_storage_path.resolve()),
        format=detected_format,
        created_at=now_iso,
    )
    upload_repo.insert(record)

    return UploadResponse(
        asset_id=upload_id,
        original_filename=raw_filename,
        sha256=sha256_hex,
        size_bytes=total_bytes,
        asset_type=inferred_type,
        format=detected_format,
        content_type=file.content_type,
        created_at=now_iso,
    )
