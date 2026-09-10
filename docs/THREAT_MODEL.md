# PRAMAAN Threat Model

> Security analysis of the PRAMAAN platform itself — not the CV pipelines it assesses.

Version: 2.0-DRAFT  
Last Updated: 2026-09-10

---

## 1. Trust Boundaries

```
┌─────────────────────────────────────────────────────┐
│                 TRUST BOUNDARY 1                     │
│              Analyst's Machine / LAN                 │
│                                                      │
│  ┌──────────┐    HTTP     ┌──────────────────────┐  │
│  │ Frontend │ ──────────► │ Backend (FastAPI)     │  │
│  │ (React)  │ ◄────────── │                      │  │
│  │          │  JSON       │ ┌──────────────────┐ │  │
│  │ UNTRUST  │             │ │ Assessment Core  │ │  │
│  └──────────┘             │ │ TRUSTED          │ │  │
│                           │ └────────┬─────────┘ │  │
│                           │          │           │  │
│                           │ ┌────────▼─────────┐ │  │
│                           │ │ SQLite + Blobs   │ │  │
│                           │ │ TRUSTED          │ │  │
│                           │ └──────────────────┘ │  │
│                           └──────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │            TRUST BOUNDARY 2                   │   │
│  │           External Inputs                     │   │
│  │                                               │   │
│  │  Datasets │ Models │ Images │ Config files    │   │
│  │  UNTRUSTED — always validated before use      │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 2. Threat Catalog

### T-01: Malicious Model File (Arbitrary Code Execution)

**Vector**: Attacker supplies a PyTorch `.pt` file containing a malicious
`__reduce__` method in a pickled object. Loading with `torch.load()` (default)
executes arbitrary Python code.

**Impact**: CRITICAL — full system compromise.

**Mitigation**:
- **Never** call `torch.load(path)` without `weights_only=True`
- ONNX models loaded via ONNX Runtime (no pickle)
- TorchScript models loaded via `torch.jit.load()` (restricted execution)
- All model loading goes through `backend/infra/model_loader.py` — a single
  controlled entry point that enforces safe loading
- Static analysis lint rule to flag any `torch.load` call without `weights_only=True`

**Residual Risk**: `weights_only=True` allowlists certain tensor types.
PyTorch's safe-loading may have undiscovered bypass. Monitor PyTorch CVEs.

---

### T-02: Malicious Image Files (Image Processing Exploits)

**Vector**: Crafted image files exploiting Pillow/libjpeg/libpng vulnerabilities
(buffer overflow, heap corruption, denial of service).

**Impact**: HIGH — potential code execution or crash.

**Mitigation**:
- Set `Image.MAX_IMAGE_PIXELS = 89_478_485` (default Pillow bomb guard)
- Validate image dimensions before loading (configurable max: 8192×8192)
- Validate file size before loading (configurable max: 50 MB per image)
- Process images in a subprocess with resource limits where feasible
- Keep Pillow updated
- Reject non-image files with image extensions (magic byte validation)

---

### T-03: Path Traversal

**Vector**: Malicious filenames in uploaded datasets (e.g., `../../etc/passwd`,
`..\..\Windows\System32\...`) escape the intended storage directory.

**Impact**: HIGH — read/write arbitrary files.

**Mitigation**:
- All file operations use `pathlib.Path.resolve()` and verify the resolved
  path starts with the configured storage root
- Reject any path component containing `..`
- Reject absolute paths in uploaded archives
- Strip or reject non-ASCII filenames that could exploit Unicode normalization

---

### T-04: Zip Bombs / Archive Bombs

**Vector**: Compressed datasets that expand to enormous size, exhausting disk
space or memory.

**Impact**: MEDIUM — denial of service.

**Mitigation**:
- Stream-extract archives with running size accounting
- Abort extraction if total extracted bytes exceed configurable limit (default: 10 GB)
- Abort if file count exceeds configurable limit (default: 100,000 files)
- Reject nested archives (no `.zip` inside `.zip`)

---

### T-05: Resource Exhaustion via Large Inputs

**Vector**: Extremely large datasets, very high-resolution images, or many
concurrent assessments consuming all CPU/memory/disk.

**Impact**: MEDIUM — denial of service.

**Mitigation**:
- Configurable limits: max dataset size, max image count, max concurrent assessments
- Detector timeout: configurable per-detector time limit (default: 300s)
- Assessment timeout: configurable total assessment time limit (default: 3600s)
- Disk space check before starting large operations

---

### T-06: Adversarial Inputs Designed to Fool Detectors

**Vector**: Attacker crafts inputs specifically designed to evade PRAMAAN's
detectors (e.g., adversarial perturbations that bypass OOD detection).

**Impact**: MEDIUM — missed detections (false negatives).

**Mitigation**:
- Honest coverage reporting: PRAMAAN states what it can and cannot detect
- Multiple orthogonal detectors per threat category
- Explicit limitations documented per detector
- This is an inherent limitation of any detection system; PRAMAAN does not
  claim perfect detection

---

### T-07: Tampered Audit Records

**Vector**: Local attacker modifies the SQLite database to alter or delete
audit events, making malicious activity undetectable.

**Impact**: HIGH — undermines auditability guarantees.

**Mitigation**:
- Hash-chain linking: each event references the hash of the previous event
- Ed25519 signatures on critical audit events
- Chain verification on every read and periodic background checks
- Export functionality for offline backup/verification
- Application-level append-only enforcement (no UPDATE/DELETE on audit tables)
- **Residual**: A root-level attacker who can replace the entire database
  AND the verification code can defeat this. Mitigation: signed report exports
  provide an external verification anchor.

---

### T-08: Report Tampering

**Vector**: After PRAMAAN generates a report, someone modifies the exported
PDF/JSON to change findings or risk levels.

**Impact**: HIGH — misleading assurance conclusions.

**Mitigation**:
- Reports include a SHA-256 digest of their content
- Reports can be Ed25519-signed
- Verification tool can check report integrity
- Report generation events are recorded in the audit chain

---

### T-09: Unsafe Model Deserialization (TorchScript)

**Vector**: TorchScript models (`*.pt` JIT-compiled) can contain arbitrary
operations, including file system access and network calls.

**Impact**: MEDIUM — restricted but possible code execution.

**Mitigation**:
- TorchScript execution in a sandboxed subprocess where feasible
- Limit TorchScript model size
- Document TorchScript as higher-risk than ONNX
- Prefer ONNX when possible

---

### T-10: Dependency Compromise (Supply Chain)

**Vector**: A compromised PyPI package or npm package injects malicious code
into PRAMAAN.

**Impact**: CRITICAL — full system compromise.

**Mitigation**:
- Pin all dependencies with exact versions
- Use lockfiles (`requirements.txt` with hashes, `package-lock.json`)
- Offline installation from vendored packages for air-gapped deployment
- Minimize dependency count
- Periodic `pip audit` / `npm audit`

---

### T-11: UI/Backend Trust Boundary Violation

**Vector**: Frontend sends crafted requests to bypass validation or trigger
unintended backend behavior.

**Impact**: MEDIUM — data corruption, unauthorized operations.

**Mitigation**:
- Backend validates ALL input (Pydantic models with strict validation)
- Frontend is treated as untrusted
- No client-side-only security checks
- CORS configured for local-only origins
- No authentication in initial version (single-user, local deployment)

---

### T-12: Malicious Metadata in Datasets

**Vector**: EXIF data, annotation files, or manifest JSON containing script
injection, SQL injection, or control characters.

**Impact**: LOW-MEDIUM — XSS in reports, potential SQLite injection.

**Mitigation**:
- Parameterized SQL queries (never string interpolation)
- Sanitize all metadata strings before display
- Strip or escape control characters
- Validate annotation file schemas strictly

---

### T-13: Compromised Provenance Records

**Vector**: Attacker forges or replays inference provenance manifests to claim
a model produced outputs it did not.

**Impact**: HIGH — undermines provenance guarantees.

**Mitigation**:
- Manifests are Ed25519-signed
- Nonce prevents replay
- Monotonic sequence number prevents reordering
- Timestamp bound checked against system clock (configurable tolerance)
- Manifest verification checks all bindings (input hash, model hash, output hash)

---

## 3. Threats Explicitly Out of Scope

| Threat | Reason |
|--------|--------|
| Network-based attacks | Air-gapped operation; no network listeners beyond localhost |
| Multi-user access control | Single-user prototype; no authentication in v1 |
| Hardware-level attacks | Software-only system; HSM integration is future work |
| Side-channel attacks on models | Research-grade; not in scope for prototype |
| GPU memory attacks | Requires kernel-level access; out of scope |

---

## 4. Security Design Principles

1. **Validate at ingestion**: Every external input is validated at the boundary
2. **Single entry points**: Model loading, image loading, archive extraction each have one controlled function
3. **Fail closed**: If validation fails, reject the input; do not attempt partial processing
4. **Least privilege**: Detectors receive only the data they need, not full filesystem access
5. **Defense in depth**: Multiple mitigations per threat where possible
6. **Explicit over implicit**: Security constraints are documented and enforced in code, not assumed
