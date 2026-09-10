"""
Persistence tests: ingestion → SQLite round-trip.

Tests that:
  - Dataset record is created and has correct fields
  - Sample records persist with correct dataset linkage
  - Hash values survive database round-trip unchanged
  - Metadata (dimensions, file size, labels) survives round-trip
  - Samples can be listed by dataset
  - Image bytes are NOT stored in SQLite
"""

import json
from pathlib import Path

import pytest
from PIL import Image

from backend.domain.entities import Assessment
from backend.domain.enums import DatasetFormat
from backend.infra.crypto import hash_file
from backend.infra.db import (
    AssessmentRepository,
    DatasetRepository,
    SampleRepository,
)
from backend.infra.ingestion import (
    ingest_image_directory,
    ingest_coco_dataset,
    register_dataset,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png(path: Path, width: int = 24, height: int = 24, color: str = "red") -> Path:
    Image.new("RGB", (width, height), color=color).save(path, format="PNG")
    return path


def _write_coco(path: Path, images_dir: Path, names: list[str]) -> Path:
    data = {
        "images": [
            {"id": i + 1, "file_name": n, "width": 24, "height": 24}
            for i, n in enumerate(names)
        ],
        "annotations": [],
        "categories": [],
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _create_assessment(db) -> str:
    a = Assessment(title="Persistence test")
    AssessmentRepository(db).insert(a)
    return a.assessment_id


# ---------------------------------------------------------------------------
# Dataset record persistence
# ---------------------------------------------------------------------------

class TestDatasetPersistence:
    def test_dataset_record_created(self, db, tmp_path):
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        aid = _create_assessment(db)

        asset, dataset = register_dataset(
            aid, "my_dataset", img_dir, DatasetFormat.IMAGE_DIR, db
        )

        retrieved = DatasetRepository(db).get(dataset.dataset_id)
        assert retrieved is not None
        assert retrieved.dataset_id == dataset.dataset_id
        assert retrieved.assessment_id == aid
        assert retrieved.format == DatasetFormat.IMAGE_DIR
        assert str(img_dir) in retrieved.source_path

    def test_sample_count_updated_after_ingestion(self, db, tmp_path):
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        for i in range(3):
            _make_png(img_dir / f"img{i}.png")

        aid = _create_assessment(db)
        asset, dataset = register_dataset(
            aid, "count_test", img_dir, DatasetFormat.IMAGE_DIR, db
        )
        ingest_image_directory(img_dir, dataset.dataset_id, db)

        ds = DatasetRepository(db).get(dataset.dataset_id)
        assert ds.sample_count == 3


# ---------------------------------------------------------------------------
# Sample record persistence
# ---------------------------------------------------------------------------

class TestSamplePersistence:
    def test_samples_linked_to_correct_dataset(self, db, tmp_path):
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        _make_png(img_dir / "img.png")

        aid = _create_assessment(db)
        asset, dataset = register_dataset(
            aid, "link_test", img_dir, DatasetFormat.IMAGE_DIR, db
        )
        ingest_image_directory(img_dir, dataset.dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset.dataset_id)
        assert len(samples) == 1
        assert samples[0].dataset_id == dataset.dataset_id

    def test_sha256_survives_roundtrip(self, db, tmp_path):
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        img_path = _make_png(img_dir / "hash_check.png")
        expected_hash = hash_file(img_path)

        aid = _create_assessment(db)
        asset, dataset = register_dataset(
            aid, "hash_rt", img_dir, DatasetFormat.IMAGE_DIR, db
        )
        ingest_image_directory(img_dir, dataset.dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset.dataset_id)
        assert samples[0].sha256 == expected_hash

    def test_phash_survives_roundtrip(self, db, tmp_path):
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        _make_png(img_dir / "img.png")

        aid = _create_assessment(db)
        asset, dataset = register_dataset(
            aid, "phash_rt", img_dir, DatasetFormat.IMAGE_DIR, db
        )
        ingest_image_directory(img_dir, dataset.dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset.dataset_id)
        assert samples[0].phash is not None
        # pHash is stored as hex — must be re-readable
        assert int(samples[0].phash, 16) >= 0

    def test_dimensions_survive_roundtrip(self, db, tmp_path):
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        _make_png(img_dir / "sized.png", width=88, height=44)

        aid = _create_assessment(db)
        asset, dataset = register_dataset(
            aid, "dim_rt", img_dir, DatasetFormat.IMAGE_DIR, db
        )
        ingest_image_directory(img_dir, dataset.dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset.dataset_id)
        assert samples[0].width == 88
        assert samples[0].height == 44

    def test_file_size_survives_roundtrip(self, db, tmp_path):
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        img_path = _make_png(img_dir / "sized.png")
        actual_size = img_path.stat().st_size

        aid = _create_assessment(db)
        asset, dataset = register_dataset(
            aid, "size_rt", img_dir, DatasetFormat.IMAGE_DIR, db
        )
        ingest_image_directory(img_dir, dataset.dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset.dataset_id)
        assert samples[0].file_size_bytes == actual_size

    def test_labels_survive_roundtrip(self, db, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        _make_png(images_dir / "cat.png")

        coco_data = {
            "images": [{"id": 1, "file_name": "cat.png", "width": 24, "height": 24}],
            "categories": [{"id": 1, "name": "cat"}, {"id": 2, "name": "indoor"}],
            "annotations": [
                {"image_id": 1, "category_id": 1},
                {"image_id": 1, "category_id": 2},
            ],
        }
        json_path = tmp_path / "anns.json"
        json_path.write_text(json.dumps(coco_data), encoding="utf-8")

        aid = _create_assessment(db)
        asset, dataset = register_dataset(
            aid, "label_rt", tmp_path, DatasetFormat.COCO_JSON, db
        )
        ingest_coco_dataset(json_path, images_dir, dataset.dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset.dataset_id)
        assert len(samples) == 1
        assert set(samples[0].labels) == {"cat", "indoor"}

    def test_empty_labels_stored_as_empty_list(self, db, tmp_path):
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        _make_png(img_dir / "unlabeled.png")

        aid = _create_assessment(db)
        asset, dataset = register_dataset(
            aid, "no_labels", img_dir, DatasetFormat.IMAGE_DIR, db
        )
        ingest_image_directory(img_dir, dataset.dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset.dataset_id)
        assert samples[0].labels == []

    def test_no_image_bytes_in_sqlite(self, db, tmp_path):
        """
        Verify that image pixel bytes are NOT stored in the SQLite samples table.
        The only image-derived data stored is: sha256, phash, dhash, and metadata.
        """
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        # Large image — if bytes were stored in SQLite, the DB would be very large
        _make_png(img_dir / "large.png", width=512, height=512)

        aid = _create_assessment(db)
        asset, dataset = register_dataset(
            aid, "no_bytes", img_dir, DatasetFormat.IMAGE_DIR, db
        )
        ingest_image_directory(img_dir, dataset.dataset_id, db)

        # DB file should be small — no image pixel data
        from backend.infra.config import PramaanConfig
        # Access the DB file via the connection's database attribute
        db_path_str = db.execute("PRAGMA database_list").fetchone()[2]
        db_size = Path(db_path_str).stat().st_size
        # A 512x512 PNG is ~100+ KB. SQLite overhead + metadata should be << 50 KB.
        assert db_size < 50_000, (
            f"DB size {db_size} bytes suggests image bytes may be stored in SQLite"
        )

    def test_multiple_datasets_independent(self, db, tmp_path):
        """Samples from different datasets do not mix."""
        dir_a = tmp_path / "ds_a"
        dir_b = tmp_path / "ds_b"
        dir_a.mkdir()
        dir_b.mkdir()

        _make_png(dir_a / "a1.png", color="red")
        _make_png(dir_b / "b1.png", color="blue")
        _make_png(dir_b / "b2.png", color="green")

        aid = _create_assessment(db)
        _, ds_a = register_dataset(aid, "A", dir_a, DatasetFormat.IMAGE_DIR, db)
        _, ds_b = register_dataset(aid, "B", dir_b, DatasetFormat.IMAGE_DIR, db)

        ingest_image_directory(dir_a, ds_a.dataset_id, db)
        ingest_image_directory(dir_b, ds_b.dataset_id, db)

        samples_a = SampleRepository(db).list_by_dataset(ds_a.dataset_id)
        samples_b = SampleRepository(db).list_by_dataset(ds_b.dataset_id)

        assert len(samples_a) == 1
        assert len(samples_b) == 2
        assert samples_a[0].file_name == "a1.png"
        names_b = {s.file_name for s in samples_b}
        assert names_b == {"b1.png", "b2.png"}
