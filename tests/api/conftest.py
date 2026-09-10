"""
Shared fixtures for API tests.

Uses FastAPI TestClient with an isolated temporary database per test,
injecting the DB dependency so each test gets its own clean state.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.deps import get_db
from backend.infra.db import open_db


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    """Fresh isolated DB per test."""
    return open_db(tmp_path / "test_api.db")


@pytest.fixture
def client(db: sqlite3.Connection) -> TestClient:
    """
    TestClient with the DB dependency overridden.

    Every test gets an isolated in-process database — no shared state.
    The real assessment engine runs inside the test process.
    """
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def image_dir(tmp_path: Path) -> Path:
    """Minimal image directory — 3 distinct images."""
    from PIL import Image
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    for i in range(3):
        img = Image.new("RGB", (64, 64), color=(i * 80, i * 40, 255 - i * 80))
        img.save(img_dir / f"img_{i:03d}.jpg", "JPEG")
    return img_dir


@pytest.fixture
def image_dir_with_duplicates(tmp_path: Path) -> Path:
    """Image directory with one pair of exact duplicates."""
    from PIL import Image
    img_dir = tmp_path / "dup_images"
    img_dir.mkdir()
    img = Image.new("RGB", (64, 64), color=(100, 150, 200))
    img.save(img_dir / "original.jpg", "JPEG")
    img.save(img_dir / "duplicate.jpg", "JPEG")
    img2 = Image.new("RGB", (64, 64), color=(200, 100, 50))
    img2.save(img_dir / "unique.jpg", "JPEG")
    return img_dir


@pytest.fixture
def onnx_model(tmp_path: Path) -> Path:
    """Minimal valid ONNX model."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from detectors.onnx_writer import make_relu_model
    path = tmp_path / "relu.onnx"
    path.write_bytes(make_relu_model(input_shape=[1, 3]))
    return path
