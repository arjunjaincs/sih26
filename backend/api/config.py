"""
PRAMAAN API runtime configuration.

Configuration is read from environment variables at startup.
All values have safe, offline-first defaults so the server starts
with zero environment setup.

Environment variables
---------------------
PRAMAAN_DB_PATH
    Absolute path to the SQLite database file.
    Default: <repo-root>/data/pramaan.db

PRAMAAN_CORS_ORIGINS
    Comma-separated list of allowed CORS origins.
    Default: http://localhost:3000,http://localhost:5173

PRAMAAN_TRUSTED_ASSET_ROOTS
    Comma-separated list of absolute directory prefixes that are
    allowed as dataset/model sources. An API-supplied path must start
    with one of these prefixes (after resolving symlinks).
    Default: empty (all absolute paths allowed -- restrict in production)

PRAMAAN_MAX_DATASET_SIZE_MB
    Per-image file size limit forwarded to the ingestion pipeline.
    Default: 50 (MB)

PRAMAAN_MAX_MODEL_SIZE_MB
    Model file size limit. Default: 2048 (MB)
"""

from __future__ import annotations

import os
from pathlib import Path


def _get_db_path() -> Path:
    raw = os.environ.get("PRAMAAN_DB_PATH", "")
    if raw:
        return Path(raw)
    # Default: <repo-root>/data/pramaan.db
    # This file is at backend/api/config.py — resolve two levels up.
    repo_root = Path(__file__).parent.parent.parent
    db_dir = repo_root / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "pramaan.db"


def _get_cors_origins() -> list[str]:
    raw = os.environ.get("PRAMAAN_CORS_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]


def _get_trusted_roots() -> list[Path]:
    raw = os.environ.get("PRAMAAN_TRUSTED_ASSET_ROOTS", "")
    if raw.strip():
        return [Path(p.strip()) for p in raw.split(",") if p.strip()]
    return []  # Empty = no prefix restriction (dev mode)


def _get_int(var: str, default: int) -> int:
    try:
        return int(os.environ.get(var, default))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Singleton config object
# ---------------------------------------------------------------------------

class _Config:
    """Lazily-evaluated runtime configuration."""

    @property
    def db_path(self) -> Path:
        return _get_db_path()

    @property
    def blob_dir(self) -> Path:
        raw = os.environ.get("PRAMAAN_BLOB_DIR", "")
        if raw:
            p = Path(raw)
            p.mkdir(parents=True, exist_ok=True)
            return p
        p = self.db_path.parent / "blobs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cors_origins(self) -> list[str]:
        return _get_cors_origins()

    @property
    def trusted_asset_roots(self) -> list[Path]:
        return _get_trusted_roots()

    @property
    def max_dataset_size_mb(self) -> int:
        return _get_int("PRAMAAN_MAX_DATASET_SIZE_MB", 50)

    @property
    def max_model_size_mb(self) -> int:
        return _get_int("PRAMAAN_MAX_MODEL_SIZE_MB", 2048)


settings = _Config()
