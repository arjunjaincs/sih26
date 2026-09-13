"""
PRAMAAN v1 Production Release Packaging Tool

Assembles the final standalone, offline Windows desktop distributable into release/PRAMAAN/
with bundled portable Python 3.14 runtime, static frontend SPA, Electron shell, and demo fixtures.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_DIR = REPO_ROOT / "release" / "PRAMAAN"
PYTHON_BASE = Path(r"C:\Users\ss\AppData\Local\Programs\Python\Python314")
VENV_DIR = REPO_ROOT / ".venv"
SITE_PACKAGES_SRC = VENV_DIR / "Lib" / "site-packages"
ELECTRON_DIST = REPO_ROOT / "node_modules" / "electron" / "dist"

# Packages to exclude from the release site-packages
EXCLUDE_PACKAGES = {
    "_pytest",
    "pytest",
    "pytest_asyncio",
    "mypy",
    "mypyc",
    "ruff",
    "pip",
    "setuptools",
    "distutils",
    "_distutils_hack",
    "tests",
}


def log(msg: str) -> None:
    print(f"[PRAMAAN Release Builder] {msg}", flush=True)


def clean_release_dir() -> None:
    log(f"Preparing release directory: {RELEASE_DIR}")
    if RELEASE_DIR.exists():
        log("Removing previous release directory...")
        shutil.rmtree(RELEASE_DIR, ignore_errors=True)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)


def package_electron() -> None:
    log("Packaging Electron runtime...")
    if not ELECTRON_DIST.is_dir():
        raise RuntimeError(f"Electron distribution not found at {ELECTRON_DIST}")

    for item in ELECTRON_DIST.iterdir():
        target = RELEASE_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    # Rename electron.exe to PRAMAAN.exe
    electron_exe = RELEASE_DIR / "electron.exe"
    pramaan_exe = RELEASE_DIR / "PRAMAAN.exe"
    if electron_exe.exists():
        if pramaan_exe.exists():
            pramaan_exe.unlink()
        electron_exe.rename(pramaan_exe)
        log("Renamed electron.exe -> PRAMAAN.exe")

    # Remove default_app.asar to ensure Electron boots resources/app
    default_asar = RELEASE_DIR / "resources" / "default_app.asar"
    if default_asar.exists():
        default_asar.unlink()
        log("Removed default_app.asar")


def package_app_code() -> None:
    log("Packaging Electron application files...")
    app_target = RELEASE_DIR / "resources" / "app"
    app_target.mkdir(parents=True, exist_ok=True)

    # Copy package.json
    shutil.copy2(REPO_ROOT / "package.json", app_target / "package.json")

    # Copy electron/ directory
    electron_target = app_target / "electron"
    electron_target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "electron" / "main.cjs", electron_target / "main.cjs")
    shutil.copy2(REPO_ROOT / "electron" / "preload.cjs", electron_target / "preload.cjs")


def package_python_runtime() -> None:
    log("Assembling portable Python 3.14 runtime...")
    py_target = RELEASE_DIR / "resources" / "backend" / "python"
    py_target.mkdir(parents=True, exist_ok=True)

    # 1. Base Python binaries and DLLs
    binaries = [
        "python.exe",
        "python3.dll",
        "python314.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
    ]
    for b in binaries:
        src = PYTHON_BASE / b
        if src.exists():
            shutil.copy2(src, py_target / b)
        else:
            log(f"Warning: {b} not found in {PYTHON_BASE}")

    # 2. Python DLLs folder
    dlls_target = py_target / "DLLs"
    if (PYTHON_BASE / "DLLs").exists():
        shutil.copytree(PYTHON_BASE / "DLLs", dlls_target, dirs_exist_ok=True)

    # 3. Python standard library
    lib_target = py_target / "Lib"
    lib_target.mkdir(parents=True, exist_ok=True)

    # Copy standard library files from base Python
    base_lib = PYTHON_BASE / "Lib"
    for item in base_lib.iterdir():
        if item.name.lower() in ("test", "distutils", "ensurepip", "site-packages"):
            continue
        dest = lib_target / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    # 4. Production site-packages from .venv
    site_packages_target = lib_target / "site-packages"
    site_packages_target.mkdir(parents=True, exist_ok=True)

    log("Copying production dependencies from virtualenv...")
    for item in SITE_PACKAGES_SRC.iterdir():
        name = item.name
        # Skip dev tools, wheel caches, pytest, mypy, ruff, editable links
        if any(name.startswith(ex) or name.lower().startswith(ex) for ex in EXCLUDE_PACKAGES):
            continue
        if name.endswith(".whl") or name.startswith("__editable__"):
            continue
        if name == "__pycache__":
            continue

        dest = site_packages_target / name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    log("Portable Python runtime assembled.")


def package_backend_source() -> None:
    log("Packaging backend application modules...")
    backend_target = RELEASE_DIR / "resources" / "backend" / "backend"
    backend_target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        REPO_ROOT / "backend",
        backend_target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )


def package_data_and_frontend() -> None:
    log("Packaging deterministic demo corpus fixtures...")
    corpus_target = RELEASE_DIR / "resources" / "backend" / "data" / "corpus"
    corpus_target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        REPO_ROOT / "data" / "corpus",
        corpus_target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__")
    )

    log("Packaging static production frontend...")
    frontend_dist_target = RELEASE_DIR / "resources" / "backend" / "frontend" / "dist"
    frontend_dist_target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        REPO_ROOT / "frontend" / "dist",
        frontend_dist_target,
        dirs_exist_ok=True
    )


def create_judge_readme() -> None:
    log("Generating Judge README.txt...")
    readme_content = """================================================================================
  PRAMAAN v1 — EVIDENCE BEFORE TRUST
  Offline Integrity Assurance Workstation for Computer Vision Data & Models
================================================================================

DISTRIBUTABLE APPLICATION INSTRUCTIONS FOR SIH JUDGES & EVALUATORS

1. HOW TO LAUNCH
   - Double click 'PRAMAAN.exe' (or run 'start-pramaan.bat').
   - PRAMAAN starts automatically as a native desktop application.
   - All backend services and forensic algorithms run locally on 127.0.0.1:8000.
   - NO Python installation is required.
   - NO Node.js or Vite installation is required.
   - NO browser is required.
   - NO administrative privileges required.

2. STRICT OFFLINE / AIR-GAP OPERATION
   - PRAMAAN operates 100% offline with zero cloud or Internet dependencies.
   - Zero external requests, zero analytics, zero update checks.
   - All cryptographic verifications (Ed25519) and SHA-256 hash chains run locally.
   - AI Analyst Copilot is explicitly optional and disabled by default.

3. EVALUATION WORKFLOW & DEMO PRESETS
   PRAMAAN includes 5 deterministic, authentic demo presets for instant evaluation:
   
   1. Clean Reference Baseline:
      - Validates untampered ONNX candidate against reference baseline.
      - 0 defects, Risk: NONE, Confidence: HIGH.
      
   2. Dataset Duplicates & Collisions:
      - Detects exact byte duplicates and DCT perceptual near-duplicate clusters.
      - Risk: HIGH, Detectors: DI-01.
      
   3. Parameter Tampering (NaN/Inf):
      - Discovers parameter corruption, NaN weights, and activation instability.
      - Risk: CRITICAL, Detectors: MI-02, MI-03.
      
   4. Trojan Shortcut Convergence:
      - Exposes backdoor trigger anomaly and activation distribution shift.
      - Risk: CRITICAL, Detectors: MI-05, DI-03.
      
   5. Cryptographic Inference Provenance:
      - Verifies tamper-evident Ed25519 digital signature and input digest attestation.
      - Status: VERIFIED, Risk: NONE.

4. EXPORTS & REPORTS
   - Machine-Readable Structured JSON: Full assurance package with zero path leaks.
   - Cryptographic PDF Report: Multi-page executive summary with SHA-256 fingerprinting.
   - Audit Trail Export: Verifiable append-only event ledger.
   - Saved Reports and exports are stored locally in your user profile:
     %APPDATA%\\PRAMAAN\\data

5. RESTART & PERSISTENCE
   - Assessments persist in an embedded SQLite database (%APPDATA%\\PRAMAAN\\data\\pramaan.db).
   - Closing and reopening PRAMAAN.exe preserves all assessment history.

================================================================================
"""
    readme_path = RELEASE_DIR / "README.txt"
    readme_path.write_text(readme_content, encoding="utf-8")

    # Convenience launcher script
    bat_content = """@echo off
cd /d "%~dp0"
start "" PRAMAAN.exe
"""
    (RELEASE_DIR / "start-pramaan.bat").write_text(bat_content, encoding="utf-8")


def smoke_test_bundled_runtime() -> None:
    log("Running smoke test on bundled Python runtime...")
    python_exe = RELEASE_DIR / "resources" / "backend" / "python" / "python.exe"
    backend_dir = RELEASE_DIR / "resources" / "backend"

    env = {
        **os.environ,
        "PYTHONHOME": str(python_exe.parent),
        "PYTHONPATH": str(backend_dir),
    }

    test_cmd = [
        str(python_exe),
        "-c",
        (
            "import sys; "
            "import torch; "
            "import onnxruntime; "
            "import scipy; "
            "import numpy; "
            "import fastapi; "
            "import reportlab; "
            "import cryptography; "
            "from backend.api.app import app; "
            "print('SUCCESS: Bundled runtime loaded all core dependencies cleanly!')"
        ),
    ]

    res = subprocess.run(test_cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        log(f"Smoke test failed!\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
        raise RuntimeError("Bundled Python runtime failed validation smoke test.")
    log(res.stdout.strip())


def main() -> None:
    log("=================================================================")
    log("  PRAMAAN v1 — PHASE 27 FINAL WINDOWS RELEASE PACKAGING")
    log("=================================================================")
    clean_release_dir()
    package_electron()
    package_app_code()
    package_python_runtime()
    package_backend_source()
    package_data_and_frontend()
    create_judge_readme()
    smoke_test_bundled_runtime()
    log("=================================================================")
    log(f"RELEASE BUILD COMPLETE: {RELEASE_DIR}")
    log("=================================================================")


if __name__ == "__main__":
    main()
