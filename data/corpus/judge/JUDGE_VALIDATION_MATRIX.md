# PRAMAAN v1 — Official Judge Validation & Demonstration Matrix
**Smart India Hackathon 2026 (SIH 2026)**  
*Computer Vision Dataset, Model, and Inference Integrity Assurance Platform*

---

## 1. Executive Demonstration Framing

PRAMAAN is designed for air-gapped forensic inspection of mission-critical Computer Vision systems.  
Every scenario in this matrix executes through the **real deterministic assessment engine** with zero simulated findings, zero mocked risk calculations, and zero external network calls.

### Core Architectural Guarantees (ADR-003)
1. **Risk ≠ Confidence**: A dataset with 0 findings does *not* mean "safe" if only 20% of detectors could run.
2. **Coverage Separation**: Denominators exclude truly non-applicable detectors, while unsupported analysis spaces emit explicit `CoverageGap` records.
3. **Cryptographic Binding**: All inference outputs, input frames, and models are bound by Ed25519 digital signatures with monotonic replay protection.
4. **Authoritative Evidence**: Every finding links to traceable cryptographic hashes, tensor statistics, or sample image previews.

---

## 2. Premier Live Demonstration Presets (1-Click SIH Scenarios)

These 3 polished scenarios are configured for live jury presentation via the **Assess Workstation → Demo Mode**:

| Preset ID | Demo Showcase Title | Layer Focus | What Judge Sees on Screen | Primary Detectors | Risk | Confidence | Coverage | Key Evidence / Live Pitch |
|---|---|---|---|---|---|---|---|---|
| **DEMO A** | **Clean Reference Baseline** | Clean Baseline | Clean Assessment Screen: 0 findings, green lifecycle badge, Ed25519 hash chain verified, instant downloadable signed PDF Assurance Report. | `MI-01`, `MI-02`, `MI-04` | **NONE** | **HIGH** | **100%** | Zero false alarms. Candidate exactly matches reference fingerprint (`MI-01`), 0 parameter drift (`MI-02`), and identical graph topology (`MI-04`). |
| **DEMO B** | **Dataset Integrity Investigation** | Dataset Forensics | Interactive Findings card + Evidence workstation. Side-by-side thumbnail previews of `dup_ped_clone.png` and `dup_ped_orig.png` with instant high-res Lightbox modal. | `DI-01` | **HIGH** | **HIGH** | **100%** | Byte-level and perceptual visual redundancy. Live interactive preview confirms real images rendered securely without arbitrary file access. |
| **DEMO C** | **Model Integrity & Backdoor Forensics** | Neural Forensics | Deep forensic finding: Latent Backdoor Trigger Shortcut (`MI-05`), parameter weight statistics (`MI-02`), and model fingerprint (`MI-01`). | `MI-01`, `MI-02`, `MI-05` | **HIGH** | **HIGH** | **100%** | Backdoor convergence measurements. Discovers adversarial trigger shortcut vulnerability without needing labeled external test sets. |

---

## 3. Comprehensive 40-Scenario Validation Matrix

### Category A: Dataset Integrity (Scenarios 01 – 09)

| # | Scenario Title | What Judge Sees | Detector(s) | Expected Finding | Risk | Confidence | Coverage | Evidence Type | SIH Judge Value |
|---|---|---|---|---|---|---|---|---|---|
| **01** | Clean Dataset Baseline | Risk: NONE, 0 findings, 100% applicable dataset coverage. | `DI-01`..`DI-04` | None (Clean) | **NONE** | **HIGH** | **FULL** | Clean baseline summary | Baseline calibration: proves 0 false-positives on authentic clean datasets. |
| **02** | Exact Byte Duplicate Injection | DI-01 finding, identifying exact sample pairs with identical SHA-256. | `DI-01` | `exact_duplicates` | **MEDIUM** | **HIGH** | **FULL** | `hash_match` | Catches byte-level duplication that skews gradient updates and inflates validation metrics. |
| **03** | Perceptual Near-Duplicate Candidate | DI-01 finding, clustering visually similar but byte-distinct samples. | `DI-01` | `near_duplicates` | **LOW** | **HIGH** | **FULL** | `perceptual_cluster` | Detects data leakage across splits caused by resizing, cropping, or format re-compression. |
| **04** | Pairwise Label Contradiction | DI-02 finding, highlighting duplicate/similar images with opposing labels. | `DI-02` | `label_flip` | **HIGH** | **HIGH** | **FULL** | `label_conflict` | Critical defect: contradictory ground-truth directly damages model decision boundaries. |
| **05** | Systematic Mislabelling Cluster | DI-02 finding, flagging statistical label discordance across an entire class subset. | `DI-02` | `mislabelling_cluster` | **HIGH** | **HIGH** | **FULL** | `mislabelling_cluster` | Exposes systematic annotator error that impairs entire semantic categories. |
| **06** | Controlled Recurring Visual Pattern | DI-03 finding, isolating recurring spatial trigger watermark artifacts. | `DI-03` | `trigger_anomaly` | **HIGH** | **HIGH** | **FULL** | `pattern_patch` | Backdoor poison detection: catches Trojan trigger patches planted in dataset imagery. |
| **07** | Distributional Outliers (OOD) | DI-04 finding, revealing multidimensional feature space anomalies. | `DI-04` | `ood_distribution` | **MEDIUM** | **HIGH** | **FULL** | `distribution_stats` | Prevents corrupt or anomalous sample ingestion that degrades feature representation stability. |
| **08** | Disproportionate Contributor Risk | DI-05 finding, tracing defect concentration to a specific data supplier. | `DI-05` | `contributor_risk` | **HIGH** | **HIGH** | **FULL** | `contributor_attribution` | Supply chain provenance: pinpoints compromised annotators, external vendors, or web scrapes. |
| **09** | Multi-Defect Mixed Integrity Dataset | Unified multi-defect card list (DI-01..DI-05) with traceable isolated evidence. | `DI-01`..`DI-05` | Multiple Findings | **HIGH** | **HIGH** | **FULL** | `multi_category` | Real-world stress test: demonstrates multi-finding triage and worst-case risk aggregation. |

---

### Category B: Model Integrity & Architecture (Scenarios 10 – 18)

| # | Scenario Title | What Judge Sees | Detector(s) | Expected Finding | Risk | Confidence | Coverage | Evidence Type | SIH Judge Value |
|---|---|---|---|---|---|---|---|---|---|
| **10** | Clean Reference Baseline Model | Risk: NONE, 0 findings, fingerprint matches reference golden image. | `MI-01`, `MI-02`, `MI-04` | None (Clean) | **NONE** | **HIGH** | **FULL** | `cryptographic_fingerprint` | Verifies candidate model identity, parameter drift, and structural topology against golden binary. |
| **11** | Architecture / Graph Substitution | MI-04 finding, flagging structural graph delta (e.g. Relu vs Add_Bias). | `MI-04` | `behavioral_divergence` | **MEDIUM** | **HIGH** | **FULL** | `graph_divergence` | Catches unauthorized model swapping where filename is preserved but internal graph is altered. |
| **12** | Non-Finite Parameter Corruption | MI-02 finding, displaying non-finite weight counts (NaN/Inf values). | `MI-02` | `parameter_corruption` | **HIGH** | **HIGH** | **FULL** | `parameter_statistics` | Prevents deployment of numerical poison attacks or corrupted checkpoints that crash edge runtimes. |
| **13** | Statistical Weight Outlier Distribution | MI-02 finding, showing abnormal weight distribution variance and spikes. | `MI-02` | `weight_outlier` | **MEDIUM** | **HIGH** | **FULL** | `numerical_distribution` | Detects quantization bugs, exploding gradients, or unregularized weights in deployed weights. |
| **14** | Dead Representation / Activation Collapse | MI-03 finding, detecting near-zero activation variance in intermediate tensors. | `MI-03` | `activation_collapse` | **MEDIUM** | **HIGH** | **FULL** | `activation_variance` | Flags broken model architectures that yield constant outputs regardless of input stimulus. |
| **15** | Trojan Shortcut Convergence | MI-05 finding, measuring high sensitivity to adversarial spatial triggers. | `MI-05` | `trigger_anomaly` | **HIGH** | **HIGH** | **FULL** | `perturbation_convergence` | Deep neural network forensics: exposes latent backdoor shortcuts without requiring test datasets. |
| **16** | Standalone Baseline Enrollment | Risk: NONE, MI-04 reported as `NOT_APPLICABLE` (CoverageGap), not false pass. | `MI-01`, `MI-02` | None (Clean) | **NONE** | **MODERATE** | **PARTIAL** | `enrollment_fingerprint` | ADR-003 transparency: missing reference models reduce confidence rather than giving false green. |
| **17** | Non-Executable PyTorch State Dict | MI-01/MI-02 ran; MI-03/MI-05 emitted as explicit CoverageGaps with reasons. | `MI-01`, `MI-02` | None (CoverageGap) | **NONE** | **MODERATE** | **PARTIAL** | `coverage_gap_record` | Demonstrates that non-executable weight files produce explicit coverage gaps, never fake passes. |
| **18** | Corrupt Model Binary Header | Fail-closed structured rejection (`ModelLoadError`), zero stack traces. | None (Rejected) | Structured Error | **NONE** | **LOW** | **ZERO** | `structured_rejection` | Robust security boundary: refuses execution of corrupted, truncated, or invalid model binaries. |

---

### Category C: Cryptographic Provenance & Replay (Scenarios 19 – 27)

| # | Scenario Title | What Judge Sees | Detector(s) | Expected Finding | Risk | Confidence | Coverage | Evidence Type | SIH Judge Value |
|---|---|---|---|---|---|---|---|---|---|
| **19** | Valid Cryptographic Provenance | PI-01 passes, Ed25519 signature verified, input/model/output SHA-256 bound. | `PI-01` | `provenance_valid` | **NONE** | **HIGH** | **FULL** | `cryptographic_attestation` | Mathematical proof that edge inference output genuinely originated from accredited model. |
| **20** | Input Image Tampering Post-Signing | PI-01 finding, severity HIGH, input_mismatch finding isolating byte changes. | `PI-01` | `input_mismatch` | **HIGH** | **HIGH** | **FULL** | `hash_mismatch` | Defeats input spoofing where an authentic inference signature is falsely paired with another image. |
| **21** | Model Identity Tampering | PI-01 finding, severity HIGH, model_mismatch showing hash divergence. | `PI-01` | `model_mismatch` | **HIGH** | **HIGH** | **FULL** | `hash_mismatch` | Enforces that inference outputs were generated by the accredited, certified model artifact. |
| **22** | Inference Output Tampering | PI-01 finding, severity HIGH, output_mismatch revealing altered predictions. | `PI-01` | `output_mismatch` | **HIGH** | **HIGH** | **FULL** | `hash_mismatch` | Protects operational decisions by catching forged detection labels or altered telemetry. |
| **23** | Signed Manifest Field Alteration | PI-01 finding, severity HIGH, signature_invalid catching signature forgery. | `PI-01` | `signature_invalid` | **HIGH** | **HIGH** | **FULL** | `signature_failure` | Cryptographic integrity: proves that modifying even 1 bit in metadata invalidates signature. |
| **24** | Direct Nonce / Manifest Replay | PI-01 finding, severity MEDIUM, replay_detected flagging duplicate nonce. | `PI-01` | `replay_detected` | **MEDIUM** | **HIGH** | **FULL** | `replay_evidence` | Blocks replay attacks where adversaries resend historical telemetry to deceive operators. |
| **25** | Monotonic Sequence Regression | PI-01 finding, severity MEDIUM, replay_anomaly due to sequence regression. | `PI-01` | `replay_anomaly` | **MEDIUM** | **HIGH** | **FULL** | `monotonic_anomaly` | Detects time-rollback and replay reordering attacks in streaming video surveillance. |
| **26** | Missing Stream Events Gap | PI-01 finding, severity MEDIUM, replay_anomaly exposing missing stream events. | `PI-01` | `replay_anomaly` | **MEDIUM** | **HIGH** | **FULL** | `sequence_gap` | Detects stream jamming, frame dropping, or intentional event suppression by adversaries. |
| **27** | Fresh Nonce Duplicate Limitation | Provenance valid (no false replay alarm) with documented limitation notice. | `PI-01` | `provenance_valid` | **NONE** | **HIGH** | **FULL** | `documented_limitation` | Scientific honesty: documents that fresh nonces for identical outputs are out of replay scope. |

---

### Category D: Coverage & Confidence Orthogonality (Scenarios 28 – 32)

| # | Scenario Title | What Judge Sees | Detector(s) | Expected Finding | Risk | Confidence | Coverage | Evidence Type | SIH Judge Value |
|---|---|---|---|---|---|---|---|---|---|
| **28** | High Risk + High Confidence + Full Coverage | High Risk alert, High Confidence gauge, 100% Coverage score, complete findings. | All Applicable | Multiple Findings | **HIGH** | **HIGH** | **FULL** | `multi_detector_finding` | Authoritative defect conviction: evaluator knows this is a real, high-severity defect. |
| **29** | High Risk + Moderate Confidence | High Risk alert, but Confidence clearly shows MODERATE due to sparse scope. | `DI-02` | `label_flip` | **HIGH** | **MODERATE** | **PARTIAL** | `bounded_sample_finding` | Validates ADR-003: finding severity never artificially inflates overall confidence score. |
| **30** | None Risk + Low Confidence (Unverified) | Risk: NONE, but Confidence: LOW/MODERATE with prominent 'Not Verified' notice. | `MI-01` | None | **NONE** | **LOW** | **PARTIAL** | `sparse_coverage_gap` | Eliminates false security: 0 findings in an uninspected space is never labeled 'safe'. |
| **31** | Not Applicable Detector Exclusion | Inapplicable detector excluded from denominator, avoiding false penalty. | `DI-01`..`DI-04` | None | **NONE** | **HIGH** | **FULL** | `denominator_exclusion` | Mathematical rigor: detectors unsuitable for asset type do not penalize coverage score. |
| **32** | Partial Model Analysis (Weights-Only) | Coverage reduced from 100% to ~50% with table explaining inactive probes. | `MI-01`, `MI-02` | None (CoverageGap) | **NONE** | **MODERATE** | **PARTIAL** | `coverage_gap_table` | Operational clarity: analyst clearly sees what was inspected vs what remains unverified. |

---

### Category E: Security Hardening & Adversarial Defenses (Scenarios 33 – 40)

| # | Scenario Title | What Judge Sees | Defense Mechanism | Expected Result | Risk | Evidence Type | SIH Judge Value |
|---|---|---|---|---|---|---|---|
| **33** | Zip Slip Path Traversal Rejection | Upload fails with HTTP 422: path traversal attempt rejected. | Canonical path resolution & containment | HTTP 422 Unprocessable | **NONE** | `security_sandbox_exception` | Host protection: malicious archives cannot escape sandbox to overwrite system files. |
| **34** | Corrupted Zip Ingestion & Cleanup | Structured 422 error, scratch directories cleanly wiped, 0 leak. | Context-managed cleanup in ingestion pipeline | HTTP 422 Unprocessable | **NONE** | `fail_closed_cleanup` | Resource safety: broken archives do not crash background services or leak disk space. |
| **35** | Decompression Bomb / Oversized Limit | Immediate 422 rejection: file size exceeds configured safety limit. | Pre-extraction size quota inspection | HTTP 422 Unprocessable | **NONE** | `dos_quota_enforcement` | DoS defense: protects air-gapped field laptops from memory/disk exhaustion attacks. |
| **36** | Evidence Preview Path Traversal | Attempt to stream `/etc/passwd` or `../../..` returns HTTP 403 Forbidden. | Relative-to-dataset root path containment | HTTP 403 Forbidden | **NONE** | `chroot_containment` | Access control: preview endpoints cannot be abused as arbitrary filesystem readers. |
| **37** | Binary Evidence Artifact Safe Fallback | Preview renders safe 'Binary Model Weights' card with layer breakdown. | MIME sniffing guard & structural JSON fallback | HTTP 200 Structured | **NONE** | `safe_structural_inspector` | Memory safety: prevents browser memory exhaustion on multi-gigabyte neural binaries. |
| **38** | Malformed API Request / Schema Error | Clean structured 422 error JSON with validation detail; zero stack traces. | Pydantic v2 strict schema enforcement | HTTP 422 Structured | **NONE** | `structured_schema_validation` | Information hiding: external callers learn zero internal code lines or dependencies. |
| **39** | SQL Injection Resistance in Search | Queries like `' OR '1'='1` execute safely via parameterized SQLite. | Parameterized queries + SQLite FTS5 | HTTP 200 (0 matches) | **NONE** | `parameterized_query_safety` | Database defense: global search cannot be hijacked to extract unauthorized records. |
| **40** | Zero Secret Leakage Verification | API keys masked, private keys never in DB/reports, zero path leaks. | Path censoring & credential redaction policy | Zero Leakage | **NONE** | `redacted_confidentiality` | Air-gap confidentiality: guarantees zero leakage of private keys or environment paths. |

---

## 4. SIH26228 Problem Statement (PS) Requirement Coverage

This section explicitly maps every capability requested or implied by Problem Statement SIH26228 to its corresponding PRAMAAN detector, validation scenario, forensic evidence type, documented limitation, and formal implementation status.

| # | PS Requirement Area | Detector / Component | Scenario / Test Pointer | Forensic Evidence | Current Documented Limitation | Coverage Status |
|---|---|---|---|---|---|---|
| **PS-01** | **Common CV Dataset Formats: COCO** | Ingestion Engine + `DI-01`..`DI-05` | `test_ps_gap_coverage.py::TestCocoPSCapabilities` (Tests A, B, C) | `hash_match`, `label_conflict`, structured bbox bounds validation | Panoptic/segmentation masks parsed for bounding boxes; keypoint skeletons not evaluated for biomechanical plausibility. | **IMPLEMENTED** |
| **PS-02** | **Common CV Dataset Formats: YOLO** | Ingestion Engine + `DI-01`..`DI-05` | `test_ps_gap_coverage.py::TestYoloPSCapabilities` (Tests D, E, F) | `images/` + `labels/` association, `classes.txt` / `data.yaml` bounds validation | Text class name lookup supported; freeform unstructured labels require explicit delimiter schema. | **IMPLEMENTED** |
| **PS-03** | **Real Distribution-Shift Assurance** | `DI-04` (Robust Statistical Distribution-Outlier Detector) | `test_ps_gap_coverage.py::test_g_reference_vs_evaluation_distribution_shift` | Shift magnitude, per-feature standardized shifts, IQR envelope bounds, outlier proportion | Evaluates robust low-level photometric & dimensional feature distributions; does not claim semantic latent embeddings (e.g. CLIP). | **IMPLEMENTED** |
| **PS-04** | **Benign Operational Drift vs Suspicious Clusters** | `DI-04` | `test_ps_gap_coverage.py` (Tests H, I) | Explicit categories: `OPERATIONAL_DRIFT_INDICATOR`, `DISTRIBUTION_SHIFT`, `SUSPICIOUS_ANOMALY_CLUSTER` | Statistical clustering indicates divergence geometry; does not attribute malicious intent without corroborating multi-detector evidence. | **IMPLEMENTED** |
| **PS-05** | **Dataset Poisoning / Recurring Patterns** | `DI-03` (Recurring Localized Visual-Pattern Anomaly Detector) + `DI-05` | Scenario 06 + `test_ps_gap_coverage.py::test_j_recurring_trigger_with_contributor_concentration` | Localized patch coordinates, cross-sample recurrence count, contributor risk concentration | Flags localized visual pattern recurrence; does not claim formal mathematical proof of backdoor objective without training gradients. | **IMPLEMENTED** |
| **PS-06** | **Model Trigger-Like Convergence** | `MI-05` (Suspicious Trigger-Like Behavioral Convergence Detector) | Scenario 15 + `test_ps_gap_coverage.py::test_k_model_trigger_like_convergence_gate` | Clean baseline output diversity, candidate spatial perturbation response, convergence ratio | Requires executable ONNX computational graph (`WHITE_BOX`); PyTorch weights-only files emit explicit `CoverageGap`. Does not claim exhaustive Trojan proof (NP-hard). | **PARTIAL / ACCESS-DEPENDENT** |
| **PS-07** | **Model Parameter & Architecture Integrity** | `MI-01`, `MI-02`, `MI-04` | Scenarios 10, 11, 12, 13 | SHA-256 fingerprint, NaN/Inf counts, weight kurtosis/IQR, graph topology diff | Static parameter and graph inspection; does not execute live model quantization precision benchmarks at runtime. | **IMPLEMENTED** |
| **PS-08** | **Access Modes (White-Box, Metadata-Only)** | Orchestrator + Ingestion Engine | `test_ps_gap_coverage.py::test_l_access_modes_whitebox_vs_metadata_only` | `access_level` on ModelAsset (`WHITE_BOX`, `METADATA_ONLY`), explicit `CoverageGapRecord` | Remote black-box API probing (querying third-party endpoints over network) not implemented within air-gapped forensic scope. | **IMPLEMENTED (Local) / DOCUMENTED LIMITATION (Remote API)** |
| **PS-09** | **Inference Provenance & Replay Resistance** | `PI-01` (Inference Provenance Integrity) | Scenarios 19 – 27 | Ed25519 signature validity, SHA-256 binding (input/model/output), monotonic sequence checks | Sequential telemetry replay is blocked; fresh nonces generated for identical outputs without hardware TEE attestation are documented as out of scope. | **IMPLEMENTED / DOCUMENTED LIMITATION** |
| **PS-10** | **Evidence Localization (WHAT, WHERE, WHY, EVIDENCE)** | Core Assessment Engine & Repositories | All Scenarios (01–40, A–L) | Sample ID, filename, annotation ID, bbox coords, contributor, layer/tensor name, parameter stats, manifest hash, nonce | Localizes to dataset samples, annotations, and model layers; does not synthesize source code line numbers for external pipelines. | **IMPLEMENTED** |
| **PS-11** | **Tamper-Evident Audit Logging** | `AuditEventRepository` + Assessment Lifecycle | All Scenarios | Append-only SHA-256 hash-linked audit chain from genesis to seal | Tamper-evident within forensic database; does not use distributed Byzantine consensus or external blockchain. | **IMPLEMENTED** |
| **PS-12** | **Automated Dataset Remediation / Retraining** | N/A | Excluded by Design | N/A | PRAMAAN is strictly an assurance and forensic evidence platform. Unsupervised automated dataset modification or weight retraining is intentionally excluded. | **NOT IMPLEMENTED** |

---

## 5. Verification & Audit Trail Traceability

Every assessment executed in this suite writes a cryptographically linked, append-only audit event chain:
```
[GENESIS] assessment.created
   ├── [INGEST] dataset.registered
   ├── [INGEST] model.registered
   ├── [DETECTOR] detector.started / completed (DI-01..DI-05, MI-01..MI-05, PI-01)
   ├── [AGGREGATE] assessment.completed (Risk, Confidence, Coverage)
   └── [SEAL] audit_chain.verified (Ed25519 hash chain intact)
```

Verification command:
```powershell
.venv\Scripts\python.exe -m pytest tests/corpus/test_judge_validation_suite.py tests/corpus/test_ps_gap_coverage.py -v
```
All 40 scenarios + 12 PS gap tests execute **100% locally and offline**. Zero mock findings. Zero simulated evidence. Zero network dependencies.
