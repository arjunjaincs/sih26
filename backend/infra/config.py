"""
PRAMAAN configuration.

All runtime configuration for PRAMAAN V1.  Loaded once at startup and
passed into components via dependency injection — no global config singletons.

Default values are designed for local development.  Override by setting
environment variables with the PRAMAAN_ prefix or by supplying a config dict.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PramaanConfig:
    """
    Immutable configuration record for PRAMAAN V1.

    All paths are resolved to absolute Paths at construction time so that
    relative-path issues are caught early.
    """

    # Root data directory — all persistent PRAMAAN data lives here
    data_dir: Path = field(default_factory=lambda: Path("pramaan_data").resolve())

    # SQLite database file
    @property
    def db_path(self) -> Path:
        return self.data_dir / "pramaan.db"

    # Content-addressed blob store root
    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "blobs"

    # Ed25519 key files
    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"

    @property
    def private_key_path(self) -> Path:
        return self.keys_dir / "signing_key.pem"

    @property
    def public_key_path(self) -> Path:
        return self.keys_dir / "signing_key.pub"

    # File ingestion limits
    max_image_size_bytes: int = 50 * 1024 * 1024        # 50 MB
    max_model_size_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB
    max_image_dimension: int = 8192                       # pixels per side
    max_dataset_images: int = 100_000

    # Perceptual hash duplicate detection defaults
    phash_threshold: int = 10   # Hamming-distance bits (pHash)
    dhash_threshold: int = 10   # Hamming-distance bits (dHash)

    # PRAMAAN version — embedded in manifests and assessments
    pramaan_version: str = "1.0.0"


def load_config() -> PramaanConfig:
    """
    Load configuration from environment variables.

    Supported env vars (all optional — defaults apply if absent):
      PRAMAAN_DATA_DIR            Path to the data directory
      PRAMAAN_MAX_IMAGE_MB        Max image size in megabytes
      PRAMAAN_MAX_MODEL_GB        Max model size in gigabytes
      PRAMAAN_PHASH_THRESHOLD     pHash Hamming-distance threshold
    """
    kwargs: dict = {}

    if data_dir := os.environ.get("PRAMAAN_DATA_DIR"):
        kwargs["data_dir"] = Path(data_dir).resolve()

    if max_img_mb := os.environ.get("PRAMAAN_MAX_IMAGE_MB"):
        kwargs["max_image_size_bytes"] = int(max_img_mb) * 1024 * 1024

    if max_model_gb := os.environ.get("PRAMAAN_MAX_MODEL_GB"):
        kwargs["max_model_size_bytes"] = int(max_model_gb) * 1024 * 1024 * 1024

    if phash_thr := os.environ.get("PRAMAAN_PHASH_THRESHOLD"):
        kwargs["phash_threshold"] = int(phash_thr)

    return PramaanConfig(**kwargs)
