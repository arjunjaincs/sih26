"""
Ingestion tests: image directory format.

Tests that:
  - A valid image directory produces correct Sample records
  - SHA-256, pHash, dHash are computed from actual image data
  - Dimensions and file sizes are recorded accurately
  - Different input images produce different hashes (anti-fake)
  - Identical input images produce identical SHA-256 (determinism)
  - Empty directories are handled correctly
  - Unsupported file types are ignored
  - Invalid images fail according to the fail-closed policy

No finding or risk assessment is produced in this phase.
No hardcoded hashes. No fixture-driven results.
"""

from pathlib import Path

import pytest
from PIL import Image

from backend.domain.enums import DatasetFormat
from backend.infra.db import open_db, DatasetRepository, SampleRepository
from backend.infra.ingestion import (
    IngestionError,
    IngestionResult,
    ingest_image_directory,
    register_dataset,
)
from backend.infra.crypto import hash_file
from backend.domain.entities import Assessment
from backend.infra.db import AssessmentRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png(path: Path, width: int = 40, height: int = 40, color: str = "red") -> Path:
    img = Image.new("RGB", (width, height), color=color)
    img.save(path, format="PNG")
    return path


def _make_jpeg(path: Path, width: int = 40, height: int = 40, color: str = "blue") -> Path:
    img = Image.new("RGB", (width, height), color=color)
    img.save(path, format="JPEG", quality=90)
    return path


def _setup_assessment_and_dataset(db, tmp_path, fmt=DatasetFormat.IMAGE_DIR):
    """Create a minimal assessment + dataset and return (assessment_id, dataset_id, conn)."""
    a = Assessment(title="Test ingestion")
    AssessmentRepository(db).insert(a)
    asset, dataset = register_dataset(
        assessment_id=a.assessment_id,
        name="test_dataset",
        source_path=tmp_path,
        fmt=fmt,
        conn=db,
    )
    return a.assessment_id, dataset.dataset_id


# ---------------------------------------------------------------------------
# Basic directory ingestion
# ---------------------------------------------------------------------------

class TestImageDirectoryIngestion:
    def test_empty_directory_returns_zero_samples(self, db, tmp_path):
        img_dir = tmp_path / "empty"
        img_dir.mkdir()
        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)

        result = ingest_image_directory(img_dir, dataset_id, db)

        assert isinstance(result, IngestionResult)
        assert result.samples_ingested == 0
        assert result.samples_skipped == 0

    def test_single_png_produces_one_sample(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "cat.png")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        result = ingest_image_directory(img_dir, dataset_id, db)

        assert result.samples_ingested == 1
        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert len(samples) == 1

    def test_multiple_images_all_ingested(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "a.png", color="red")
        _make_png(img_dir / "b.png", color="green")
        _make_jpeg(img_dir / "c.jpg", color="blue")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        result = ingest_image_directory(img_dir, dataset_id, db)

        assert result.samples_ingested == 3
        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert len(samples) == 3

    def test_file_names_preserved(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "image_001.png")
        _make_jpeg(img_dir / "image_002.jpg")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        names = {s.file_name for s in samples}
        assert names == {"image_001.png", "image_002.jpg"}


# ---------------------------------------------------------------------------
# Hash correctness
# ---------------------------------------------------------------------------

class TestHashCorrectness:
    def test_sha256_matches_actual_file(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        img_path = _make_png(img_dir / "verify.png")
        expected_sha256 = hash_file(img_path)

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert len(samples) == 1
        assert samples[0].sha256 == expected_sha256

    def test_identical_files_produce_identical_sha256(self, db, tmp_path):
        """Two identical image files must produce the same SHA-256."""
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        img = Image.new("RGB", (20, 20), color="yellow")
        img.save(img_dir / "copy_a.png", format="PNG")
        # Save exact same image bytes to second file
        import shutil
        shutil.copy(img_dir / "copy_a.png", img_dir / "copy_b.png")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = {s.file_name: s for s in SampleRepository(db).list_by_dataset(dataset_id)}
        assert samples["copy_a.png"].sha256 == samples["copy_b.png"].sha256

    def test_different_images_produce_different_sha256(self, db, tmp_path):
        """Different image files must produce different SHA-256."""
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "red.png", color="red")
        _make_png(img_dir / "blue.png", color="blue")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = {s.file_name: s for s in SampleRepository(db).list_by_dataset(dataset_id)}
        assert samples["red.png"].sha256 != samples["blue.png"].sha256

    def test_phash_is_present(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "img.png")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert samples[0].phash is not None
        assert len(samples[0].phash) > 0

    def test_dhash_is_present(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "img.png")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert samples[0].dhash is not None

    def test_structurally_different_images_have_different_phash(self, db, tmp_path):
        """
        Perceptual hash measures image structure (spatial frequency via DCT).
        A solid-color image and a horizontal gradient have clearly different
        spatial structure and produce different pHash values.

        Note: solid-color images of different colors produce the SAME pHash
        because pHash operates on luminance structure, not absolute color.
        This is correct behavior for a perceptual hash — it is tested here
        only to confirm our hashing code actually runs on real pixel data.
        """
        img_dir = tmp_path / "ds"
        img_dir.mkdir()

        # Solid white — all pixels identical, all DCT AC components ≈ 0
        _make_png(img_dir / "solid.png", width=64, height=64, color="white")

        # Horizontal gradient — strong low-frequency spatial component
        import numpy as np
        gradient = np.tile(np.arange(64, dtype=np.uint8), (64, 1))
        rgb = np.stack([gradient, gradient, gradient], axis=-1)
        from PIL import Image as PILImage
        PILImage.fromarray(rgb).save(img_dir / "gradient.png", format="PNG")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = {s.file_name: s for s in SampleRepository(db).list_by_dataset(dataset_id)}
        assert samples["solid.png"].phash != samples["gradient.png"].phash, (
            "Solid white and horizontal gradient must have different perceptual hashes"
        )


# ---------------------------------------------------------------------------
# Metadata correctness
# ---------------------------------------------------------------------------

class TestMetadataCorrectness:
    def test_dimensions_correct(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "sized.png", width=120, height=80)

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert samples[0].width == 120
        assert samples[0].height == 80

    def test_file_size_correct(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        img_path = _make_png(img_dir / "sized.png")
        actual_size = img_path.stat().st_size

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        assert samples[0].file_size_bytes == actual_size

    def test_dataset_sample_count_updated(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        for i in range(4):
            _make_png(img_dir / f"img{i}.png")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        dataset = DatasetRepository(db).get(dataset_id)
        assert dataset.sample_count == 4

    def test_no_image_bytes_in_samples(self, db, tmp_path):
        """Verify that sample records do not store raw pixel data."""
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "img.png", width=500, height=500)

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        ingest_image_directory(img_dir, dataset_id, db)

        samples = SampleRepository(db).list_by_dataset(dataset_id)
        s = samples[0]
        # Sample has no pixel data field at all
        assert not hasattr(s, "pixels")
        assert not hasattr(s, "image_data")
        # The sha256 is just a 64-char hex string, not image bytes
        assert len(s.sha256) == 64


# ---------------------------------------------------------------------------
# Unsupported files
# ---------------------------------------------------------------------------

class TestUnsupportedFiles:
    def test_txt_file_ignored(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        (img_dir / "notes.txt").write_text("not an image")
        _make_png(img_dir / "real.png")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        result = ingest_image_directory(img_dir, dataset_id, db)

        # txt is not a supported extension — only the PNG is ingested
        assert result.samples_ingested == 1

    def test_json_file_ignored(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        (img_dir / "annotations.json").write_text("{}")
        _make_jpeg(img_dir / "photo.jpg")

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        result = ingest_image_directory(img_dir, dataset_id, db)

        assert result.samples_ingested == 1


# ---------------------------------------------------------------------------
# Fail-closed / skip policy
# ---------------------------------------------------------------------------

class TestFailPolicy:
    def test_corrupt_image_fails_ingestion_by_default(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "good.png")
        # A .jpg file that is actually garbage — not a valid image
        (img_dir / "bad.jpg").write_bytes(b"not an image at all " * 10)

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)

        with pytest.raises(IngestionError):
            ingest_image_directory(img_dir, dataset_id, db)

    def test_corrupt_image_skipped_with_flag(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        _make_png(img_dir / "good.png")
        (img_dir / "bad.jpg").write_bytes(b"garbage bytes " * 10)

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)
        result = ingest_image_directory(
            img_dir, dataset_id, db, skip_invalid_images=True
        )

        assert result.samples_ingested == 1
        assert result.samples_skipped == 1
        assert len(result.errors) == 1
        assert "bad.jpg" in result.errors[0].file_name

    def test_oversized_image_fails_by_default(self, db, tmp_path):
        img_dir = tmp_path / "ds"
        img_dir.mkdir()
        img = _make_png(img_dir / "big.png", width=64, height=64)

        _, dataset_id = _setup_assessment_and_dataset(db, img_dir)

        with pytest.raises(IngestionError):
            ingest_image_directory(
                img_dir, dataset_id, db, max_image_size_bytes=10  # 10 bytes — way too small
            )

    def test_not_a_directory_raises_value_error(self, db, tmp_path):
        not_dir = tmp_path / "file.txt"
        not_dir.write_text("text")
        _, dataset_id = _setup_assessment_and_dataset(db, tmp_path)

        with pytest.raises(ValueError):
            ingest_image_directory(not_dir, dataset_id, db)


# ---------------------------------------------------------------------------
# Anti-fake: different datasets produce different results
# ---------------------------------------------------------------------------

class TestAntiFake:
    def test_two_different_datasets_produce_different_samples(self, tmp_path):
        """
        The ingestion output must differ for different input datasets.
        This test proves that results are not hardcoded or fixture-driven.
        """
        from backend.infra.config import PramaanConfig
        from backend.infra.db import open_db

        config_a = PramaanConfig(data_dir=tmp_path / "db_a")
        config_b = PramaanConfig(data_dir=tmp_path / "db_b")
        db_a = open_db(config_a.db_path)
        db_b = open_db(config_b.db_path)

        dir_a = tmp_path / "dataset_a"
        dir_b = tmp_path / "dataset_b"
        dir_a.mkdir()
        dir_b.mkdir()

        # Dataset A: red and green images
        _make_png(dir_a / "img1.png", color="red")
        _make_png(dir_a / "img2.png", color="green")

        # Dataset B: completely different image (blue and yellow)
        _make_png(dir_b / "img1.png", color="blue")
        _make_png(dir_b / "img3.png", color="yellow")

        a = Assessment(title="DS A")
        AssessmentRepository(db_a).insert(a)
        asset_a, ds_a = register_dataset(
            a.assessment_id, "ds_a", dir_a, DatasetFormat.IMAGE_DIR, db_a
        )

        b = Assessment(title="DS B")
        AssessmentRepository(db_b).insert(b)
        asset_b, ds_b = register_dataset(
            b.assessment_id, "ds_b", dir_b, DatasetFormat.IMAGE_DIR, db_b
        )

        ingest_image_directory(dir_a, ds_a.dataset_id, db_a)
        ingest_image_directory(dir_b, ds_b.dataset_id, db_b)

        samples_a = SampleRepository(db_a).list_by_dataset(ds_a.dataset_id)
        samples_b = SampleRepository(db_b).list_by_dataset(ds_b.dataset_id)

        hashes_a = {s.sha256 for s in samples_a}
        hashes_b = {s.sha256 for s in samples_b}

        # The two datasets have different images → different hashes
        assert hashes_a != hashes_b, (
            "ANTI-FAKE FAILURE: different input datasets produced identical sample hashes"
        )
