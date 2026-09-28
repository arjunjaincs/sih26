"""
PRAMAAN dataset ingestion engine.

Converts an external dataset (image directory or COCO JSON) into persisted
Sample records in the PRAMAAN database.

V1 Supported Formats:
  - IMAGE_DIR: A plain directory of image files (no annotations)
  - COCO_JSON: COCO-format dataset with a JSON annotations file

V1 Unsupported (planned):
  - YOLO format (planned for Phase 3+)
  - Pascal VOC XML
  - Custom CSV

Failure Policy (V1):
  - Structural failures (invalid COCO JSON, missing required keys, duplicate
    IDs) fail the entire ingestion immediately — no partial dataset is
    created in an ambiguous state.
  - Individual image failures (corrupt image, oversized image) by default
    also fail the ingestion. This is the "fail-closed" policy.
    Rationale: A dataset with unprocessable images produces inaccurate
    sample counts and hash coverage; analysts must know about every failure.
  - The caller can set skip_invalid_images=True to record failures and
    continue — useful for exploratory analysis where completeness is less
    critical than coverage breadth. This is opt-in; default is fail-closed.

Memory Behavior:
  - Images are processed one at a time; pixel data is not held in memory.
  - COCO JSON is loaded fully (annotations metadata only, not image data).
  - Samples are persisted in a single batch transaction after all images
    are processed (or in configurable batch sizes for very large datasets).

No detector logic lives here — pHash/dHash are fingerprints attached to
each Sample; duplicate analysis belongs in Phase 3 (DI-01 detector).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import imagehash
from PIL import Image

from backend.domain.entities import Asset, Dataset, Sample
from backend.domain.enums import AssetType, DatasetFormat
from backend.infra.crypto import hash_file
from backend.infra.db import AssetRepository, DatasetRepository, SampleRepository
from backend.infra.image_loader import ImageLoadError, load_image_metadata
from backend.infra.file_validator import validate_absolute_path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported image file extensions
# Extensions are a first-pass filter only; actual format is verified by
# image_loader via Pillow's header detection.
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".bmp",
})

# Batch size for sample persistence — limits peak memory for large datasets.
_BATCH_SIZE = 200


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class SampleError:
    """Records a single image that could not be processed."""

    file_name: str
    reason: str
    code: str


@dataclass
class IngestionResult:
    """
    Summary of a completed (or partially completed) dataset ingestion.

    samples_ingested counts only successfully persisted samples.
    errors contains records for any images that were skipped or failed.
    """

    dataset_id: str
    samples_ingested: int
    samples_skipped: int
    errors: list[SampleError] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_hashes(path: Path) -> tuple[str, str, str]:
    """
    Return (sha256, phash_hex, dhash_hex) for the image at *path*.

    sha256  — SHA-256 of the raw file bytes
    phash   — perceptual hash as a hex string (length depends on hash_size=8 → 16 chars)
    dhash   — difference hash as a hex string (same length)

    Both perceptual hashes are computed from the decoded image pixels,
    not from the compressed bytes, so format differences do not affect them.

    imagehash.ImageHash.__str__() returns a zero-padded hex string.
    We store it directly — no int() conversion needed.
    """
    sha256 = hash_file(path)

    with Image.open(path) as img:
        ph = imagehash.phash(img)
        dh = imagehash.dhash(img)

    # str() on ImageHash returns the hex representation directly.
    # It is already padded to the correct length (16 chars for hash_size=8).
    phash_hex = str(ph)
    dhash_hex = str(dh)

    return sha256, phash_hex, dhash_hex


def _iter_image_files(directory: Path) -> Iterator[Path]:
    """
    Yield all files with supported extensions under *directory*.

    Yields absolute Path objects in sorted order (reproducible across runs).
    Non-image files are silently skipped — see module docstring for policy.
    """
    for p in sorted(directory.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield p


# ---------------------------------------------------------------------------
# Image-directory ingestion
# ---------------------------------------------------------------------------

def ingest_image_directory(
    directory: Path,
    dataset_id: str,
    conn: sqlite3.Connection,
    *,
    max_image_size_bytes: int = 50 * 1024 * 1024,
    max_image_dimension: int = 8192,
    skip_invalid_images: bool = False,
) -> IngestionResult:
    """
    Ingest a plain directory of images into the PRAMAAN database.

    For each supported image file:
      1. Validate file size
      2. Load and validate image (format, dimensions, decode)
      3. Compute SHA-256, pHash, dHash
      4. Build a Sample entity
      5. Persist samples in batches

    Parameters
    ----------
    directory:
        Absolute path to the image directory.  Must exist.
    dataset_id:
        The dataset_id (= asset_id) under which samples will be stored.
    conn:
        Open SQLite connection.  Caller owns the connection lifecycle.
    max_image_size_bytes:
        Per-image file size limit.
    max_image_dimension:
        Maximum width or height in pixels.
    skip_invalid_images:
        If False (default, fail-closed), any image error aborts ingestion.
        If True, the error is recorded and ingestion continues.

    Returns
    -------
    IngestionResult
    """
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    sample_repo = SampleRepository(conn)
    dataset_repo = DatasetRepository(conn)

    samples_batch: list[Sample] = []
    errors: list[SampleError] = []
    total_ingested = 0

    image_files = list(_iter_image_files(directory))
    log.info("Found %d candidate image files in %s", len(image_files), directory)

    # Check for metadata.json, dataset_manifest.json, contributors.json, or labels.json in directory and parent
    contributors_map: dict[str, str] = {}
    labels_map: dict[str, list[str]] = {}
    meta_candidates = (
        directory / "metadata.json",
        directory.parent / "metadata.json",
        directory / "dataset_manifest.json",
        directory.parent / "dataset_manifest.json",
        directory / "contributors.json",
        directory.parent / "contributors.json",
        directory / "labels.json",
        directory.parent / "labels.json",
    )
    for meta_file in meta_candidates:
        if meta_file.is_file():
            try:
                with open(meta_file, "r", encoding="utf-8") as mf:
                    mdata = json.load(mf)
                    if isinstance(mdata, dict):
                        if "contributors" in mdata and isinstance(mdata["contributors"], dict):
                            contributors_map.update({str(k): str(v) for k, v in mdata["contributors"].items()})
                        if "labels" in mdata and isinstance(mdata["labels"], dict):
                            for k, v in mdata["labels"].items():
                                if isinstance(v, list):
                                    labels_map[str(k)] = [str(x) for x in v]
                                else:
                                    labels_map[str(k)] = [str(v)]
                        elif "samples" in mdata and isinstance(mdata["samples"], list):
                            for it in mdata["samples"]:
                                if isinstance(it, dict) and "file_name" in it:
                                    if "contributor" in it:
                                        contributors_map[str(it["file_name"])] = str(it["contributor"])
                                    if "label" in it:
                                        labels_map[str(it["file_name"])] = [str(it["label"])]
                                    elif "labels" in it and isinstance(it["labels"], list):
                                        labels_map[str(it["file_name"])] = [str(x) for x in it["labels"]]
                        elif "images" in mdata and isinstance(mdata["images"], list):
                            for it in mdata["images"]:
                                if isinstance(it, dict) and "file_name" in it:
                                    if "contributor" in it:
                                        contributors_map[str(it["file_name"])] = str(it["contributor"])
                                    if "label" in it:
                                        labels_map[str(it["file_name"])] = [str(it["label"])]
                                    elif "labels" in it and isinstance(it["labels"], list):
                                        labels_map[str(it["file_name"])] = [str(x) for x in it["labels"]]
                        else:
                            for k, v in mdata.items():
                                if isinstance(v, (str, int)):
                                    contributors_map[str(k)] = str(v)
            except Exception:
                pass

    for img_path in image_files:
        file_name = img_path.name

        # -- File-level validation (size) ------------------------------------
        fv = validate_absolute_path(img_path, max_size_bytes=max_image_size_bytes)
        if not fv.ok:
            err = SampleError(file_name=file_name, reason=fv.message, code=fv.code.value)
            if not skip_invalid_images:
                raise IngestionError(
                    f"Image validation failed ({fv.code.value}): {fv.message}"
                )
            log.warning("Skipping %s: %s", file_name, fv.message)
            errors.append(err)
            continue

        # -- Image decode and metadata extraction ----------------------------
        try:
            meta = load_image_metadata(
                img_path,
                max_size_bytes=max_image_size_bytes,
                max_dimension=max_image_dimension,
            )
        except ImageLoadError as exc:
            err = SampleError(file_name=file_name, reason=str(exc), code=exc.code.value)
            if not skip_invalid_images:
                raise IngestionError(
                    f"Image load failed ({exc.code.value}): {exc}"
                ) from exc
            log.warning("Skipping %s: %s", file_name, exc)
            errors.append(err)
            continue

        # -- Hash computation ------------------------------------------------
        try:
            sha256, phash_hex, dhash_hex = _compute_hashes(img_path)
        except Exception as exc:
            err = SampleError(file_name=file_name, reason=str(exc), code="hash_error")
            if not skip_invalid_images:
                raise IngestionError(f"Hash computation failed: {exc}") from exc
            log.warning("Skipping %s (hash error): %s", file_name, exc)
            errors.append(err)
            continue

        # Determine contributor if available
        contributor: str | None = None
        if file_name in contributors_map:
            contributor = contributors_map[file_name]
        else:
            try:
                rel_parent = img_path.relative_to(directory).parent
                if rel_parent != Path(".") and str(rel_parent) != "":
                    contributor = rel_parent.parts[0]
            except ValueError:
                pass

        sample = Sample(
            dataset_id=dataset_id,
            file_name=file_name,
            sha256=sha256,
            phash=phash_hex,
            dhash=dhash_hex,
            width=meta.width,
            height=meta.height,
            file_size_bytes=meta.file_size_bytes,
            labels=labels_map.get(file_name, []),
            contributor=contributor,
        )
        samples_batch.append(sample)

        # -- Batch persist ---------------------------------------------------
        if len(samples_batch) >= _BATCH_SIZE:
            sample_repo.insert_many(samples_batch)
            total_ingested += len(samples_batch)
            log.debug("Persisted batch of %d samples", len(samples_batch))
            samples_batch = []

    # Persist remaining samples
    if samples_batch:
        sample_repo.insert_many(samples_batch)
        total_ingested += len(samples_batch)

    # Update sample count on Dataset record
    dataset_repo.update_sample_count(dataset_id, total_ingested)
    log.info(
        "Ingestion complete: %d samples ingested, %d errors",
        total_ingested,
        len(errors),
    )

    return IngestionResult(
        dataset_id=dataset_id,
        samples_ingested=total_ingested,
        samples_skipped=len(errors),
        errors=errors,
        class_names=[],
    )


# ---------------------------------------------------------------------------
# COCO JSON ingestion
# ---------------------------------------------------------------------------

@dataclass
class _CocoImage:
    id: int
    file_name: str
    width: int | None
    height: int | None
    contributor: str | None = None


@dataclass
class _CocoCategory:
    id: int
    name: str


@dataclass
class _CocoAnnotation:
    image_id: int
    category_id: int


def _parse_coco_json(json_path: Path) -> tuple[
    dict[int, _CocoImage],
    dict[int, _CocoCategory],
    dict[int, list[str]],  # image_id → label names
]:
    """
    Parse and validate a COCO JSON annotation file.

    Returns
    -------
    (images_by_id, categories_by_id, labels_by_image_id)

    Raises
    ------
    CocoValidationError on any structural problem.
    """
    try:
        st = json_path.stat()
        if st.st_size > 50 * 1024 * 1024:
            raise CocoValidationError(f"COCO JSON exceeds maximum size limit of 50MB ({st.st_size} bytes)")
        raw = json_path.read_bytes()
    except OSError as exc:
        raise CocoValidationError(f"Cannot read COCO JSON: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CocoValidationError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise CocoValidationError("COCO JSON root must be a JSON object")

    # --- Required top-level keys -------------------------------------------
    for key in ("images", "annotations", "categories"):
        if key not in data:
            raise CocoValidationError(f"Missing required COCO key: {key!r}")
        if not isinstance(data[key], list):
            raise CocoValidationError(f"COCO key {key!r} must be a list")

    # --- Parse categories --------------------------------------------------
    categories: dict[int, _CocoCategory] = {}
    for i, cat in enumerate(data["categories"]):
        if not isinstance(cat, dict):
            raise CocoValidationError(f"categories[{i}] is not an object")
        cid = cat.get("id")
        name = cat.get("name")
        if not isinstance(cid, int):
            raise CocoValidationError(f"categories[{i}].id must be an integer")
        if not isinstance(name, str) or not name.strip():
            raise CocoValidationError(f"categories[{i}].name must be a non-empty string")
        if cid in categories:
            raise CocoValidationError(f"Duplicate category id: {cid}")
        categories[cid] = _CocoCategory(id=cid, name=name.strip())

    # --- Parse images -------------------------------------------------------
    images: dict[int, _CocoImage] = {}
    for i, img in enumerate(data["images"]):
        if not isinstance(img, dict):
            raise CocoValidationError(f"images[{i}] is not an object")
        iid = img.get("id")
        fname = img.get("file_name")
        if not isinstance(iid, int):
            raise CocoValidationError(f"images[{i}].id must be an integer")
        if not isinstance(fname, str) or not fname.strip():
            raise CocoValidationError(f"images[{i}].file_name must be a non-empty string")
        if iid in images:
            raise CocoValidationError(f"Duplicate image id: {iid}")
        contrib = img.get("contributor") or img.get("source") or img.get("user_id") or img.get("annotator")
        if contrib is not None:
            contrib = str(contrib).strip()
        elif "info" in data and isinstance(data["info"], dict) and "contributor" in data["info"]:
            contrib = str(data["info"]["contributor"]).strip()

        images[iid] = _CocoImage(
            id=iid,
            file_name=fname.strip(),
            width=img.get("width") if isinstance(img.get("width"), int) else None,
            height=img.get("height") if isinstance(img.get("height"), int) else None,
            contributor=contrib,
        )

    # --- Parse annotations → build image_id → [label_name] map ------------
    labels_by_image: dict[int, list[str]] = {iid: [] for iid in images}
    for i, ann in enumerate(data["annotations"]):
        if not isinstance(ann, dict):
            raise CocoValidationError(f"annotations[{i}] is not an object")
        img_id = ann.get("image_id")
        cat_id = ann.get("category_id")
        if not isinstance(img_id, int):
            raise CocoValidationError(f"annotations[{i}].image_id must be an integer")
        if not isinstance(cat_id, int):
            raise CocoValidationError(f"annotations[{i}].category_id must be an integer")
        if img_id not in images:
            raise CocoValidationError(
                f"annotations[{i}].image_id {img_id} references unknown image"
            )
        if cat_id not in categories:
            raise CocoValidationError(
                f"annotations[{i}].category_id {cat_id} references unknown category"
            )

        # Validate bounding box if present
        if "bbox" in ann:
            bbox = ann["bbox"]
            if not isinstance(bbox, list) or len(bbox) != 4:
                raise CocoValidationError(
                    f"annotations[{i}].bbox must be a list of 4 numbers [x, y, width, height]"
                )
            for val in bbox:
                if not isinstance(val, (int, float)) or val < 0:
                    raise CocoValidationError(
                        f"annotations[{i}].bbox coordinates must be non-negative numbers: {bbox}"
                    )
            if bbox[2] <= 0 or bbox[3] <= 0:
                raise CocoValidationError(
                    f"annotations[{i}].bbox width and height must be positive: {bbox}"
                )

        label_name = categories[cat_id].name
        if label_name not in labels_by_image[img_id]:
            labels_by_image[img_id].append(label_name)

    return images, categories, labels_by_image


def ingest_coco_dataset(
    coco_json_path: Path,
    images_dir: Path,
    dataset_id: str,
    conn: sqlite3.Connection,
    *,
    max_image_size_bytes: int = 50 * 1024 * 1024,
    max_image_dimension: int = 8192,
    skip_invalid_images: bool = False,
) -> IngestionResult:
    """
    Ingest a COCO-format dataset into the PRAMAAN database.

    Parameters
    ----------
    coco_json_path:
        Absolute path to the COCO annotations JSON file.
    images_dir:
        Absolute path to the directory containing the image files.
    dataset_id:
        The dataset_id (= asset_id) for this dataset.
    conn:
        Open SQLite connection.
    max_image_size_bytes:
        Per-image file size limit.
    max_image_dimension:
        Maximum width or height in pixels.
    skip_invalid_images:
        See ingest_image_directory for policy description.

    Returns
    -------
    IngestionResult
    """
    # Structural parse + validation first — no images touched yet.
    images_meta, categories, labels_by_image = _parse_coco_json(coco_json_path)

    sample_repo = SampleRepository(conn)
    dataset_repo = DatasetRepository(conn)

    samples_batch: list[Sample] = []
    errors: list[SampleError] = []
    total_ingested = 0

    class_names = sorted(c.name for c in categories.values())
    log.info(
        "COCO: %d images, %d categories, images_dir=%s",
        len(images_meta),
        len(categories),
        images_dir,
    )

    for coco_img in images_meta.values():
        file_name = coco_img.file_name
        img_path = images_dir / file_name

        # -- Check image file exists -----------------------------------------
        if not img_path.exists():
            err = SampleError(
                file_name=file_name,
                reason=f"Image file not found: {img_path}",
                code="file_not_found",
            )
            if not skip_invalid_images:
                raise IngestionError(
                    f"Missing image file: {file_name}"
                )
            errors.append(err)
            log.warning("Missing image: %s", file_name)
            continue

        # -- File-level validation -------------------------------------------
        fv = validate_absolute_path(img_path, max_size_bytes=max_image_size_bytes)
        if not fv.ok:
            err = SampleError(file_name=file_name, reason=fv.message, code=fv.code.value)
            if not skip_invalid_images:
                raise IngestionError(
                    f"Image validation failed ({fv.code.value}): {fv.message}"
                )
            errors.append(err)
            log.warning("Skipping %s: %s", file_name, fv.message)
            continue

        # -- Image decode and metadata extraction ----------------------------
        try:
            meta = load_image_metadata(
                img_path,
                max_size_bytes=max_image_size_bytes,
                max_dimension=max_image_dimension,
            )
        except ImageLoadError as exc:
            err = SampleError(file_name=file_name, reason=str(exc), code=exc.code.value)
            if not skip_invalid_images:
                raise IngestionError(
                    f"Image load failed ({exc.code.value}): {exc}"
                ) from exc
            errors.append(err)
            log.warning("Skipping %s: %s", file_name, exc)
            continue

        # -- Hash computation ------------------------------------------------
        try:
            sha256, phash_hex, dhash_hex = _compute_hashes(img_path)
        except Exception as exc:
            err = SampleError(file_name=file_name, reason=str(exc), code="hash_error")
            if not skip_invalid_images:
                raise IngestionError(f"Hash computation failed: {exc}") from exc
            errors.append(err)
            log.warning("Skipping %s (hash error): %s", file_name, exc)
            continue

        labels = labels_by_image.get(coco_img.id, [])
        sample = Sample(
            dataset_id=dataset_id,
            file_name=file_name,
            sha256=sha256,
            phash=phash_hex,
            dhash=dhash_hex,
            width=meta.width,
            height=meta.height,
            file_size_bytes=meta.file_size_bytes,
            labels=labels,
            contributor=coco_img.contributor,
        )
        samples_batch.append(sample)

        if len(samples_batch) >= _BATCH_SIZE:
            sample_repo.insert_many(samples_batch)
            total_ingested += len(samples_batch)
            log.debug("Persisted batch of %d samples", len(samples_batch))
            samples_batch = []

    # Persist remaining samples
    if samples_batch:
        sample_repo.insert_many(samples_batch)
        total_ingested += len(samples_batch)

    dataset_repo.update_sample_count(dataset_id, total_ingested)
    log.info(
        "COCO ingestion complete: %d samples, %d errors",
        total_ingested,
        len(errors),
    )

    return IngestionResult(
        dataset_id=dataset_id,
        samples_ingested=total_ingested,
        samples_skipped=len(errors),
        errors=errors,
        class_names=class_names,
    )


# ---------------------------------------------------------------------------
# YOLO dataset ingestion
# ---------------------------------------------------------------------------

def ingest_yolo_dataset(
    yolo_dir: Path,
    dataset_id: str,
    conn: sqlite3.Connection,
    *,
    images_dir: Path | None = None,
    labels_dir: Path | None = None,
    max_image_size_bytes: int = 50 * 1024 * 1024,
    max_image_dimension: int = 8192,
    max_label_size_bytes: int = 10 * 1024 * 1024,
    skip_invalid_images: bool = False,
) -> IngestionResult:
    """
    Ingest a YOLO-format dataset into the PRAMAAN database.

    Directory structure:
      yolo_dir/
        images/     (optional subfolder; images can also reside directly in yolo_dir)
        labels/     (optional subfolder; label .txt files can also reside directly in yolo_dir)
        classes.txt (optional class names, 1 per line)
        data.yaml   (optional dataset config containing 'names')

    Each label file is named <image_stem>.txt and contains lines:
      <class_id> <x_center> <y_center> <width> <height>
    where coordinates are normalized to [0.0, 1.0].
    """
    import math

    if not yolo_dir.is_dir():
        raise ValueError(f"Not a directory: {yolo_dir}")

    # Determine image directory
    if images_dir is not None and images_dir.is_dir():
        img_dir = images_dir
    elif (yolo_dir / "images").is_dir():
        img_dir = yolo_dir / "images"
    else:
        img_dir = yolo_dir

    # Determine labels directory
    if labels_dir is not None and labels_dir.is_dir():
        lbl_dir = labels_dir
    elif (yolo_dir / "labels").is_dir():
        lbl_dir = yolo_dir / "labels"
    else:
        lbl_dir = img_dir

    # Resolve class names
    class_names: list[str] = []
    classes_file = None
    for cand in (
        yolo_dir / "classes.txt",
        lbl_dir / "classes.txt",
        img_dir / "classes.txt",
    ):
        if cand.is_file():
            classes_file = cand
            break

    if classes_file is not None:
        try:
            class_names = [
                line.strip()
                for line in classes_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except Exception as exc:
            raise YoloValidationError(f"Cannot read classes.txt: {exc}") from exc
    else:
        # Check data.yaml or data.yml
        for yml_cand in (yolo_dir / "data.yaml", yolo_dir / "data.yml"):
            if yml_cand.is_file():
                try:
                    import yaml
                    yd = yaml.safe_load(yml_cand.read_text(encoding="utf-8"))
                    if isinstance(yd, dict) and "names" in yd:
                        names_val = yd["names"]
                        if isinstance(names_val, list):
                            class_names = [str(x) for x in names_val]
                        elif isinstance(names_val, dict):
                            # sort by integer key if possible
                            sorted_keys = sorted(names_val.keys(), key=lambda k: int(k) if str(k).isdigit() else k)
                            class_names = [str(names_val[k]) for k in sorted_keys]
                except Exception as exc:
                    log.warning("Could not parse %s: %s", yml_cand, exc)
                break

    # Read contributors map if present
    contributors_map: dict[str, str] = {}
    meta_candidates = (
        yolo_dir / "metadata.json",
        yolo_dir.parent / "metadata.json",
        yolo_dir / "contributors.json",
        yolo_dir.parent / "contributors.json",
    )
    for meta_file in meta_candidates:
        if meta_file.is_file():
            try:
                with open(meta_file, "r", encoding="utf-8") as mf:
                    mdata = json.load(mf)
                    if isinstance(mdata, dict):
                        if "contributors" in mdata and isinstance(mdata["contributors"], dict):
                            contributors_map.update({str(k): str(v) for k, v in mdata["contributors"].items()})
                        elif "samples" in mdata and isinstance(mdata["samples"], list):
                            for it in mdata["samples"]:
                                if isinstance(it, dict) and "file_name" in it and "contributor" in it:
                                    contributors_map[str(it["file_name"])] = str(it["contributor"])
            except Exception:
                pass

    image_files = list(_iter_image_files(img_dir))
    if not image_files:
        raise YoloValidationError(f"No image files found in YOLO directory: {img_dir}")

    sample_repo = SampleRepository(conn)
    dataset_repo = DatasetRepository(conn)

    samples_batch: list[Sample] = []
    errors: list[SampleError] = []
    total_ingested = 0

    for img_path in image_files:
        file_name = img_path.name
        stem = img_path.stem

        # Look for matching label file
        lbl_path = lbl_dir / f"{stem}.txt"
        if not lbl_path.is_file():
            alt_path = img_path.parent / f"{stem}.txt"
            if alt_path.is_file():
                lbl_path = alt_path
            else:
                err = SampleError(
                    file_name=file_name,
                    reason=f"Missing label file: {stem}.txt",
                    code="missing_label",
                )
                if not skip_invalid_images:
                    raise YoloValidationError(
                        f"Missing label file for image '{file_name}': expected '{stem}.txt' in {lbl_dir}"
                    )
                errors.append(err)
                continue

        # Validate label file size
        try:
            st = lbl_path.stat()
            if st.st_size > max_label_size_bytes:
                raise YoloValidationError(
                    f"Label file {lbl_path.name} exceeds {max_label_size_bytes} bytes ({st.st_size} bytes)"
                )
            lbl_raw = lbl_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise YoloValidationError(f"Cannot read label file {lbl_path}: {exc}") from exc

        # Parse and validate label lines
        class_ids_in_sample: set[int] = set()
        for line_num, line in enumerate(lbl_raw.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            tokens = line.split()
            if len(tokens) < 5:
                raise YoloValidationError(
                    f"Malformed YOLO label line in {lbl_path.name}:{line_num} "
                    f"— expected 5 tokens (class x y w h), got {len(tokens)}: {line!r}"
                )

            # Class ID
            try:
                cid = int(tokens[0])
            except ValueError:
                raise YoloValidationError(
                    f"Invalid non-integer class ID in {lbl_path.name}:{line_num}: {tokens[0]!r}"
                )
            if cid < 0:
                raise YoloValidationError(
                    f"Class ID must be non-negative in {lbl_path.name}:{line_num}: {cid}"
                )
            if class_names and cid >= len(class_names):
                raise YoloValidationError(
                    f"Class ID {cid} in {lbl_path.name}:{line_num} exceeds defined class count ({len(class_names)})"
                )

            # Bounding box coordinates
            try:
                xc = float(tokens[1])
                yc = float(tokens[2])
                w = float(tokens[3])
                h = float(tokens[4])
            except ValueError:
                raise YoloValidationError(
                    f"Malformed numeric coordinates in {lbl_path.name}:{line_num}: {line!r}"
                )

            if any(math.isnan(v) or math.isinf(v) for v in (xc, yc, w, h)):
                raise YoloValidationError(
                    f"Coordinates contain NaN or Inf in {lbl_path.name}:{line_num}: {line!r}"
                )
            if not (0.0 <= xc <= 1.0 and 0.0 <= yc <= 1.0):
                raise YoloValidationError(
                    f"Center coordinates out of bounds [0.0, 1.0] in {lbl_path.name}:{line_num}: "
                    f"xc={xc}, yc={yc}"
                )
            if not (0.0 < w <= 1.0 and 0.0 < h <= 1.0):
                raise YoloValidationError(
                    f"Width or height out of bounds (0.0, 1.0] in {lbl_path.name}:{line_num}: "
                    f"w={w}, h={h}"
                )

            class_ids_in_sample.add(cid)

        # File-level image validation
        fv = validate_absolute_path(img_path, max_size_bytes=max_image_size_bytes)
        if not fv.ok:
            err = SampleError(file_name=file_name, reason=fv.message, code=fv.code.value)
            if not skip_invalid_images:
                raise IngestionError(f"Image validation failed ({fv.code.value}): {fv.message}")
            errors.append(err)
            continue

        try:
            meta = load_image_metadata(
                img_path,
                max_size_bytes=max_image_size_bytes,
                max_dimension=max_image_dimension,
            )
        except ImageLoadError as exc:
            err = SampleError(file_name=file_name, reason=str(exc), code=exc.code.value)
            if not skip_invalid_images:
                raise IngestionError(f"Image load failed ({exc.code.value}): {exc}") from exc
            errors.append(err)
            continue

        try:
            sha256, phash_hex, dhash_hex = _compute_hashes(img_path)
        except Exception as exc:
            err = SampleError(file_name=file_name, reason=str(exc), code="hash_error")
            if not skip_invalid_images:
                raise IngestionError(f"Hash computation failed: {exc}") from exc
            errors.append(err)
            continue

        # Resolve labels
        labels = [
            class_names[c] if c < len(class_names) else f"class_{c}"
            for c in sorted(class_ids_in_sample)
        ]

        # Determine contributor
        contributor: str | None = contributors_map.get(file_name)
        if contributor is None:
            try:
                rel_parent = img_path.relative_to(yolo_dir).parent
                if rel_parent != Path(".") and str(rel_parent) != "":
                    contributor = rel_parent.parts[0]
            except ValueError:
                pass

        sample = Sample(
            dataset_id=dataset_id,
            file_name=file_name,
            sha256=sha256,
            phash=phash_hex,
            dhash=dhash_hex,
            width=meta.width,
            height=meta.height,
            file_size_bytes=meta.file_size_bytes,
            labels=labels,
            contributor=contributor,
        )
        samples_batch.append(sample)

        if len(samples_batch) >= _BATCH_SIZE:
            sample_repo.insert_many(samples_batch)
            total_ingested += len(samples_batch)
            samples_batch = []

    if samples_batch:
        sample_repo.insert_many(samples_batch)
        total_ingested += len(samples_batch)

    dataset_repo.update_sample_count(dataset_id, total_ingested)
    log.info(
        "YOLO ingestion complete: %d samples ingested, %d errors, classes=%s",
        total_ingested,
        len(errors),
        class_names,
    )

    return IngestionResult(
        dataset_id=dataset_id,
        samples_ingested=total_ingested,
        samples_skipped=len(errors),
        errors=errors,
        class_names=class_names,
    )


# ---------------------------------------------------------------------------
# Dataset registration helper
# ---------------------------------------------------------------------------

def register_dataset(
    assessment_id: str,
    name: str,
    source_path: Path,
    fmt: DatasetFormat,
    conn: sqlite3.Connection,
) -> tuple[Asset, Dataset]:
    """
    Create and persist an Asset + Dataset record for a new dataset.

    The asset SHA-256 is a placeholder ("0"*64) at registration time;
    for directories there is no single canonical hash.  Individual sample
    SHA-256 values are the authoritative fingerprints.

    Returns
    -------
    (asset, dataset) — both already persisted in the database.
    """
    asset = Asset(
        assessment_id=assessment_id,
        asset_type=AssetType.DATASET,
        name=name,
        sha256="0" * 64,  # Placeholder — no single hash for a directory
        size_bytes=0,
    )
    dataset = Dataset(
        dataset_id=asset.asset_id,
        assessment_id=assessment_id,
        format=fmt,
        source_path=str(source_path),
        sample_count=0,
    )
    AssetRepository(conn).insert(asset)
    DatasetRepository(conn).insert(dataset)
    return asset, dataset


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class IngestionError(Exception):
    """Raised when ingestion cannot continue due to a fatal error."""


class CocoValidationError(Exception):
    """Raised when a COCO JSON file fails structural validation."""


class YoloValidationError(Exception):
    """Raised when a YOLO dataset fails structural or coordinate validation."""
