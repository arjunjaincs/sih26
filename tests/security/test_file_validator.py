"""
Security tests for PRAMAAN file validator.

Tests that the validator correctly rejects:
  - Path traversal (POSIX and Windows forms)
  - Absolute paths (POSIX, Windows drive, UNC)
  - Storage-root escapes after resolution
  - Oversized files
  - Missing files
  - Unsafe filenames

Critically: a rejected input must NEVER silently succeed.
"""

from pathlib import Path

import pytest

from backend.infra.file_validator import (
    ValidationCode,
    validate_path,
    validate_absolute_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    root = tmp_path / "storage"
    root.mkdir()
    return root


@pytest.fixture
def safe_file(storage_root: Path) -> Path:
    f = storage_root / "image001.jpg"
    f.write_bytes(b"FAKE IMAGE BYTES")
    return f


# ---------------------------------------------------------------------------
# Valid path — must pass
# ---------------------------------------------------------------------------

class TestValidPaths:
    def test_simple_filename_accepted(self, storage_root, safe_file):
        result = validate_path("image001.jpg", storage_root)
        assert result.ok is True
        assert result.code == ValidationCode.OK
        assert result.resolved_path is not None
        assert result.resolved_path.name == "image001.jpg"

    def test_resolved_path_is_absolute(self, storage_root, safe_file):
        result = validate_path("image001.jpg", storage_root)
        assert result.resolved_path.is_absolute()

    def test_size_within_limit_accepted(self, storage_root, safe_file):
        result = validate_path("image001.jpg", storage_root, max_size_bytes=1024)
        assert result.ok is True

    def test_must_exist_false_allows_nonexistent(self, storage_root):
        result = validate_path(
            "future_image.jpg", storage_root, must_exist=False
        )
        assert result.ok is True


# ---------------------------------------------------------------------------
# Path traversal — must be rejected
# ---------------------------------------------------------------------------

class TestPathTraversal:
    def test_posix_dotdot_rejected(self, storage_root):
        result = validate_path("../../etc/passwd", storage_root, must_exist=False)
        assert result.ok is False
        assert result.code in (
            ValidationCode.PATH_TRAVERSAL,
            ValidationCode.ABSOLUTE_PATH,
            ValidationCode.STORAGE_ROOT_ESCAPE,
        )

    def test_single_dotdot_rejected(self, storage_root):
        result = validate_path("../outside.jpg", storage_root, must_exist=False)
        assert result.ok is False

    def test_embedded_dotdot_rejected(self, storage_root):
        result = validate_path("subdir/../../../etc/passwd", storage_root, must_exist=False)
        assert result.ok is False

    def test_windows_backslash_traversal_rejected(self, storage_root):
        result = validate_path("..\\..\\Windows\\System32", storage_root, must_exist=False)
        assert result.ok is False

    def test_url_encoded_dotdot_is_treated_as_literal(self, storage_root):
        # %2e%2e is NOT decoded here — it is a literal string with percent signs.
        # The validator sees '%2e%2e' as a filename, not '..'.
        # If the OS somehow resolves it as '..', containment check catches it.
        result = validate_path("%2e%2e/passwd", storage_root, must_exist=False)
        # This may or may not pass depending on OS. What matters is it never
        # escapes the storage root silently — check that if it passes, the
        # resolved path is still inside the root.
        if result.ok:
            assert str(result.resolved_path).startswith(str(storage_root.resolve()))

    def test_null_byte_traversal_rejected(self, storage_root):
        # Null bytes in paths are treated as unsafe filenames.
        result = validate_path("image\x00.jpg", storage_root, must_exist=False)
        assert result.ok is False


# ---------------------------------------------------------------------------
# Absolute path injection — must be rejected
# ---------------------------------------------------------------------------

class TestAbsolutePaths:
    def test_posix_root_rejected(self, storage_root):
        result = validate_path("/etc/passwd", storage_root, must_exist=False)
        assert result.ok is False
        assert result.code == ValidationCode.ABSOLUTE_PATH

    def test_windows_drive_letter_rejected(self, storage_root):
        result = validate_path("C:\\Windows\\System32\\cmd.exe", storage_root, must_exist=False)
        assert result.ok is False

    def test_windows_drive_forward_slash_rejected(self, storage_root):
        result = validate_path("C:/Windows/System32", storage_root, must_exist=False)
        assert result.ok is False

    def test_unc_path_rejected(self, storage_root):
        result = validate_path("\\\\server\\share\\file", storage_root, must_exist=False)
        assert result.ok is False

    def test_tilde_home_is_relative_not_absolute(self, storage_root):
        # '~' is NOT an absolute path at the validator level (shell doesn't
        # expand it here). It is a relative path with an unusual name.
        # It may be rejected for other reasons (unsafe chars or not-found),
        # but not for being absolute.
        result = validate_path("~/secret", storage_root, must_exist=False)
        if not result.ok:
            assert result.code != ValidationCode.ABSOLUTE_PATH


# ---------------------------------------------------------------------------
# Storage-root containment
# ---------------------------------------------------------------------------

class TestStorageRootContainment:
    def test_symlink_escape_detected(self, tmp_path: Path):
        """A symlink that points outside the root must be detected if followed."""
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("secret")

        # Create a symlink inside root pointing outside
        link = root / "escape_link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Symlinks not supported on this system")

        # Validate the symlink name — the resolved path will escape the root
        result = validate_path("escape_link.txt", root)
        # Either the escape is caught by containment check, or the file
        # is accepted (resolved inside root). On Windows, symlinks may not
        # resolve across drives. The important property: if ok, path is contained.
        if result.ok:
            assert str(result.resolved_path).startswith(str(root.resolve()))


# ---------------------------------------------------------------------------
# File size limit
# ---------------------------------------------------------------------------

class TestFileSizeLimit:
    def test_file_within_limit_accepted(self, storage_root):
        f = storage_root / "small.jpg"
        f.write_bytes(b"X" * 100)
        result = validate_path("small.jpg", storage_root, max_size_bytes=200)
        assert result.ok is True

    def test_file_at_limit_accepted(self, storage_root):
        f = storage_root / "exact.jpg"
        f.write_bytes(b"X" * 200)
        result = validate_path("exact.jpg", storage_root, max_size_bytes=200)
        assert result.ok is True

    def test_file_over_limit_rejected(self, storage_root):
        f = storage_root / "big.jpg"
        f.write_bytes(b"X" * 201)
        result = validate_path("big.jpg", storage_root, max_size_bytes=200)
        assert result.ok is False
        assert result.code == ValidationCode.FILE_TOO_LARGE

    def test_error_message_contains_filename(self, storage_root):
        f = storage_root / "toobig.jpg"
        f.write_bytes(b"X" * 500)
        result = validate_path("toobig.jpg", storage_root, max_size_bytes=100)
        assert result.ok is False
        assert "toobig.jpg" in result.message or "500" in result.message


# ---------------------------------------------------------------------------
# Missing files
# ---------------------------------------------------------------------------

class TestMissingFiles:
    def test_nonexistent_file_rejected_by_default(self, storage_root):
        result = validate_path("ghost.jpg", storage_root)
        assert result.ok is False
        assert result.code == ValidationCode.FILE_NOT_FOUND

    def test_directory_rejected_as_not_a_file(self, storage_root):
        d = storage_root / "subdir"
        d.mkdir()
        result = validate_path("subdir", storage_root)
        assert result.ok is False
        assert result.code == ValidationCode.NOT_A_FILE


# ---------------------------------------------------------------------------
# validate_absolute_path
# ---------------------------------------------------------------------------

class TestValidateAbsolutePath:
    def test_existing_file_accepted(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"data")
        result = validate_absolute_path(f)
        assert result.ok is True

    def test_nonexistent_rejected(self, tmp_path):
        result = validate_absolute_path(tmp_path / "missing.bin")
        assert result.ok is False
        assert result.code == ValidationCode.FILE_NOT_FOUND

    def test_directory_rejected(self, tmp_path):
        result = validate_absolute_path(tmp_path)
        assert result.ok is False
        assert result.code == ValidationCode.NOT_A_FILE

    def test_oversized_rejected(self, tmp_path):
        f = tmp_path / "big.bin"
        f.write_bytes(b"X" * 300)
        result = validate_absolute_path(f, max_size_bytes=100)
        assert result.ok is False
        assert result.code == ValidationCode.FILE_TOO_LARGE
