"""
PRAMAAN safe image loading.

All image files ingested by PRAMAAN pass through this module.
External image data is treated as untrusted — a crafted image can exploit
decoders, consume excessive memory, or embed malicious payloads.

Threat model addressed:
  - Decompression bombs (excessively large decoded images)
  - Corrupt/truncated images crashing the process
  - Non-image files renamed to .jpg/.png
  - Images with extreme dimensions

V1 Policy:
  - File size is checked before opening (via file_validator).
  - Pillow's Image.MAX_IMAGE_PIXELS limit is enforced.
  - Width, height, and total pixel count are checked after minimal decode.
  - The image is fully decoded to verify it is not truncated/corrupt.
  - Only JPEG, PNG, WEBP, BMP formats are accepted.
  - The actual format is read from the file header, not the filename extension.

Unsupported files (wrong format, corrupt data, truncated) produce a typed
ImageLoadError — they never raise unhandled exceptions into callers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PIL import Image, UnidentifiedImageError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported formats
# ---------------------------------------------------------------------------

# Pillow format strings (uppercase) that PRAMAAN V1 accepts.
# Extend here as support is validated.
SUPPORTED_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP", "BMP"})


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

class ImageLoadCode(str, Enum):
    OK = "ok"
    UNSUPPORTED_FORMAT = "unsupported_format"
    CORRUPT_IMAGE = "corrupt_image"
    DIMENSION_EXCEEDED = "dimension_exceeded"
    PIXEL_COUNT_EXCEEDED = "pixel_count_exceeded"
    DECODE_FAILED = "decode_failed"
    NOT_AN_IMAGE = "not_an_image"


@dataclass(frozen=True)
class ImageLoadError(Exception):
    """Raised when an image cannot be safely loaded."""

    code: ImageLoadCode
    message: str
    path: Path | None = None

    def __str__(self) -> str:
        prefix = f"[{self.code.value}]"
        if self.path:
            return f"{prefix} {self.path.name}: {self.message}"
        return f"{prefix} {self.message}"


@dataclass(frozen=True)
class ImageMetadata:
    """
    Safe metadata extracted from a successfully loaded image.

    Callers receive this object; no Pillow Image object leaks out of the loader.
    """

    width: int
    height: int
    format: str          # Pillow format string, e.g. "JPEG", "PNG"
    mode: str            # Pillow mode string, e.g. "RGB", "L"
    file_size_bytes: int
    path: Path


# ---------------------------------------------------------------------------
# Limits (override via PramaanConfig; defaults match config.py)
# ---------------------------------------------------------------------------

_DEFAULT_MAX_BYTES = 50 * 1024 * 1024   # 50 MB
_DEFAULT_MAX_DIM = 8192                  # pixels per side
_DEFAULT_MAX_PIXELS = 8192 * 8192       # total pixel count cap


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_image_metadata(
    path: Path,
    *,
    max_size_bytes: int = _DEFAULT_MAX_BYTES,
    max_dimension: int = _DEFAULT_MAX_DIM,
    max_pixels: int = _DEFAULT_MAX_PIXELS,
) -> ImageMetadata:
    """
    Safely open *path*, validate it, and return image metadata.

    The image is fully decoded to confirm it is not truncated or corrupt.
    No image data is returned to the caller — only the metadata struct.

    Parameters
    ----------
    path:
        Absolute path to the image file.  Must already have passed
        file_validator checks (size limit, existence).
    max_size_bytes:
        Maximum allowed file size in bytes.
    max_dimension:
        Maximum allowed width or height in pixels.
    max_pixels:
        Maximum allowed total pixel count (width × height).

    Raises
    ------
    ImageLoadError
        On any validation or decode failure, with a specific ImageLoadCode.
    """

    # --- File size pre-check (belt-and-suspenders; file_validator may have
    #     already checked, but image_loader enforces its own limit) ----------
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise ImageLoadError(
            code=ImageLoadCode.DECODE_FAILED,
            message=f"Cannot stat file: {exc}",
            path=path,
        )

    if file_size > max_size_bytes:
        raise ImageLoadError(
            code=ImageLoadCode.DECODE_FAILED,
            message=(
                f"File size {file_size:,} bytes exceeds limit "
                f"{max_size_bytes:,} bytes"
            ),
            path=path,
        )

    # --- Enforce Pillow's decompression-bomb limit --------------------------
    # Set max pixels globally for this decode.  We use a context-manager
    # pattern via try/finally to restore the original value.
    original_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = max_pixels

    try:
        # Open in a context manager; this reads the header but does not
        # decompress the full image yet.
        try:
            img = Image.open(path)
        except UnidentifiedImageError:
            raise ImageLoadError(
                code=ImageLoadCode.NOT_AN_IMAGE,
                message="File is not a recognized image format",
                path=path,
            )
        except Exception as exc:
            raise ImageLoadError(
                code=ImageLoadCode.CORRUPT_IMAGE,
                message=f"Image open failed: {exc}",
                path=path,
            )

        # --- Format check (from file header, not filename) ------------------
        fmt = img.format or ""
        if fmt not in SUPPORTED_FORMATS:
            img.close()
            raise ImageLoadError(
                code=ImageLoadCode.UNSUPPORTED_FORMAT,
                message=(
                    f"Format {fmt!r} is not supported. "
                    f"Supported: {sorted(SUPPORTED_FORMATS)}"
                ),
                path=path,
            )

        # --- Dimension check (header-only, cheap) ---------------------------
        width, height = img.size
        if width > max_dimension or height > max_dimension:
            img.close()
            raise ImageLoadError(
                code=ImageLoadCode.DIMENSION_EXCEEDED,
                message=(
                    f"Image dimensions {width}×{height} exceed limit "
                    f"{max_dimension}×{max_dimension}"
                ),
                path=path,
            )

        pixel_count = width * height
        if pixel_count > max_pixels:
            img.close()
            raise ImageLoadError(
                code=ImageLoadCode.PIXEL_COUNT_EXCEEDED,
                message=(
                    f"Pixel count {pixel_count:,} exceeds limit {max_pixels:,}"
                ),
                path=path,
            )

        mode = img.mode

        # --- Full decode verification ----------------------------------------
        # img.verify() is destructive — the image cannot be used after verify().
        # We re-open and call load() instead to ensure the full pixel data
        # can be decoded without error.
        img.close()
        try:
            with Image.open(path) as img2:
                img2.load()  # Forces full decompression; catches truncated images
        except Exception as exc:
            raise ImageLoadError(
                code=ImageLoadCode.CORRUPT_IMAGE,
                message=f"Image decode failed (truncated or corrupt): {exc}",
                path=path,
            )

    finally:
        Image.MAX_IMAGE_PIXELS = original_max_pixels

    return ImageMetadata(
        width=width,
        height=height,
        format=fmt,
        mode=mode,
        file_size_bytes=file_size,
        path=path,
    )
