"""
Tests for YOLO format dataset ingestion.

Verifies:
  - Ingestion of valid YOLO datasets with images/ and labels/ subdirectories
  - Handling of classes.txt and data.yaml class mappings
  - Bounding box coordinate validation ([0.0, 1.0])
  - Invalid class ID detection
  - Missing label file detection (fail-closed vs skip)
  - Label exposure on Sample entity for downstream DI-02 compatibility
"""

import sqlite3
from pathlib import Path
import pytest
from PIL import Image

from backend.domain.entities import Assessment
from backend.domain.enums import DatasetFormat
from backend.infra.db import AssessmentRepository, SampleRepository
from backend.infra.ingestion import (
    YoloValidationError,
    ingest_yolo_dataset,
    register_dataset,
)


def _create_test_image(path: Path, width: int = 64, height: int = 64, color: tuple = (128, 128, 128)) -> None:
    img = Image.new("RGB", (width, height), color)
    img.save(path)


def _setup_db_and_dataset(db: sqlite3.Connection, tmp_path: Path) -> tuple[str, str]:
    a = Assessment(title="YOLO test")
    AssessmentRepository(db).insert(a)
    asset, ds = register_dataset(
        assessment_id=a.assessment_id,
        name="test_yolo",
        source_path=tmp_path,
        fmt=DatasetFormat.YOLO,
        conn=db,
    )
    return a.assessment_id, ds.dataset_id


class TestYoloIngestionClean:
    def test_clean_yolo_dataset_ingested(self, db, tmp_path):
        img_dir = tmp_path / "images"
        lbl_dir = tmp_path / "labels"
        img_dir.mkdir()
        lbl_dir.mkdir()

        # classes.txt
        (tmp_path / "classes.txt").write_text("pedestrian\nvehicle\ncyclist\n", encoding="utf-8")

        # 3 images and labels
        _create_test_image(img_dir / "img1.png")
        (lbl_dir / "img1.txt").write_text("0 0.5 0.5 0.2 0.3\n1 0.7 0.8 0.1 0.1\n", encoding="utf-8")

        _create_test_image(img_dir / "img2.png")
        (lbl_dir / "img2.txt").write_text("1 0.4 0.4 0.3 0.3\n", encoding="utf-8")

        _create_test_image(img_dir / "img3.png")
        (lbl_dir / "img3.txt").write_text("", encoding="utf-8")  # background / empty label is valid

        _, dataset_id = _setup_db_and_dataset(db, tmp_path)
        result = ingest_yolo_dataset(tmp_path, dataset_id, db)

        assert result.samples_ingested == 3
        assert result.samples_skipped == 0
        assert len(result.errors) == 0
        assert result.class_names == ["pedestrian", "vehicle", "cyclist"]

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert len(samples) == 3

        s1 = next(s for s in samples if s.file_name == "img1.png")
        assert sorted(s1.labels) == ["pedestrian", "vehicle"]

        s2 = next(s for s in samples if s.file_name == "img2.png")
        assert s2.labels == ["vehicle"]

        s3 = next(s for s in samples if s.file_name == "img3.png")
        assert s3.labels == []


class TestYoloIngestionValidation:
    def test_missing_label_file_fails_closed(self, db, tmp_path):
        img_dir = tmp_path / "images"
        lbl_dir = tmp_path / "labels"
        img_dir.mkdir()
        lbl_dir.mkdir()

        _create_test_image(img_dir / "img1.png")
        # No img1.txt

        _, dataset_id = _setup_db_and_dataset(db, tmp_path)
        with pytest.raises(YoloValidationError, match="Missing label file"):
            ingest_yolo_dataset(tmp_path, dataset_id, db)

    def test_missing_label_file_skipped_when_opted_in(self, db, tmp_path):
        img_dir = tmp_path / "images"
        lbl_dir = tmp_path / "labels"
        img_dir.mkdir()
        lbl_dir.mkdir()

        _create_test_image(img_dir / "img1.png")
        _create_test_image(img_dir / "img2.png")
        (lbl_dir / "img2.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

        _, dataset_id = _setup_db_and_dataset(db, tmp_path)
        result = ingest_yolo_dataset(tmp_path, dataset_id, db, skip_invalid_images=True)

        assert result.samples_ingested == 1
        assert result.samples_skipped == 1
        assert result.errors[0].code == "missing_label"

    def test_coordinates_out_of_bounds_rejected(self, db, tmp_path):
        img_dir = tmp_path / "images"
        lbl_dir = tmp_path / "labels"
        img_dir.mkdir()
        lbl_dir.mkdir()

        _create_test_image(img_dir / "img1.png")
        # Center x is 1.5 (> 1.0)
        (lbl_dir / "img1.txt").write_text("0 1.5 0.5 0.2 0.2\n", encoding="utf-8")

        _, dataset_id = _setup_db_and_dataset(db, tmp_path)
        with pytest.raises(YoloValidationError, match="Center coordinates out of bounds"):
            ingest_yolo_dataset(tmp_path, dataset_id, db)

    def test_negative_width_rejected(self, db, tmp_path):
        img_dir = tmp_path / "images"
        lbl_dir = tmp_path / "labels"
        img_dir.mkdir()
        lbl_dir.mkdir()

        _create_test_image(img_dir / "img1.png")
        (lbl_dir / "img1.txt").write_text("0 0.5 0.5 -0.2 0.2\n", encoding="utf-8")

        _, dataset_id = _setup_db_and_dataset(db, tmp_path)
        with pytest.raises(YoloValidationError, match="Width or height out of bounds"):
            ingest_yolo_dataset(tmp_path, dataset_id, db)

    def test_invalid_class_id_rejected(self, db, tmp_path):
        img_dir = tmp_path / "images"
        lbl_dir = tmp_path / "labels"
        img_dir.mkdir()
        lbl_dir.mkdir()

        (tmp_path / "classes.txt").write_text("cat\ndog\n", encoding="utf-8")

        _create_test_image(img_dir / "img1.png")
        # Class id 5 exceeds class count 2
        (lbl_dir / "img1.txt").write_text("5 0.5 0.5 0.2 0.2\n", encoding="utf-8")

        _, dataset_id = _setup_db_and_dataset(db, tmp_path)
        with pytest.raises(YoloValidationError, match="exceeds defined class count"):
            ingest_yolo_dataset(tmp_path, dataset_id, db)

    def test_malformed_token_count_rejected(self, db, tmp_path):
        img_dir = tmp_path / "images"
        lbl_dir = tmp_path / "labels"
        img_dir.mkdir()
        lbl_dir.mkdir()

        _create_test_image(img_dir / "img1.png")
        (lbl_dir / "img1.txt").write_text("0 0.5 0.5\n", encoding="utf-8")  # only 3 tokens

        _, dataset_id = _setup_db_and_dataset(db, tmp_path)
        with pytest.raises(YoloValidationError, match="expected 5 tokens"):
            ingest_yolo_dataset(tmp_path, dataset_id, db)
