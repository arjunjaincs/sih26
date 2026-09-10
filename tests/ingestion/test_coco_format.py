"""
Ingestion tests: COCO JSON format.

Tests that:
  - A valid COCO dataset ingests correctly with labels
  - Labels are mapped correctly from categories
  - Multiple annotations per image are handled
  - Malformed COCO JSON is rejected with explicit errors
  - Missing image files are caught
  - Duplicate image IDs are rejected
  - Invalid category references are rejected
  - Ingested samples persist correctly with labels preserved

No findings or risk assessments are produced here.
All test data is generated programmatically.
"""

import json
from pathlib import Path

import pytest
from PIL import Image

from backend.domain.entities import Assessment
from backend.domain.enums import DatasetFormat
from backend.infra.db import AssessmentRepository, SampleRepository
from backend.infra.ingestion import (
    CocoValidationError,
    IngestionError,
    ingest_coco_dataset,
    register_dataset,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png(path: Path, width: int = 32, height: int = 32, color: str = "red") -> Path:
    Image.new("RGB", (width, height), color=color).save(path, format="PNG")
    return path


def _write_coco_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _minimal_coco(images_dir: Path, image_files: list[str]) -> dict:
    """Build a minimal valid COCO JSON dict for the given image filenames."""
    return {
        "images": [
            {"id": i + 1, "file_name": fname, "width": 32, "height": 32}
            for i, fname in enumerate(image_files)
        ],
        "annotations": [],
        "categories": [],
    }


def _setup_assessment_and_dataset(db, source_path: Path):
    a = Assessment(title="COCO test")
    AssessmentRepository(db).insert(a)
    asset, dataset = register_dataset(
        assessment_id=a.assessment_id,
        name="coco_test",
        source_path=source_path,
        fmt=DatasetFormat.COCO_JSON,
        conn=db,
    )
    return a.assessment_id, dataset.dataset_id


# ---------------------------------------------------------------------------
# Valid COCO ingestion
# ---------------------------------------------------------------------------

class TestValidCocoIngestion:
    def test_no_annotations_dataset_ingests(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_png(images_dir / "img1.png")
        _make_png(images_dir / "img2.png")

        coco = _minimal_coco(images_dir, ["img1.png", "img2.png"])
        json_path = _write_coco_json(tmp_path / "annotations.json", coco)

        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)
        result = ingest_coco_dataset(json_path, images_dir, dataset_id, db)

        assert result.samples_ingested == 2
        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert len(samples) == 2

    def test_labels_mapped_correctly(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_png(images_dir / "cat.png")
        _make_png(images_dir / "dog.png")

        coco = {
            "images": [
                {"id": 1, "file_name": "cat.png", "width": 32, "height": 32},
                {"id": 2, "file_name": "dog.png", "width": 32, "height": 32},
            ],
            "categories": [
                {"id": 1, "name": "cat"},
                {"id": 2, "name": "dog"},
            ],
            "annotations": [
                {"image_id": 1, "category_id": 1},
                {"image_id": 2, "category_id": 2},
            ],
        }
        json_path = _write_coco_json(tmp_path / "anns.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        result = ingest_coco_dataset(json_path, images_dir, dataset_id, db)

        assert result.samples_ingested == 2
        assert "cat" in result.class_names
        assert "dog" in result.class_names

        samples = {s.file_name: s for s in SampleRepository(db).list_by_dataset(dataset_id)}
        assert "cat" in samples["cat.png"].labels
        assert "dog" in samples["dog.png"].labels

    def test_multiple_annotations_per_image(self, db, tmp_path):
        """An image with multiple category annotations gets all labels."""
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_png(images_dir / "multi.png")

        coco = {
            "images": [{"id": 1, "file_name": "multi.png", "width": 32, "height": 32}],
            "categories": [
                {"id": 1, "name": "car"},
                {"id": 2, "name": "person"},
                {"id": 3, "name": "traffic_light"},
            ],
            "annotations": [
                {"image_id": 1, "category_id": 1},
                {"image_id": 1, "category_id": 2},
                {"image_id": 1, "category_id": 3},
            ],
        }
        json_path = _write_coco_json(tmp_path / "anns.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        ingest_coco_dataset(json_path, images_dir, dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert len(samples) == 1
        assert set(samples[0].labels) == {"car", "person", "traffic_light"}

    def test_unlabeled_image_has_empty_labels(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_png(images_dir / "unlabeled.png")

        coco = {
            "images": [{"id": 1, "file_name": "unlabeled.png", "width": 32, "height": 32}],
            "categories": [{"id": 1, "name": "cat"}],
            "annotations": [],  # No annotation for this image
        }
        json_path = _write_coco_json(tmp_path / "anns.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        ingest_coco_dataset(json_path, images_dir, dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert samples[0].labels == []

    def test_class_names_in_result(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_png(images_dir / "img.png")

        coco = {
            "images": [{"id": 1, "file_name": "img.png", "width": 32, "height": 32}],
            "categories": [
                {"id": 10, "name": "zebra"},
                {"id": 20, "name": "giraffe"},
            ],
            "annotations": [],
        }
        json_path = _write_coco_json(tmp_path / "anns.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        result = ingest_coco_dataset(json_path, images_dir, dataset_id, db)

        assert "zebra" in result.class_names
        assert "giraffe" in result.class_names


# ---------------------------------------------------------------------------
# Malformed COCO JSON — must be rejected
# ---------------------------------------------------------------------------

class TestMalformedCoco:
    def test_invalid_json_rejected(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        json_path = tmp_path / "bad.json"
        json_path.write_text("{ this is not json }", encoding="utf-8")
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(CocoValidationError, match="[Ii]nvalid JSON"):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)

    def test_missing_images_key_rejected(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        json_path = _write_coco_json(
            tmp_path / "missing_images.json",
            {"annotations": [], "categories": []},
        )
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(CocoValidationError, match="images"):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)

    def test_missing_annotations_key_rejected(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        json_path = _write_coco_json(
            tmp_path / "miss_ann.json",
            {"images": [], "categories": []},
        )
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(CocoValidationError, match="annotations"):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)

    def test_missing_categories_key_rejected(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        json_path = _write_coco_json(
            tmp_path / "miss_cat.json",
            {"images": [], "annotations": []},
        )
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(CocoValidationError, match="categories"):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)

    def test_duplicate_image_id_rejected(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        coco = {
            "images": [
                {"id": 1, "file_name": "a.png", "width": 32, "height": 32},
                {"id": 1, "file_name": "b.png", "width": 32, "height": 32},  # Duplicate id
            ],
            "annotations": [],
            "categories": [],
        }
        json_path = _write_coco_json(tmp_path / "dup.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(CocoValidationError, match="[Dd]uplicate"):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)

    def test_duplicate_category_id_rejected(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        coco = {
            "images": [],
            "annotations": [],
            "categories": [
                {"id": 1, "name": "cat"},
                {"id": 1, "name": "dog"},  # Duplicate category id
            ],
        }
        json_path = _write_coco_json(tmp_path / "dup_cat.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(CocoValidationError, match="[Dd]uplicate"):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)

    def test_annotation_references_unknown_image_rejected(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_png(images_dir / "known.png")
        coco = {
            "images": [{"id": 1, "file_name": "known.png", "width": 32, "height": 32}],
            "categories": [{"id": 1, "name": "cat"}],
            "annotations": [
                {"image_id": 999, "category_id": 1},  # Unknown image_id
            ],
        }
        json_path = _write_coco_json(tmp_path / "bad_ref.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(CocoValidationError, match="[Uu]nknown image"):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)

    def test_annotation_references_unknown_category_rejected(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_png(images_dir / "img.png")
        coco = {
            "images": [{"id": 1, "file_name": "img.png", "width": 32, "height": 32}],
            "categories": [{"id": 1, "name": "cat"}],
            "annotations": [
                {"image_id": 1, "category_id": 999},  # Unknown category_id
            ],
        }
        json_path = _write_coco_json(tmp_path / "bad_cat_ref.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(CocoValidationError, match="[Uu]nknown category"):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)

    def test_root_not_a_dict_rejected(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        json_path = tmp_path / "list.json"
        json_path.write_text("[1, 2, 3]", encoding="utf-8")
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(CocoValidationError):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)


# ---------------------------------------------------------------------------
# Missing image files
# ---------------------------------------------------------------------------

class TestMissingImageFiles:
    def test_missing_image_fails_by_default(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        # Declare img.png in COCO but do NOT create the file

        coco = {
            "images": [{"id": 1, "file_name": "missing.png", "width": 32, "height": 32}],
            "annotations": [],
            "categories": [],
        }
        json_path = _write_coco_json(tmp_path / "anns.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(IngestionError, match="[Mm]issing"):
            ingest_coco_dataset(json_path, images_dir, dataset_id, db)

    def test_missing_image_skipped_with_flag(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_png(images_dir / "present.png")

        coco = {
            "images": [
                {"id": 1, "file_name": "present.png", "width": 32, "height": 32},
                {"id": 2, "file_name": "missing.png", "width": 32, "height": 32},
            ],
            "annotations": [],
            "categories": [],
        }
        json_path = _write_coco_json(tmp_path / "anns.json", coco)
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        result = ingest_coco_dataset(
            json_path, images_dir, dataset_id, db, skip_invalid_images=True
        )

        assert result.samples_ingested == 1
        assert result.samples_skipped == 1
