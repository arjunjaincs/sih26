"""
PRAMAAN secure file validation.

All externally-supplied paths and files pass through this module before
any further processing.  The guiding principle is fail-closed: ambiguous
or dangerous inputs are rejected explicitly; no silent sanitization that
might hide an attack.

Threat model addressed:
  - Path traversal (../../etc/passwd, ..\\..\\Windows\\...)
  - Absolute-path injection (/etc/passwd, C:\\Windows\\...)
  - Storage-root escape
  - Oversized file upload
  - Extension-name mismatch (validated by image_loader separately)

V1 Policy:
  - Paths are validated against a configured storage root.
  - Absolute paths are always rejected.
  - Paths containing '..' components are always rejected.
  - The resolved path must remain inside the storage root.
  - File size is checked against a configurable limit before reading.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------

class ValidationCode(str, Enum):
    """Structured reason codes for file-validation failures."""

    OK = "ok"
    PATH_TRAVERSAL = "path_traversal"
    ABSOLUTE_PATH = "absolute_path"
    STORAGE_ROOT_ESCAPE = "storage_root_escape"
    FILE_TOO_LARGE = "file_too_large"
    FILE_NOT_FOUND = "file_not_found"
    NOT_A_FILE = "not_a_file"
    UNSAFE_FILENAME = "unsafe_filename"


@dataclass(frozen=True)
class ValidationResult:
    """Result of a file-validation check."""

    ok: bool
    code: ValidationCode
    message: str
    resolved_path: Path | None = None  # Set only when ok=True


# ---------------------------------------------------------------------------
# Filename safety
# ---------------------------------------------------------------------------

# Characters that are problematic in filenames across common filesystems.
_UNSAFE_CHARS = frozenset('<>:"|?*\x00')

# Windows reserved device names (case-insensitive) that must not be filenames.
_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})


def _is_safe_filename(name: str) -> bool:
    """
    Return True if *name* is a safe bare filename (no path separators).

    Checks:
      - Not empty
      - No path separators
      - No null bytes or shell-special characters
      - Not a Windows reserved device name
    """
    if not name or not name.strip():
        return False
    if "/" in name or "\\" in name:
        return False
    if any(c in _UNSAFE_CHARS for c in name):
        return False
    stem = name.rsplit(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        return False
    return True


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

def _contains_traversal(raw: str) -> bool:
    """
    Return True if *raw* contains any path-traversal component.

    Checks both POSIX and Windows path representations so that inputs like
    '..\\..\\secret' are caught even on Linux.
    """
    # Check via PurePosixPath parts
    try:
        parts_posix = PurePosixPath(raw).parts
        if any(p == ".." for p in parts_posix):
            return True
    except Exception:
        return True

    # Check via PureWindowsPath parts (catches backslash forms)
    try:
        parts_win = PureWindowsPath(raw).parts
        if any(p == ".." for p in parts_win):
            return True
    except Exception:
        return True

    # Explicit string checks for edge cases
    raw_normalised = raw.replace("\\", "/")
    if "../" in raw_normalised or raw_normalised.startswith(".."):
        return True

    return False


def _is_absolute_raw(raw: str) -> bool:
    """Return True if *raw* looks like an absolute path."""
    stripped = raw.strip()
    # POSIX absolute
    if stripped.startswith("/"):
        return True
    # Windows absolute: C:\, D:/, UNC \\server
    if len(stripped) >= 2 and stripped[1] == ":" :
        return True
    if stripped.startswith("\\\\"):
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_path(
    raw_name: str,
    storage_root: Path,
    *,
    max_size_bytes: int | None = None,
    must_exist: bool = True,
) -> ValidationResult:
    """
    Validate that *raw_name* is a safe relative path inside *storage_root*.

    Parameters
    ----------
    raw_name:
        The untrusted filename or relative path string from external input.
    storage_root:
        Absolute directory that the resolved path must remain inside.
    max_size_bytes:
        If set, reject the file if its size exceeds this value.
    must_exist:
        If True (default), reject if the resolved path does not exist as a file.

    Returns
    -------
    ValidationResult with ok=True and resolved_path set on success,
    or ok=False with a descriptive code and message on failure.
    """

    # --- Absolute-path check ------------------------------------------------
    if _is_absolute_raw(raw_name):
        return ValidationResult(
            ok=False,
            code=ValidationCode.ABSOLUTE_PATH,
            message=f"Absolute paths are not permitted: {raw_name!r}",
        )

    # --- Traversal check (before any resolution) ----------------------------
    if _contains_traversal(raw_name):
        return ValidationResult(
            ok=False,
            code=ValidationCode.PATH_TRAVERSAL,
            message=f"Path traversal detected in: {raw_name!r}",
        )

    # --- Filename safety (bare name only) ------------------------------------
    bare_name = Path(raw_name).name
    if not _is_safe_filename(bare_name):
        return ValidationResult(
            ok=False,
            code=ValidationCode.UNSAFE_FILENAME,
            message=f"Unsafe filename: {bare_name!r}",
        )

    # --- Resolve and containment check ---------------------------------------
    try:
        resolved = (storage_root / raw_name).resolve()
        root_resolved = storage_root.resolve()
    except Exception as exc:
        return ValidationResult(
            ok=False,
            code=ValidationCode.PATH_TRAVERSAL,
            message=f"Path resolution failed: {exc}",
        )

    # The resolved path must be inside (or equal to) the storage root.
    # Use os.path.commonpath for reliable cross-platform containment check.
    try:
        common = os.path.commonpath([str(root_resolved), str(resolved)])
        if common != str(root_resolved):
            return ValidationResult(
                ok=False,
                code=ValidationCode.STORAGE_ROOT_ESCAPE,
                message=(
                    f"Resolved path escapes storage root: "
                    f"{resolved} is not under {root_resolved}"
                ),
            )
    except ValueError:
        # commonpath raises ValueError on Windows for paths on different drives
        return ValidationResult(
            ok=False,
            code=ValidationCode.STORAGE_ROOT_ESCAPE,
            message=f"Path {raw_name!r} is on a different drive than the storage root",
        )

    # --- Existence and type checks -------------------------------------------
    if must_exist:
        if not resolved.exists():
            return ValidationResult(
                ok=False,
                code=ValidationCode.FILE_NOT_FOUND,
                message=f"File not found: {resolved}",
            )
        if not resolved.is_file():
            return ValidationResult(
                ok=False,
                code=ValidationCode.NOT_A_FILE,
                message=f"Path is not a regular file: {resolved}",
            )

    # --- File size check -----------------------------------------------------
    if max_size_bytes is not None and resolved.exists() and resolved.is_file():
        size = resolved.stat().st_size
        if size > max_size_bytes:
            return ValidationResult(
                ok=False,
                code=ValidationCode.FILE_TOO_LARGE,
                message=(
                    f"File size {size:,} bytes exceeds limit "
                    f"{max_size_bytes:,} bytes: {resolved.name}"
                ),
            )

    return ValidationResult(
        ok=True,
        code=ValidationCode.OK,
        message="",
        resolved_path=resolved,
    )


def validate_absolute_path(
    path: Path,
    *,
    max_size_bytes: int | None = None,
) -> ValidationResult:
    """
    Validate a *Path* object that is already absolute (e.g., produced internally).

    Use this when PRAMAAN itself has constructed the path (e.g., during directory
    traversal) and containment relative to a root has already been verified.
    Only checks existence, file type, and size.
    """
    if not path.exists():
        return ValidationResult(
            ok=False,
            code=ValidationCode.FILE_NOT_FOUND,
            message=f"File not found: {path}",
        )
    if not path.is_file():
        return ValidationResult(
            ok=False,
            code=ValidationCode.NOT_A_FILE,
            message=f"Path is not a regular file: {path}",
        )
    if max_size_bytes is not None:
        size = path.stat().st_size
        if size > max_size_bytes:
            return ValidationResult(
                ok=False,
                code=ValidationCode.FILE_TOO_LARGE,
                message=(
                    f"File size {size:,} bytes exceeds limit "
                    f"{max_size_bytes:,} bytes: {path.name}"
                ),
            )
    return ValidationResult(
        ok=True,
        code=ValidationCode.OK,
        message="",
        resolved_path=path,
    )
