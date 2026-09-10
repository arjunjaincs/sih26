"""
Shared pytest configuration and fixtures for PRAMAAN tests.
"""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.infra.config import PramaanConfig
from backend.infra.db import open_db
from backend.infra.blob_store import BlobStore


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """A temporary directory that is cleaned up after each test."""
    return tmp_path


@pytest.fixture
def config(tmp_path: Path) -> PramaanConfig:
    """A PramaanConfig pointing at a fresh temp directory."""
    return PramaanConfig(data_dir=tmp_path / "pramaan_data")


@pytest.fixture
def db(config: PramaanConfig) -> sqlite3.Connection:
    """An open SQLite connection with the PRAMAAN schema initialised."""
    return open_db(config.db_path)


@pytest.fixture
def blob_store(config: PramaanConfig) -> BlobStore:
    """A BlobStore backed by a fresh temp directory."""
    return BlobStore(config.blob_dir)
