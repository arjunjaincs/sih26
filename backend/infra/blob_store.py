"""
PRAMAAN content-addressed blob store.

Files are stored under:
    <blob_dir>/<aa>/<bb>/<sha256hex>

where <aa> and <bb> are the first two byte-pairs of the hash (directory
sharding to avoid very large flat directories).

Storing by SHA-256 guarantees:
  - Identical files are stored once (deduplication)
  - Content integrity is implicit (path is the hash)
  - No naming collisions
"""

from __future__ import annotations

import shutil
from pathlib import Path


class BlobStore:
    """Content-addressed filesystem storage for PRAMAAN artifacts."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _blob_path(self, sha256: str) -> Path:
        """
        Derive the filesystem path for a given SHA-256 hex digest.

        Layout: <root>/<first2>/<next2>/<full64hex>
        """
        if len(sha256) < 4:
            raise ValueError(f"SHA-256 digest too short: {sha256!r}")
        return self._root / sha256[:2] / sha256[2:4] / sha256

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_bytes(self, data: bytes, sha256: str) -> Path:
        """
        Write *data* into the blob store under *sha256*.

        If the blob already exists (identical content), the write is skipped.
        Returns the path of the stored blob.
        """
        dest = self._blob_path(sha256)
        if dest.exists():
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def store_file(self, src: Path, sha256: str) -> Path:
        """
        Copy the file at *src* into the blob store under *sha256*.

        Uses shutil.copy2 to preserve metadata.
        Returns the path of the stored blob.
        """
        dest = self._blob_path(sha256)
        if dest.exists():
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def retrieve(self, sha256: str) -> bytes:
        """
        Read and return the bytes of the blob identified by *sha256*.

        Raises FileNotFoundError if the blob is not present.
        """
        path = self._blob_path(sha256)
        if not path.exists():
            raise FileNotFoundError(f"Blob not found: {sha256}")
        return path.read_bytes()

    def exists(self, sha256: str) -> bool:
        """Return True if the blob identified by *sha256* is stored."""
        return self._blob_path(sha256).exists()

    def blob_path(self, sha256: str) -> Path:
        """Return the expected filesystem path for a blob (may not exist)."""
        return self._blob_path(sha256)
