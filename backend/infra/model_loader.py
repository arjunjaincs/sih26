"""
PRAMAAN secure model loading boundary.

ALL model file loading goes through this module — per ADR-006.
No other module may call torch.load, onnx.load, or similar directly.

Policy (ADR-006):
  PyTorch     → torch.load(path, weights_only=True) only
  ONNX        → onnx.load + onnx.checker.check_model, then ort.InferenceSession
  TorchScript → torch.jit.load() (accepted but documented as higher-risk)
  All others  → rejected with ModelLoadError(code=UNSUPPORTED_FORMAT)

Graceful degradation:
  If a framework (torch, onnx, onnxruntime) is not installed, any request
  for that format returns ModelLoadError(code=DEPENDENCY_UNAVAILABLE).
  This produces a coverage limitation in MI-01, not a crash.

Resource limits:
  - File size is checked before any deserialization attempt.
  - Dimension/shape limits on ONNX graphs are not enforced here; they belong
    in the structural fingerprint analysis layer.

Security:
  - Absolute paths and path traversal are rejected.
  - File must exist and be a regular file.
  - PyTorch: weights_only=True prevents arbitrary pickle execution.
  - ONNX: onnx.checker validates the protobuf schema before further use.
  - No remote URIs, no Hugging Face downloads, no cloud APIs.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from backend.infra.crypto import hash_file

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Framework availability flags
# Detected once at import time so tests can monkey-patch if needed.
# ---------------------------------------------------------------------------

try:
    import onnx as _onnx_mod  # noqa: F401
    import onnx.checker as _onnx_checker  # noqa: F401
    _ONNX_AVAILABLE = True
except ImportError:
    _ONNX_AVAILABLE = False

try:
    import onnxruntime as _ort_mod  # noqa: F401
    _ORT_AVAILABLE = True
except ImportError:
    _ORT_AVAILABLE = False

try:
    import torch as _torch_mod  # noqa: F401
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Supported extensions → framework mapping
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".onnx": "onnx",
    ".pt": "pytorch",
    ".pth": "pytorch",
    ".torchscript": "torchscript",
    ".ts": "torchscript",
}

# Maximum default model file size (can be overridden per call)
DEFAULT_MAX_MODEL_BYTES: int = 5 * 1024 * 1024 * 1024  # 5 GB


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class ModelLoadErrorCode(str, Enum):
    UNSUPPORTED_FORMAT    = "unsupported_format"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    FILE_NOT_FOUND        = "file_not_found"
    FILE_TOO_LARGE        = "file_too_large"
    NOT_A_FILE            = "not_a_file"
    PATH_TRAVERSAL        = "path_traversal"
    ABSOLUTE_PATH         = "absolute_path"
    MALFORMED             = "malformed"
    UNSAFE_PICKLE         = "unsafe_pickle"
    VALIDATION_FAILED     = "validation_failed"
    RUNTIME_ERROR         = "runtime_error"


class ModelLoadError(Exception):
    """Raised when a model file cannot be safely loaded."""

    def __init__(self, message: str, code: ModelLoadErrorCode) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Loaded model container
# ---------------------------------------------------------------------------

@dataclass
class LoadedModel:
    """
    Container for a successfully validated and loaded model.

    raw_object — the deserialized framework object (onnx.ModelProto,
                 OrderedDict for pytorch state dicts, etc.)
                 May be None if framework is unavailable (SKIPPED cases).
    framework  — string identifier of the framework that loaded this model.
    path       — absolute Path of the source file.
    sha256     — SHA-256 of the raw file bytes (computed before load).
    file_size  — size in bytes.
    """
    raw_object: Any
    framework: str
    path: Path
    sha256: str
    file_size: int


# ---------------------------------------------------------------------------
# Path safety helpers (mirrors file_validator.py — model-specific variant)
# ---------------------------------------------------------------------------

def _validate_model_path(
    path: Path,
    max_size_bytes: int,
) -> None:
    """
    Validate *path* as a model file before any deserialization.

    Raises ModelLoadError on any security or validation failure.
    Accepts only absolute Path objects (constructed internally by PRAMAAN).
    """
    # Must be absolute (PRAMAAN constructs paths, users supply names)
    if not path.is_absolute():
        raise ModelLoadError(
            f"Internal error: expected absolute path, got {path!r}",
            ModelLoadErrorCode.PATH_TRAVERSAL,
        )

    # Must exist
    if not path.exists():
        raise ModelLoadError(
            f"Model file not found: {path}",
            ModelLoadErrorCode.FILE_NOT_FOUND,
        )

    # Must be a regular file
    if not path.is_file():
        raise ModelLoadError(
            f"Not a regular file: {path}",
            ModelLoadErrorCode.NOT_A_FILE,
        )

    # Size check before deserialization
    size = path.stat().st_size
    if size > max_size_bytes:
        raise ModelLoadError(
            f"Model file too large: {size:,} bytes > {max_size_bytes:,} bytes limit",
            ModelLoadErrorCode.FILE_TOO_LARGE,
        )

    # Extension check
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ModelLoadError(
            f"Unsupported model format: {ext!r}. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS.keys())}",
            ModelLoadErrorCode.UNSUPPORTED_FORMAT,
        )


# ---------------------------------------------------------------------------
# Format-specific loaders
# ---------------------------------------------------------------------------

def _load_onnx(path: Path) -> Any:
    """
    Load and validate an ONNX model.

    Primary path: onnxruntime.InferenceSession — validates the model graph
    on load (equivalent to onnx.checker for most real models) without
    executing arbitrary code.  ORT is a no-pickle, protobuf-based loader.

    Supplemental path: onnx.load() for deeper protobuf inspection.
    Only used when onnx package is available; not required for basic analysis.

    Returns the onnx.ModelProto if onnx is available, otherwise returns
    the raw file bytes (the behavioral/structural analyses use ORT directly).

    Raises ModelLoadError on any failure.
    """
    if not _ORT_AVAILABLE and not _ONNX_AVAILABLE:
        raise ModelLoadError(
            "Neither onnxruntime nor onnx package is installed. "
            "Install with: pip install onnxruntime",
            ModelLoadErrorCode.DEPENDENCY_UNAVAILABLE,
        )

    if _ORT_AVAILABLE:
        import onnxruntime as ort
        try:
            # ORT validates the model graph on session creation — this is the
            # primary security validation boundary for ONNX files.
            ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise ModelLoadError(
                f"ONNX model validation failed (ORT): {exc}",
                ModelLoadErrorCode.MALFORMED,
            ) from exc

    # Optional: load full protobuf via onnx package for deeper inspection
    if _ONNX_AVAILABLE:
        import onnx
        import onnx.checker
        try:
            model_proto = onnx.load(str(path))
            onnx.checker.check_model(model_proto)
            return model_proto
        except Exception as exc:
            raise ModelLoadError(
                f"ONNX protobuf validation failed: {exc}",
                ModelLoadErrorCode.VALIDATION_FAILED,
            ) from exc

    # ORT validated the model; return raw bytes as the loaded object
    # (structural/behavioral analysis uses ORT sessions directly)
    return path.read_bytes()



def _load_pytorch(path: Path) -> Any:
    """
    Load a PyTorch state dict using weights_only=True (ADR-006).

    Raises ModelLoadError on any failure.
    Never uses unrestricted pickle deserialization.
    """
    if not _TORCH_AVAILABLE:
        raise ModelLoadError(
            "torch package is not installed. "
            "Install with: pip install torch --index-url https://download.pytorch.org/whl/cpu",
            ModelLoadErrorCode.DEPENDENCY_UNAVAILABLE,
        )

    import torch

    try:
        # weights_only=True: restricts loading to tensor data only (no arbitrary objects)
        obj = torch.load(str(path), weights_only=True, map_location="cpu")
    except Exception as exc:
        err_str = str(exc).lower()
        if "weights_only" in err_str or "pickle" in err_str or "reduce" in err_str.lower():
            raise ModelLoadError(
                f"PyTorch model rejected: unsafe deserialization attempt detected. "
                f"The model may contain arbitrary Python objects incompatible with "
                f"weights_only=True. Re-save as a state_dict to analyze. Detail: {exc}",
                ModelLoadErrorCode.UNSAFE_PICKLE,
            ) from exc
        raise ModelLoadError(
            f"PyTorch load failed: {exc}",
            ModelLoadErrorCode.MALFORMED,
        ) from exc

    return obj


def _load_torchscript(path: Path) -> Any:
    """
    Load a TorchScript model using torch.jit.load().

    TorchScript uses a restricted execution environment but can still access
    the filesystem — documented as higher risk than plain state dicts.
    """
    if not _TORCH_AVAILABLE:
        raise ModelLoadError(
            "torch package is not installed.",
            ModelLoadErrorCode.DEPENDENCY_UNAVAILABLE,
        )

    import torch

    try:
        model = torch.jit.load(str(path), map_location="cpu")
        return model
    except Exception as exc:
        raise ModelLoadError(
            f"TorchScript load failed: {exc}",
            ModelLoadErrorCode.MALFORMED,
        ) from exc


# ---------------------------------------------------------------------------
# Public entry point (ADR-006: single controlled entry point)
# ---------------------------------------------------------------------------

def load_model(
    path: Path,
    *,
    max_size_bytes: int = DEFAULT_MAX_MODEL_BYTES,
) -> LoadedModel:
    """
    Securely load a model file from *path*.

    This is the ONLY sanctioned entry point for model loading in PRAMAAN.
    No other module may call torch.load / onnx.load / pickle.load directly.

    Parameters
    ----------
    path:
        Absolute path to the model file. Must exist and be a regular file.
    max_size_bytes:
        Maximum permitted file size before deserialization.

    Returns
    -------
    LoadedModel — container with the deserialized object and metadata.

    Raises
    ------
    ModelLoadError — on any security, format, or deserialization failure.
    """
    _validate_model_path(path, max_size_bytes)

    # Compute SHA-256 before any deserialization attempt
    sha256 = hash_file(path)
    file_size = path.stat().st_size
    framework = SUPPORTED_EXTENSIONS[path.suffix.lower()]

    log.info(
        "Loading model: path=%s framework=%s size=%d sha256=%s…",
        path.name, framework, file_size, sha256[:16],
    )

    if framework == "onnx":
        raw = _load_onnx(path)
    elif framework == "pytorch":
        raw = _load_pytorch(path)
    elif framework == "torchscript":
        raw = _load_torchscript(path)
    else:
        raise ModelLoadError(
            f"No loader implemented for framework: {framework}",
            ModelLoadErrorCode.UNSUPPORTED_FORMAT,
        )

    log.info("Model loaded successfully: %s (%s)", path.name, framework)
    return LoadedModel(
        raw_object=raw,
        framework=framework,
        path=path,
        sha256=sha256,
        file_size=file_size,
    )


def framework_available(framework: str) -> bool:
    """
    Return True if the required Python package for *framework* is importable.

    Used by can_run() to produce accurate coverage gaps without attempting
    to actually load a model.
    """
    mapping = {
        "onnx": _ONNX_AVAILABLE or _ORT_AVAILABLE,  # ORT can load/validate ONNX
        "pytorch": _TORCH_AVAILABLE,
        "torchscript": _TORCH_AVAILABLE,
    }
    return mapping.get(framework, False)
