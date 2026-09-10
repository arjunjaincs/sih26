"""
Security tests for PRAMAAN image loader.

Tests that the image loader correctly:
  - Loads valid JPEG and PNG
  - Rejects non-image files masquerading as images (extension spoofing)
  - Rejects corrupt/truncated images
  - Rejects images exceeding dimension or pixel limits
  - Returns correct metadata (width, height, format, size)
  - Never relies on the filename extension for format detection

All test images are generated programmatically using Pillow.
No external downloads. Fully offline.
"""

from pathlib import Path
import struct

import pytest
from PIL import Image

from backend.infra.image_loader import (
    ImageLoadCode,
    ImageLoadError,
    ImageMetadata,
    load_image_metadata,
    SUPPORTED_FORMATS,
)


# ---------------------------------------------------------------------------
# Test image generation helpers
# ---------------------------------------------------------------------------

def _make_png(path: Path, width: int = 64, height: int = 64, color: str = "red") -> Path:
    img = Image.new("RGB", (width, height), color=color)
    img.save(path, format="PNG")
    return path


def _make_jpeg(path: Path, width: int = 64, height: int = 64, color: str = "blue") -> Path:
    img = Image.new("RGB", (width, height), color=color)
    img.save(path, format="JPEG", quality=85)
    return path


def _make_webp(path: Path, width: int = 32, height: int = 32) -> Path:
    img = Image.new("RGB", (width, height), color="green")
    img.save(path, format="WEBP")
    return path


def _make_bmp(path: Path, width: int = 16, height: int = 16) -> Path:
    img = Image.new("RGB", (width, height), color="white")
    img.save(path, format="BMP")
    return path


def _make_corrupt_image(path: Path) -> Path:
    """Write random bytes that are not a valid image."""
    path.write_bytes(b"\xFF\xD8\xFF" + b"\xAB\xCD\xEF" * 50)  # Looks like JPEG header but broken
    return path


def _make_text_file_as_jpg(path: Path) -> Path:
    """A plain text file with a .jpg extension — classic extension spoofing."""
    path.write_text("This is not an image, just text pretending to be a JPEG.")
    return path


def _make_truncated_png(path: Path) -> Path:
    """A PNG with valid header but truncated data."""
    img = Image.new("RGB", (100, 100), color="purple")
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    full_bytes = buf.getvalue()
    # Keep only the first 50 bytes — enough for the header but not the data
    path.write_bytes(full_bytes[:50])
    return path


# ---------------------------------------------------------------------------
# Valid image loading
# ---------------------------------------------------------------------------

class TestValidImages:
    def test_load_valid_png(self, tmp_path):
        p = _make_png(tmp_path / "test.png", width=100, height=80)
        meta = load_image_metadata(p)
        assert isinstance(meta, ImageMetadata)
        assert meta.width == 100
        assert meta.height == 80
        assert meta.format == "PNG"
        assert meta.file_size_bytes == p.stat().st_size
        assert meta.path == p

    def test_load_valid_jpeg(self, tmp_path):
        p = _make_jpeg(tmp_path / "test.jpg", width=200, height=150)
        meta = load_image_metadata(p)
        assert meta.format == "JPEG"
        assert meta.width == 200
        assert meta.height == 150

    def test_load_valid_webp(self, tmp_path):
        p = _make_webp(tmp_path / "test.webp")
        meta = load_image_metadata(p)
        assert meta.format == "WEBP"

    def test_load_valid_bmp(self, tmp_path):
        p = _make_bmp(tmp_path / "test.bmp")
        meta = load_image_metadata(p)
        assert meta.format == "BMP"

    def test_file_size_matches_stat(self, tmp_path):
        p = _make_png(tmp_path / "size_check.png")
        meta = load_image_metadata(p)
        assert meta.file_size_bytes == p.stat().st_size
        assert meta.file_size_bytes > 0

    def test_mode_is_captured(self, tmp_path):
        p = _make_png(tmp_path / "mode.png")
        meta = load_image_metadata(p)
        assert meta.mode in ("RGB", "RGBA", "L")  # Pillow mode string


# ---------------------------------------------------------------------------
# Extension spoofing — format from header, not name
# ---------------------------------------------------------------------------

class TestExtensionSpoofing:
    def test_text_file_named_jpg_rejected(self, tmp_path):
        p = _make_text_file_as_jpg(tmp_path / "malicious.jpg")
        with pytest.raises(ImageLoadError) as exc_info:
            load_image_metadata(p)
        assert exc_info.value.code in (
            ImageLoadCode.NOT_AN_IMAGE,
            ImageLoadCode.CORRUPT_IMAGE,
            ImageLoadCode.UNSUPPORTED_FORMAT,
        )

    def test_png_named_jpg_loads_as_png(self, tmp_path):
        """A PNG file with .jpg extension should load with format=PNG."""
        png = tmp_path / "actually_a_png.jpg"
        _make_png(png)
        meta = load_image_metadata(png)
        assert meta.format == "PNG"

    def test_jpeg_named_png_loads_as_jpeg(self, tmp_path):
        jpeg = tmp_path / "actually_a_jpeg.png"
        _make_jpeg(jpeg)
        meta = load_image_metadata(jpeg)
        assert meta.format == "JPEG"


# ---------------------------------------------------------------------------
# Corrupt and truncated images
# ---------------------------------------------------------------------------

class TestCorruptImages:
    def test_corrupt_bytes_rejected(self, tmp_path):
        p = _make_corrupt_image(tmp_path / "corrupt.jpg")
        with pytest.raises(ImageLoadError) as exc_info:
            load_image_metadata(p)
        assert exc_info.value.code in (
            ImageLoadCode.NOT_AN_IMAGE,
            ImageLoadCode.CORRUPT_IMAGE,
            ImageLoadCode.UNSUPPORTED_FORMAT,
        )

    def test_truncated_png_rejected(self, tmp_path):
        p = _make_truncated_png(tmp_path / "truncated.png")
        with pytest.raises(ImageLoadError) as exc_info:
            load_image_metadata(p)
        assert exc_info.value.code in (
            ImageLoadCode.CORRUPT_IMAGE,
            ImageLoadCode.NOT_AN_IMAGE,
        )

    def test_empty_file_rejected(self, tmp_path):
        p = tmp_path / "empty.jpg"
        p.write_bytes(b"")
        with pytest.raises(ImageLoadError):
            load_image_metadata(p)

    def test_random_bytes_rejected(self, tmp_path):
        p = tmp_path / "random.png"
        p.write_bytes(bytes(range(256)) * 10)
        with pytest.raises(ImageLoadError):
            load_image_metadata(p)


# ---------------------------------------------------------------------------
# Dimension limits
# ---------------------------------------------------------------------------

class TestDimensionLimits:
    def test_image_within_limits_accepted(self, tmp_path):
        p = _make_png(tmp_path / "ok.png", width=100, height=100)
        meta = load_image_metadata(p, max_dimension=200)
        assert meta.width == 100

    def test_image_at_limit_accepted(self, tmp_path):
        p = _make_png(tmp_path / "at_limit.png", width=200, height=200)
        meta = load_image_metadata(p, max_dimension=200)
        assert meta.width == 200

    def test_image_over_width_limit_rejected(self, tmp_path):
        p = _make_png(tmp_path / "wide.png", width=300, height=50)
        with pytest.raises(ImageLoadError) as exc_info:
            load_image_metadata(p, max_dimension=200)
        assert exc_info.value.code == ImageLoadCode.DIMENSION_EXCEEDED

    def test_image_over_height_limit_rejected(self, tmp_path):
        p = _make_png(tmp_path / "tall.png", width=50, height=300)
        with pytest.raises(ImageLoadError) as exc_info:
            load_image_metadata(p, max_dimension=200)
        assert exc_info.value.code == ImageLoadCode.DIMENSION_EXCEEDED

    def test_pixel_count_limit(self, tmp_path):
        # 100×100 = 10,000 pixels; limit to 5,000
        p = _make_png(tmp_path / "many_pixels.png", width=100, height=100)
        with pytest.raises(ImageLoadError) as exc_info:
            load_image_metadata(p, max_dimension=200, max_pixels=5000)
        assert exc_info.value.code == ImageLoadCode.PIXEL_COUNT_EXCEEDED

    def test_very_small_image_always_accepted(self, tmp_path):
        p = _make_png(tmp_path / "tiny.png", width=1, height=1)
        meta = load_image_metadata(p, max_dimension=8192)
        assert meta.width == 1
        assert meta.height == 1


# ---------------------------------------------------------------------------
# File size limit
# ---------------------------------------------------------------------------

class TestFileSizeLimit:
    def test_file_over_size_limit_rejected(self, tmp_path):
        p = _make_png(tmp_path / "big.png", width=200, height=200)
        file_size = p.stat().st_size
        # Set limit just below actual size
        with pytest.raises(ImageLoadError):
            load_image_metadata(p, max_size_bytes=file_size - 1)

    def test_file_at_size_limit_accepted(self, tmp_path):
        p = _make_png(tmp_path / "ok_size.png", width=10, height=10)
        file_size = p.stat().st_size
        meta = load_image_metadata(p, max_size_bytes=file_size)
        assert meta.width == 10


# ---------------------------------------------------------------------------
# Metadata correctness
# ---------------------------------------------------------------------------

class TestMetadataCorrectness:
    def test_dimensions_are_exact(self, tmp_path):
        for w, h in [(1, 1), (32, 64), (128, 256)]:
            p = _make_png(tmp_path / f"img_{w}x{h}.png", width=w, height=h)
            meta = load_image_metadata(p)
            assert meta.width == w, f"Width mismatch for {w}x{h}"
            assert meta.height == h, f"Height mismatch for {w}x{h}"

    def test_supported_formats_match_module_constant(self, tmp_path):
        """Verify that each format in SUPPORTED_FORMATS actually loads."""
        makers = {
            "PNG": lambda p: _make_png(p),
            "JPEG": lambda p: _make_jpeg(p),
            "WEBP": lambda p: _make_webp(p),
            "BMP": lambda p: _make_bmp(p),
        }
        for fmt, maker in makers.items():
            assert fmt in SUPPORTED_FORMATS, f"{fmt} not in SUPPORTED_FORMATS"
            p = tmp_path / f"check.{fmt.lower()}"
            maker(p)
            meta = load_image_metadata(p)
            assert meta.format == fmt
