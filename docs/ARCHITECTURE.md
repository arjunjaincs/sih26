# PRAMAAN Architecture

> Evidence Before Trust — Offline Computer-Vision Integrity Assurance

Version: 2.0-DRAFT  
Status: Architecture Review  
Last Updated: 2026-09-10

---

## 1. System Overview

PRAMAAN is a modular monolith that assesses the integrity of computer-vision
pipelines across three asset classes: **training data**, **models**, and
**inference outputs**. It produces evidence-backed, analyst-readable assurance
findings and maintains a cryptographically verifiable audit trail.

```
┌──────────────────────────────────────────────────────────┐
│                    ANALYST WORKSTATION                    │
│              React / TypeScript / Tailwind                │
│                                                          │
│  Assessment  │ Findings │ Evidence │ Provenance │ Audit  │
└──────────┬───────────────────────────────────────────────┘
           │ REST (JSON)
┌──────────▼───────────────────────────────────────────────┐
│                      API GATEWAY                         │
│                FastAPI / Pydantic v2                      │
│                                                          │
│  Assessments │ Assets │ Findings │ Reports │ Audit │ Cfg │
└──────────┬───────────────────────────────────────────────┘
           │
┌──────────▼───────────────────────────────────────────────┐
│                  ASSESSMENT ORCHESTRATOR                  │
│                                                          │
│  Lifecycle management · Detector dispatch · Evidence      │
│  collection · Risk/confidence calculation · Coverage      │
└───┬──────────┬──────────┬──────────┬──────────┬─────────┘
    │          │          │          │          │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│ Data  │ │ Model │ │ Infer │ │ Drift │ │ Fuse  │
│Integr.│ │Integr.│ │Proven.│ │Engine │ │Engine │
│Engine │ │Engine │ │Engine │ │       │ │       │
└───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘
    │          │          │          │          │
    └──────────┴──────────┴──────────┴──────────┘
                        │
           ┌────────────▼────────────┐
           │     EVIDENCE STORE      │
           │  SQLite + Content-Addr. │
           │     File Storage        │
           └────────────┬────────────┘
                        │
           ┌────────────▼────────────┐
           │     AUDIT LEDGER        │
           │  Append-only · Hash-    │
           │  linked · Signed        │
           └─────────────────────────┘
```

## 2. Layered Architecture

### Layer 0: Domain Core (`backend/domain/`)

Pure Python. No framework imports. No I/O.

Contains:
- **Entities**: `Assessment`, `Asset`, `Finding`, `Evidence`, `RiskAssessment`, etc.
- **Value Objects**: `Severity`, `AccessLevel`, `DetectorStatus`, `HashDigest`
- **Protocols**: `Detector`, `EvidenceCollector`, `AuditWriter`
- **Domain Logic**: risk/confidence calculation, coverage computation, evidence linkage

### Layer 1: Engines (`backend/engines/`)

Stateless assessment logic organized by domain concern.

| Engine | Responsibility |
|--------|---------------|
| `DataIntegrityEngine` | Perceptual hashing, label analysis, OOD detection, contributor aggregation |
| `ModelIntegrityEngine` | Artifact fingerprinting, behavioral testing, activation analysis, backdoor assessment |
| `InferenceProvenanceEngine` | Manifest construction, binding, signing, verification |
| `DriftEngine` | Distribution comparison, statistical shift detection |
| `EvidenceFusionEngine` | Multi-source evidence aggregation, risk/confidence synthesis |

Each engine:
- Accepts typed input contracts (Pydantic models)
- Returns typed output contracts (findings + evidence + coverage)
- Declares required access level per method
- Reports unavailable methods as `CoverageGap` entries
- Does **not** import FastAPI

### Layer 2: Detectors (`backend/detectors/`)

Individual detection algorithms, each implementing the `Detector` protocol:

```python
class Detector(Protocol):
    @property
    def metadata(self) -> DetectorMetadata: ...

    def can_run(self, context: DetectorContext) -> CanRunResult: ...

    def run(self, context: DetectorContext) -> DetectorResult: ...
```

`DetectorMetadata` includes:
- `detector_id`, `version`, `category`
- `required_access_level` (BLACK_BOX | GRAY_BOX | WHITE_BOX)
- `required_asset_types`
- `dependencies` (other detectors or libraries)
- `supported_formats`
- `method_description`, `method_reference` (paper/source)
- `output_schema`
- `confidence_semantics`
- `limitations`
- `implementation_status` (IMPLEMENTED | PARTIAL | EXPERIMENTAL | DEMO_ONLY | UNAVAILABLE)

### Layer 3: Infrastructure (`backend/infra/`)

- **Persistence**: SQLite via `sqlite3` (no ORM). Content-addressed blob store for evidence artifacts.
- **Crypto**: SHA-256 hashing, Ed25519 signing, hash-chain verification.
- **Serialization**: Canonical JSON for deterministic hashing.
- **Config**: TOML/YAML policy files.

### Layer 4: API (`backend/api/`)

FastAPI routes. Thin layer — validates input, calls orchestrator, returns response.
No business logic in route handlers.

### Layer 5: Frontend (`frontend/`)

React + TypeScript + Tailwind. Analyst workstation interface.

---

## 3. Assessment Lifecycle

```
INGEST              Receive dataset / model / inference bundle
    │
VALIDATE            Format checks, size limits, safety scans
    │
IDENTIFY_ASSETS     Catalog assets, assign IDs, classify types
    │
FINGERPRINT         SHA-256 hash every asset, perceptual hash images
    │
PROFILE_ACCESS      Determine access level per model (white/gray/black)
    │
SELECT_METHODS      Match available detectors to asset types + access
    │
EXECUTE             Run all applicable detectors
    │
COLLECT_EVIDENCE    Gather structured evidence from detector results
    │
CALCULATE_RISK      Aggregate evidence → risk assessment per asset
    │
CALCULATE_CONFIDENCE  Assess confidence in each risk judgment
    │
DETERMINE_COVERAGE  Record what was tested, what was not, and why
    │
GENERATE_FINDINGS   Produce analyst-readable finding records
    │
AUDIT               Append all events to the audit ledger
    │
REPORT              Generate structured assurance report
```

Each stage produces audit events. Each transition is recorded.
The orchestrator advances through stages sequentially; detectors within
a stage may execute concurrently.

---

## 4. Risk / Confidence Architecture

### Fundamental Separation

| Concept | Meaning | Source |
|---------|---------|--------|
| **Evidence** | Raw observations from detectors | Detectors |
| **Risk** | Estimated threat level given evidence | Fusion engine |
| **Confidence** | Degree of trust in the risk estimate | Fusion engine |
| **Coverage** | Fraction of applicable methods that ran | Orchestrator |
| **Severity** | Potential impact if the risk is real | Domain policy |

### Risk is NOT a single score

Risk is represented as:

```python
class RiskAssessment:
    level: RiskLevel          # NONE | LOW | MEDIUM | HIGH | CRITICAL
    qualitative: str          # Human-readable summary
    contributing_evidence: list[EvidenceRef]
    access_level_used: AccessLevel
    methods_applied: list[str]
    methods_unavailable: list[CoverageGap]
```

### Confidence is separate and qualified

```python
class ConfidenceAssessment:
    level: ConfidenceLevel    # LOW | MODERATE | HIGH
    qualifier: str            # Why this confidence level
    limiting_factors: list[str]
    sample_size: int | None
    statistical_basis: str | None
```

**Rules**:
- HIGH risk + LOW confidence = "Suspicious, needs investigation"
- LOW risk + LOW confidence ≠ "Safe" — it means "Insufficient evidence"
- Coverage < 100% always reduces confidence
- Absence of findings with incomplete coverage → explicit "INCONCLUSIVE"

---

## 5. Access-Aware Architecture

```
┌─────────────┬──────────────────────────────────────────┐
│ Access Level │ Available Methods                        │
├─────────────┼──────────────────────────────────────────┤
│ WHITE_BOX   │ All methods: weight inspection,          │
│             │ activation analysis, gradient analysis,   │
│             │ architectural inspection, behavioral,     │
│             │ fingerprinting                           │
├─────────────┼──────────────────────────────────────────┤
│ GRAY_BOX    │ Behavioral testing, input/output pairs,  │
│             │ limited activation (hooks if supported),  │
│             │ fingerprinting, no direct weight access   │
├─────────────┼──────────────────────────────────────────┤
│ BLACK_BOX   │ Behavioral testing only: input → output  │
│             │ consistency, reference battery, timing    │
│             │ analysis, no internal access              │
└─────────────┴──────────────────────────────────────────┘
```

When a detector cannot run due to insufficient access:

```python
class CoverageGap:
    detector_id: str
    reason: str               # "Requires WHITE_BOX access; only BLACK_BOX available"
    risk_implication: str     # What threat this leaves unassessed
    recommendation: str       # "Provide model weights for full analysis"
```

These gaps are surfaced in findings and reports, never silently dropped.

---

## 6. Provenance Architecture

### Inference Manifest

Every inference execution produces a canonical manifest:

```python
class InferenceManifest:
    manifest_id: str              # UUID v4
    assessment_id: str            # Parent assessment
    input_hash: HashDigest        # SHA-256 of input image(s)
    model_id: str                 # Model asset identifier
    model_hash: HashDigest        # SHA-256 of model artifact
    preprocessing_config: dict    # Exact preprocessing params
    inference_config: dict        # Exact inference params
    runtime_version: str          # e.g., "onnxruntime==1.16.0"
    software_version: str         # PRAMAAN version
    output_hash: HashDigest       # SHA-256 of raw output
    output_data: dict             # The actual inference result
    timestamp: datetime           # UTC, ISO 8601
    nonce: str                    # Random 32-byte hex
    sequence_number: int          # Monotonic counter
    environment: EnvironmentInfo  # OS, Python, GPU, etc.
```

### Canonical Serialization

For deterministic hashing/signing:
1. Serialize to JSON with sorted keys, no whitespace, UTF-8 encoding
2. All datetimes as ISO 8601 UTC with Z suffix
3. All byte arrays as lowercase hex
4. Floats serialized with fixed precision (6 decimal places)
5. Hash the canonical bytes with SHA-256

### Signing

- **Algorithm**: Ed25519
- **Key management**: Local keypair generated at PRAMAAN installation
- **Signing**: Sign the canonical SHA-256 digest
- **Verification**: Verify signature against the stored public key
- **No PKI dependency**: Self-signed for offline operation; optional local CA

---

## 7. Audit Architecture

### Append-Only Ledger

```python
class AuditEvent:
    event_id: str               # UUID v4
    event_type: AuditEventType  # Enum: ASSESSMENT_CREATED, ASSET_INGESTED, etc.
    timestamp: datetime         # UTC
    actor: str                  # "system", "user:<id>", "detector:<id>"
    assessment_id: str | None   # Context
    payload_digest: HashDigest  # SHA-256 of the event payload
    previous_hash: HashDigest   # Hash of previous event (chain link)
    current_hash: HashDigest    # H(previous_hash || event_id || timestamp || payload_digest)
    signature: bytes | None     # Ed25519 signature of current_hash
```

### Chain Verification

```
verify_chain(events):
    for i, event in enumerate(events):
        if i == 0:
            assert event.previous_hash == GENESIS_HASH
        else:
            assert event.previous_hash == events[i-1].current_hash
        recomputed = H(event.previous_hash || event.event_id || ...)
        assert recomputed == event.current_hash
        if event.signature:
            verify_ed25519(public_key, event.current_hash, event.signature)
```

### Storage

Audit events are written to a dedicated SQLite table with WAL mode.
The table is append-only at the application level (no UPDATE/DELETE in the
audit API). Periodic integrity checks verify the hash chain.

---

## 8. Persistence Strategy

### SQLite (Primary)

Single SQLite database file (`pramaan.db`) with WAL mode.

Tables:
- `assessments` — assessment metadata and state
- `assets` — registered assets (datasets, models, images)
- `findings` — assessment findings
- `detector_results` — raw detector outputs
- `audit_events` — append-only audit chain
- `coverage_gaps` — recorded coverage limitations
- `provenance_manifests` — inference provenance records

### Content-Addressed Blob Store

Directory: `evidence/blobs/`

Files stored by their SHA-256 hash: `evidence/blobs/ab/cd/abcdef1234...`

Used for: input images, model files, evidence artifacts, report snapshots.

This avoids storing large binary data in SQLite while maintaining
content integrity through hash-based addressing.

### Rationale

- SQLite handles all structured data; no server process needed
- Blob store handles large artifacts without SQLite bloat
- Both work on a developer laptop
- Both work air-gapped
- Both are trivially backed up (copy 1 file + 1 directory)

---

## 9. Demo Architecture

### Strict Separation

```
backend/
├── engines/          # LIVE analysis — real detectors, real evidence
├── detectors/        # LIVE analysis — real detection algorithms
└── demo/             # DEMO layer — deterministic fixtures only
    ├── fixtures/     # Pre-computed, deterministic demo data
    ├── scenarios.py  # Scenario definitions
    └── runner.py     # Demo scenario executor
```

### Rules

1. Demo fixtures are **pre-computed, deterministic data files** — not runtime-generated fakes
2. Every demo finding carries `source: "DEMO_FIXTURE"` — never `source: "LIVE_ANALYSIS"`
3. The demo runner calls the same orchestrator but with fixture-backed "detectors"
4. The UI displays a prominent `DEMO MODE` banner when viewing demo assessments
5. Demo assessments have `assessment_type: DEMO`; live assessments have `assessment_type: LIVE`
6. Demo code **never** imports from `engines/` or `detectors/`; live code **never** imports from `demo/`

### Demo Scenarios

| ID | Scenario | PS Requirement |
|----|----------|---------------|
| DS-01 | Label manipulation | Data poisoning |
| DS-02 | Near-duplicate flooding | Data integrity |
| DS-03 | OOD sample insertion | Data integrity |
| DS-04 | Model substitution | Model integrity |
| DS-05 | Backdoor trigger (simulated) | Model integrity |
| DS-06 | Inference output tampering | Output integrity |
| DS-07 | Replay attack | Provenance |
| DS-08 | Distribution shift | Drift detection |

---

## 10. Security Model (Summary)

See [THREAT_MODEL.md](./THREAT_MODEL.md) for full treatment.

Key defenses:
- **Model loading**: Never use `pickle.load` or `torch.load` with `weights_only=False`. Only `torch.load(..., weights_only=True)` or ONNX Runtime.
- **Image processing**: PIL/Pillow with `Image.MAX_IMAGE_PIXELS` limit. No SVG rendering.
- **Path traversal**: All file paths resolved against a configured root; reject `..` components.
- **Resource limits**: Configurable max file size, max dataset size, max concurrent detectors.
- **Zip bombs**: Stream-decompress with size accounting; abort if expanded size exceeds limit.
- **Audit integrity**: Hash-chain verification; signature verification for provenance.
- **UI/backend boundary**: Backend validates all input; frontend is untrusted.

---

## 11. Reproducibility

Every assessment records:

| Field | Purpose |
|-------|---------|
| `assessment_id` | Unique identifier |
| `software_version` | PRAMAAN version (semver + git hash) |
| `detector_versions` | Dict of detector_id → version |
| `configuration_hash` | SHA-256 of the full config used |
| `input_hashes` | SHA-256 of every input asset |
| `model_hashes` | SHA-256 of every model artifact |
| `random_seed` | Global seed if randomness is used |
| `environment` | Python version, OS, CPU, GPU, library versions |
| `started_at` / `completed_at` | UTC timestamps |

Given the same inputs, configuration, software version, and random seed,
PRAMAAN must produce byte-identical findings and evidence.

---

## 12. Technology Decisions

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Backend framework | FastAPI + Pydantic v2 | Async, typed, fast, well-documented |
| Frontend framework | React + TypeScript + Vite | Standard, fast builds, good tooling |
| Styling | Tailwind CSS | Utility-first, consistent, fast |
| Database | SQLite (WAL mode) | Zero-config, air-gapped, single file |
| Hashing | SHA-256 (hashlib) | Standard, fast, well-understood |
| Signing | Ed25519 (PyNaCl or cryptography) | Fast, small keys, no RSA complexity |
| Model loading | PyTorch (weights_only), ONNX Runtime | Safe loading, no pickle |
| Image processing | Pillow | Standard, no native deps |
| Embeddings | torchvision models (local) | Offline, no API needed |
| Statistics | scipy, numpy | Standard scientific computing |
| Perceptual hash | imagehash | Lightweight, pure Python |
| Testing | pytest + httpx | Standard Python testing |
