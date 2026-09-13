# PRAMAAN

> **Evidence Before Trust.**
> Offline, evidence-based computer-vision integrity assurance for multi-contributor pipelines.

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.14-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-33.4.11-47848F?logo=electron)](https://electronjs.org)
[![React](https://img.shields.io/badge/React-18.3.1-61DAFB?logo=react)](https://react.dev)
[![Tests](https://img.shields.io/badge/Tests-988%20Backend%20%7C%20128%20Frontend%20PASS-brightgreen)](#automated-testing)
[![Air--Gap](https://img.shields.io/badge/Air--Gap-Validated%20Offline-success)](#air-gap--offline-validation)

---

## 1. Executive Overview

**PRAMAAN** is an air-gapped forensic workstation designed to establish mathematical, statistical, and cryptographic verification for computer vision assets before they enter mission-critical defense pipelines.

In multi-vendor, distributed AI workflows, models and datasets frequently pass through untrusted boundaries. Traditional security relies on subjective trust or simple file hashing—neither of which reveals if training samples are contaminated with poisoned triggers, if model weights have been corrupted with IEEE-754 non-finite anomalies, or if inference outputs were spoofed in transit.

PRAMAAN replaces subjective trust with **Evidence Before Trust**: every defect finding is backed by localized raw pixel coordinates, Hamming distance clusters, parameter tensors, and cryptographic digital signatures linked in a tamper-evident audit chain.

---

## 2. SIH 2026 Problem Statement

- **Problem ID:** `SIH26228`
- **Organization:** Ministry of Defence / Indian Army (DGIS)
- **Title:** *Trustworthy Computer Vision Integrity Assurance for Data, Models and Inference Outputs in Multi-Contributor Pipelines.*
- **Core Focus Areas:**
  1. **Training / Data Integrity:** Identifying exact duplicate images, perceptual near-duplicates, label mismatches, spatial trigger artifacts, covariate shift (OOD), and contributor concentration.
  2. **Model Integrity:** Verifying architecture fingerprints, IEEE-754 weight moment bounds, intermediate activation saturation, L2/cosine parameter drift against baseline references, and Trojan shortcut behavior.
  3. **Inference & Provenance Integrity:** Cryptographically binding model outputs to signed manifests via Ed25519 (RFC 8032) and enforcing nonce/timestamp replay protection.
  4. **Auditability & Traceability:** Recording every lifecycle event in a SHA-256 hash-linked audit ledger.
  5. **Air-Gapped Operation:** Functioning entirely offline without cloud dependencies, telemetry, or external network access.

---

## 3. Core Assurance Pipeline

PRAMAAN executes an immutable, deterministic evaluation pipeline:

```
INGEST → VALIDATE → IDENTIFY ASSETS → FINGERPRINT → PROFILE ACCESS
       → SELECT METHODS → EXECUTE → COLLECT EVIDENCE
       → CALCULATE RISK → CALCULATE CONFIDENCE → DETERMINE COVERAGE
       → GENERATE FINDINGS → AUDIT CHAIN → REPORT
```

1. **Ingest & Validate:** Validates asset bounds, MIME types, file sizes, and ZIP archives against path traversal attacks (Zip-Slip defense).
2. **Identify & Fingerprint:** Extracts cryptographic SHA-256 hashes, tensor shapes, and model topology.
3. **Profile Access & Select Methods:** Detects black-box vs. white-box access levels and activates compatible forensic detectors.
4. **Execute & Collect Evidence:** Executes deterministic detectors, capturing raw evidence items into a content-addressed `BlobStore`.
5. **Metric Triad Evaluation:** Decouples overall Risk, Confidence, and Coverage into independent, mathematically defined dimensions.
6. **Audit & Report:** Links all execution steps into a SHA-256 event chain and generates court-ready cryptographic PDF and machine-readable JSON reports.

---

## 4. Four Forensic Assurance Layers

PRAMAAN organizes its 11 canonical detectors across four foundational pillars:

| Assurance Layer | Scope & Objective | Access Requirements |
| :--- | :--- | :--- |
| **1. Dataset Integrity** | Scans training/validation images for duplication, label poisoning, spatial triggers, and contributor bias. | Black-Box (Images, COCO annotations, manifests) |
| **2. Model Integrity** | Evaluates neural network weights, activation stability, reference divergence, and Trojan shortcuts. | White-Box (ONNX executable graphs, PyTorch weights-only state dicts) |
| **3. Inference Provenance** | Verifies cryptographic attestations over input/output tensors and detects manifest replay attacks. | Cryptographic Manifest (Ed25519 signatures, input/output tensors) |
| **4. Audit & Traceability** | Preserves a chronological, hash-chained ledger of every system and assessment event. | System Ledger (SQLite WAL, SHA-256 chain) |

---

## 5. Canonical Detector Registry

PRAMAAN features **11 canonical forensic detectors**:

| Code | Canonical Detector ID | Name & Purpose | Primary Evidence Produced |
| :---: | :--- | :--- | :--- |
| **DI-01** | `data.integrity.di01_duplicates` | **Exact & Near-Duplicate Clustering:** Discovers byte collisions (SHA-256) and perceptual near-duplicates via DCT pHash Hamming distance clustering ($\le 10$). | Collision tables, perceptual hash Hamming matrices, duplicate image clusters. |
| **DI-02** | `data.integrity.di02_label_integrity` | **Label Consistency & Margin:** Evaluates label distribution and feature-space consistency using kNN distance margins. | Ambiguous/misannotated sample IDs, label entropy scores, margin deltas. |
| **DI-03** | `data.integrity.di03_trigger_anomaly` | **Spatial Trigger & Patch Artifacts:** Analyzes high-frequency residual anomalies and pixel bounding boxes for backdoor triggers. | Localized patch coordinates $[x, y, w, h]$, spectral frequency peaks, residual masks. |
| **DI-04** | `data.integrity.di04_ood_distribution` | **Covariate Shift & Distribution Drift:** Measures Wasserstein distance and covariate shift against baseline validation distributions. | Distribution histograms, Wasserstein drift distances, outlier sample lists. |
| **DI-05** | `data.integrity.di05_contributor_risk` | **Contributor Concentration:** Calculates Gini source concentration coefficients to detect disproportionate data ownership. | Gini imbalance coefficient, contributor contribution ratios, concentration alerts. |
| **MI-01** | `model.integrity.mi01_fingerprint` | **Architecture & Topology Fingerprint:** Computes SHA-256 digests of parameter bytes, operator schemas, and computational graphs. | Parameter byte hashes, layer node counts, operator compatibility manifests. |
| **MI-02** | `model.integrity.mi02_parameter_stats` | **Weight Moments & Parameter Corruption:** Evaluates IEEE-754 floating-point moments, non-finite values (`NaN`, `+Inf`, `-Inf`), and layer sparsity. | Non-finite tensor indices, layer weight moments (min, max, mean, std), sparsity ratios. |
| **MI-03** | `model.integrity.mi03_activation_stats` | **Activation Profiling & Saturation:** Passes calibrated deterministic probe inputs to monitor dead activations ($> 98\%$ zero) and saturation. | Per-layer activation summaries, dead activation counts, numerical clipping warnings. |
| **MI-04** | `model.integrity.mi04_reference_comparison` | **Reference Divergence & Weight Drift:** Computes cosine similarity, L2 weight distance, and behavioral divergence against baseline references. | L2 parameter delta matrices, cosine similarity metrics, max output divergence. |
| **MI-05** | `model.integrity.mi05_trigger_anomaly` | **Trojan Shortcut & Trigger Behavior:** Evaluates Attack Success Rate (ASR) spikes and spectral clustering on poisoned inputs. | Attack Success Rate ($0.0 - 1.0$), localized trigger patch artifacts, activation delta. |
| **PI-01** | `inference.provenance.pi01_integrity` | **Ed25519 Attestation & Replay Defense:** Validates RFC 8032 digital signatures over I/O digests and detects nonce/timestamp replay. | Digital signature validity status (`VERIFIED` / `INVALID`), nonce deduplication logs, I/O tensor match. |

---

## 6. Critical Assurance Semantics (ADR-003)

PRAMAAN adheres to strict, decoupled mathematical definitions:

1. **Risk, Confidence, and Coverage are Orthogonal:**
   - **Risk (`NONE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`):** The probability and operational severity of detected defects or adversarial compromise.
   - **Confidence (`LOW`, `MODERATE`, `HIGH`):** The statistical certainty and access depth of the measurement. Small datasets or black-box state dicts yield lower confidence, even if high risk is detected.
   - **Coverage ($0\% - 100\%$):** The fraction of applicable detectors that were executable given the supplied asset access level.
2. **No Composite "Trust Score":**
   - Compounding Risk, Confidence, and Coverage into a single percentage (e.g., "85% Trustworthy") is fundamentally unscientific and conceals critical single-point vulnerabilities.
3. **Coverage Gaps Never Default to Passes:**
   - If a model cannot be executed or annotations are missing, PRAMAAN reports an explicit `CoverageGap` rather than silently passing the asset.
4. **Low Confidence Does Not Equal Safe:**
   - A finding with `LOW` confidence warrants human analyst inspection, not dismissal.
5. **Evidence-Backed Findings:**
   - Every finding points to raw evidence digests stored in SQLite and the `BlobStore`.

---

## 7. Security Architecture

- **Cryptographic Algorithms:** SHA-256 for content-addressed hashing and hash-chaining; Ed25519 (RFC 8032) for digital attestation.
- **Tamper-Evident Audit Chain:** Chronologically chained event ledger initialized from a deterministic Genesis event (`00000000...`). Every event records `current_hash = SHA256(previous_hash + payload)`.
- **Safe Model Loading:** PyTorch state dicts are deserialized strictly with `torch.load(..., weights_only=True)` to prevent arbitrary code execution via Python pickle vulnerabilities.
- **Secure File Ingestion:** All ZIP archives are extracted with relative-path resolution containment to eliminate Zip-Slip directory traversal attacks.
- **SQL Injection Defense:** All queries utilize parameterized SQLite queries via the repository pattern.
- **Electron Isolation:** Native shell runs with `contextIsolation = true`, `nodeIntegration = false`, `sandbox = true`, external navigation blocked via `will-navigate`, and arbitrary window opening blocked.

---

## 8. Air-Gap & Offline Validation

> **Validated Operational Statement:**
> The core assurance workflow is designed to operate without Internet access and was validated under controlled outbound-network blocking/browser interception with **zero external requests** observed during the validation run.

- **Zero Cloud Reliance:** Core detectors, scoring algorithms, report generators, and database operations execute locally.
- **Local Typography:** All fonts (`Inter`, `JetBrains Mono`) are packaged locally as WOFF2 assets—zero Google Fonts CDN calls.
- **Local Runtime:** Native Electron Chromium browser and Python backend run locally on loopback (`127.0.0.1`).

---

## 9. AI Copilot Architecture & Governance

PRAMAAN includes an optional natural-language **Analyst Copilot**:
- **Role:** Explains complex findings, summarizes limitations, and assists junior forensic analysts.
- **Strict Non-Authoritative Governance:** The Copilot **CANNOT** alter findings, change risk/confidence/coverage scores, modify evidence hashes, or edit the audit ledger.
- **Release Status:** Disabled and unconfigured by default in release builds (`PRAMAAN_AI_ENABLED=false`).
- **Offline Integrity:** The core assurance engine never requires the Copilot or an external API key to run complete evaluations.

---

## 10. Desktop Application Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Native Electron Desktop Shell              │
│       (Chromium 130 + Secure Preload Context Bridge)    │
└───────────────────────────┬─────────────────────────────┘
                            │ Loopback IPC / HTTP (127.0.0.1)
┌───────────────────────────▼─────────────────────────────┐
│                 FastAPI Python Runtime                  │
│       (FastAPI + Uvicorn + SQLite WAL + BlobStore)      │
├─────────────────────────────────────────────────────────┤
│  11 Forensic Detectors (DI-01..DI-05, MI-01..MI-05, PI) │
│  PyTorch CPU Kernels · ONNX Runtime · ReportLab Engine  │
└─────────────────────────────────────────────────────────┘
```

- **Production Static Frontend:** Served directly from local memory without Vite, HMR WebSockets, or Node.js development servers.
- **Isolated Writable Storage:** Application data, SQLite database, and blobs are stored in `%APPDATA%\PRAMAAN\data` without requiring administrator privileges.
- **Source Remains Editable:** Packaging the standalone distributable does not freeze or lock source code files in the repository.

---

## 11. Standalone Windows Release Package

PRAMAAN is packaged as a standalone Windows AMD64 distribution:
- **Executable:** `release\PRAMAAN\PRAMAAN.exe` (188.7 MB)
- **Total Release Footprint:** ~1.25 GB (includes bundled isolated Python 3.14.7 runtime, PyTorch CPU, ONNX Runtime, and static frontend).
- **Zero Host Prerequisites:** Requires **no installed Python**, **no installed Node.js**, **no external web browser**, and **no Internet access**.
- **Distribution Notice:** The release is distributed as the complete `release/PRAMAAN` directory (or ZIP archive), not merely the launcher executable, as it relies on adjacent bundled runtime libraries.

---

## 12. Deterministic Demo Presets

PRAMAAN bundles five authentic offline demo presets backed by local corpus assets:

1. **Clean Reference Baseline (`clean_baseline`):**
   - Validates an untampered ONNX candidate against its baseline reference.
   - *Outcome:* Risk: `NONE`, Confidence: `HIGH`, Coverage: `100%`, Findings: 5 baseline checks pass.
2. **Dataset Duplicates & Collisions (`duplicate_data`):**
   - Scans computer vision dataset for byte collisions and perceptual near-duplicates (Hamming $\le 10$).
   - *Outcome:* Risk: `MEDIUM`, Confidence: `MODERATE`, Coverage: `60%`, Findings: 2 duplicate clusters.
3. **Parameter Tampering (NaN/Inf) (`corrupted_model`):**
   - Detects IEEE-754 non-finite corrupted weights and extreme magnitude outliers in neural network tensors.
   - *Outcome:* Risk: `HIGH`, Confidence: `HIGH`, Coverage: `100%`, Findings: 7 parameter corruption alerts.
4. **Trojan Shortcut Convergence (`trojan_model`):**
   - Isolates a high-frequency spatial trigger patch causing an Attack Success Rate (ASR) spike to $99.2\%$.
   - *Outcome:* Risk: `HIGH`, Confidence: `HIGH`, Coverage: `100%`, Findings: 4 backdoor findings.
5. **Cryptographic Inference Provenance (`provenance_attestation`):**
   - Evaluates RFC 8032 Ed25519 signature verification and flags duplicate nonce replay attacks.
   - *Outcome:* Risk: `MEDIUM` (Replay flagged), Confidence: `HIGH`, Coverage: `100%`, Findings: 3 provenance findings.

---

## 13. 5-Minute SIH Demonstration Sequence

1. **0:00 - 0:30 (Landing):** Introduce *Evidence Before Trust* and the 4 forensic layers.
2. **0:30 - 1:00 (Capabilities):** Open Capabilities and inspect detector `MI-05` (Trojan Shortcut).
3. **1:00 - 1:45 (Execute Demo):** Switch to Demo Mode, load *Scenario 4: Trojan Shortcut Convergence*, and execute assessment.
4. **1:45 - 2:45 (Results & Metric Triad):** Review Risk `HIGH`, Confidence `HIGH`, and Coverage `100%` (decoupled triad).
5. **2:45 - 3:30 (Findings & Evidence):** Drill into the localized trigger patch coordinates and SHA-256 evidence digests.
6. **3:30 - 4:15 (Audit & Exports):** Open Audit Trail, click *"Verify Chain"* (green cryptographic check), and download PDF report.
7. **4:15 - 5:00 (Judge Q&A):** Answer judge questions grounded in implementation.

---

## 14. Export Formats

1. **Cryptographic PDF Report:** Complete assessment summary, metric triad, detector results, findings with recommended dispositions, and audit certificate.
2. **Structured JSON Package:** Machine-readable evaluation summary formatted for SIEM integration or automated CI/CD gating.
3. **Audit Trail JSON:** Chronological ledger of SHA-256 hash-chained events from genesis for compliance auditing.

---

## 15. Automated Testing

PRAMAAN enforces an extensive automated regression test suite:

- **Backend Test Suite (pytest):** **988 passed, 1 skipped** (989 tests total)
  - Covers API routes, cryptographic algorithms, detectors (DI-01 to DI-05, MI-01 to MI-05, PI-01), ingestion, and security boundaries.
- **Frontend Test Suite (vitest):** **128 passed** (18 test suites total)
  - Covers AppShell, navigation, findings filters, lightboxes, global search, and export dialogs.
- **Production Static Build:** Built cleanly via `tsc -b && vite build` in **1.77 seconds**.
- **Security Scans:** 0 leaked API keys, 0 hardcoded developer paths, 0 external CDN calls.

---

## 16. Development Quickstart

### Prerequisites
- Python 3.11+ with `venv`
- Node.js 18+ with `npm`

### Local Development Setup

```bash
# 1. Clone repository
git clone https://github.com/arjunjaincs/sih26.git
cd sih26

# 2. Set up Python virtual environment
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,models]"

# 3. Set up Frontend dependencies
cd frontend
npm install
cd ..

# 4. Launch Desktop Shell in Development Mode
start-dev.bat
# or:
npm run electron:dev
```

### Running Test Suites

```bash
# Backend pytest suite
.venv\Scripts\python.exe -m pytest

# Frontend vitest suite
cd frontend
npm test -- --run
cd ..

# Production frontend build
cd frontend
npm run build
cd ..
```

### Building the Standalone Release

```bash
# Clean standalone Windows packaging
.venv\Scripts\python.exe tools/build_release.py
```

---

## 17. Known Technical Limitations

PRAMAAN maintains strict technical honesty regarding its operational boundaries:
1. **Invisible / Blended Triggers:** Subtle, natural-style perturbations across entire pixel domains without high-frequency artifacts may evade spatial patch detection without behavioral baseline comparisons.
2. **Semantic Out-of-Distribution:** Covariate shift detection (DI-04) operates in raw pixel and channel statistical spaces; high-level semantic OOD without foundation embeddings is not claimed.
3. **Unattributed Datasets:** Contributor risk analysis (DI-05) requires source attribution metadata; unannotated batches create explicit coverage gaps.
4. **Single-Manifest Replay Inference:** Replay detection (PI-01) requires historical nonce tracking in SQLite; a single isolated manifest cannot prove replay without prior ledger context.
5. **PyTorch State-Dict Constraints:** Unexecutable `.pt`/`.pth` state dictionaries support parameter moment inspection (MI-02) but report coverage gaps for dynamic forward-pass activation profiling (MI-03).
6. **TorchScript Deserialization:** Serialized TorchScript graphs carry higher loading complexity than weights-only state dicts; safe deserialization is enforced.
7. **Platform & Network Binding:** The standalone packaged release targets Windows AMD64 and binds its local API service to loopback port `8000`.

---

## 18. Project Information

- **Event:** Smart India Hackathon (SIH 2026)
- **Ministry / Department:** Ministry of Defence / Indian Army (DGIS)
- **Problem Statement Code:** `SIH26228`
- **Core Architecture Principle:** *Evidence Before Trust.*
