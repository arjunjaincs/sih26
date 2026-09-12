# PRAMAAN Assurance Methods

> Mapping of PS requirements to detection methods, access requirements, and implementation status.

Version: 2.0-DRAFT  
Last Updated: 2026-09-10

---

## 1. Method Status Definitions

| Status | Meaning |
|--------|---------|
| **IMPLEMENTED** | Code exists, tests pass, produces real evidence |
| **PARTIAL** | Core logic exists but incomplete (limited formats, missing edge cases) |
| **EXPERIMENTAL** | Research-grade, may produce unreliable results, explicitly flagged |
| **DEMO_ONLY** | Uses deterministic fixtures, never claims to be real analysis |
| **PLANNED** | Designed but not yet coded |
| **INFEASIBLE** | Determined to be impractical under current constraints |

---

## 2. Data Integrity Methods

### DI-01: Perceptual Hash Duplicate Detection

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `data.integrity.di01_duplicates` |
| **PS Requirement** | Near-duplicate flooding |
| **Category** | `DATA_INTEGRITY` |
| **Method** | Exact byte match (SHA-256) and perceptual near-duplicate clustering via 64-bit DCT pHash and dHash Hamming distance graph clustering (Union-Find). |
| **Required Access** | Dataset with images (offline local directory or COCO archive) |
| **Evidence Produced** | Duplicate clusters with representative hash, max Hamming distance, sample IDs, and file names (`EvidenceType.ANOMALY`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, `Pillow`, `numpy` |
| **Risk Semantics** | HIGH for exact byte duplicate clusters with size ≥ 3 or high duplicate ratios; MEDIUM for near-duplicate clusters; NONE if no duplicate clusters found. |
| **Confidence Semantics** | HIGH for deterministic hash collisions. Scaled by dataset size (ADR-003). |
| **Coverage Semantics** | Applicable when dataset asset provided. Evaluated across all readable images. |
| **Limitations** | Pixel and perceptual spatial frequency analysis only. Does not infer high-level semantic equivalence under severe non-linear photomorphic changes. |
| **Test Strategy** | Programmatic test battery: exact byte duplicates, perceptual near-duplicates (DCT variations), clean unique images, corrupt image handling. |

### DI-02: Label Integrity & Systematic Mislabelling

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `data.integrity.di02_label_integrity` |
| **PS Requirement** | Label flipping / systematic mislabelling |
| **Category** | `DATA_INTEGRITY` |
| **Method** | Two-tier analysis: (1) Near-duplicate label conflict detection: pairwise pHash comparison (Hamming ≤ 4) across samples with disjoint class labels; (2) Statistical class centroid outlier detection: bit-vector centroid distance per class compared against alternative class centroids to identify candidate label flips. |
| **Required Access** | Dataset with images AND class label annotations (COCO format or directory metadata/labels mapping, min 2 labeled samples) |
| **Evidence Produced** | Near-duplicate label conflict records with sample IDs and conflicting classes (`EvidenceType.ANOMALY`), Class centroid outlier projections with nearest-class distance comparison (`EvidenceType.STATISTICAL_TEST`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, `Pillow`, `numpy` |
| **Risk Semantics** | HIGH for direct contradictory labels on visually identical images; MEDIUM for statistical centroid flips to alternative classes; NONE if label assignments are consistent. |
| **Confidence Semantics** | HIGH for near-duplicate label contradictions; MODERATE for statistical centroid flips (dependent on class compactness). |
| **Coverage Semantics** | Emits `CoverageGap` (`label_flipping_and_mislabelling_not_assessed`) when dataset lacks annotations or contains < 2 labeled samples. |
| **Limitations** | Requires explicit class labels. Does not verify ground-truth semantic truth without external verified reference labels. Multi-modal class distributions may exhibit dispersion. |
| **Test Strategy** | Programmatic tests for clean labeled data, identical images with contradictory labels, statistical centroid flips with nearest-class matching, and missing-label pre-flight checks. |

### DI-03: Trigger & Spatial Pattern Anomaly Detection

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `data.integrity.di03_trigger_anomaly` |
| **PS Requirement** | Trigger injection |
| **Category** | `DATA_INTEGRITY` |
| **Method** | Multi-region spatial patch extraction (4 corners: top-left, top-right, bottom-left, bottom-right, and center; 16x16 / 25% bounding boxes). Computes local patch dHash and intensity variance. Flags high-contrast, non-flat localized patterns that recur across ≥ 3 distinct images. |
| **Required Access** | Dataset with images (at least 3 samples required) |
| **Evidence Produced** | Recurring spatial patch findings with bounding box coordinates, patch dHash, occurrence frequency, variance metric, and affected sample IDs (`EvidenceType.ANOMALY`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, `Pillow`, `numpy` |
| **Risk Semantics** | HIGH if recurring patch appears in ≥ 20% of dataset or ≥ 5 images; MEDIUM if recurring patch appears in ≥ 3 images; NONE if no recurring localized patches detected. |
| **Confidence Semantics** | HIGH for recurring localized high-contrast patches across distinct images. |
| **Coverage Semantics** | Emits `CoverageGap` (`trigger_injection_and_backdoor_patterns_not_assessed`) if dataset has < 3 samples. |
| **Limitations** | Detects localized spatial trigger patterns (stickers, watermarks, corners). Does not detect invisible blended, low-amplitude, or full-image sinusoidal backdoor perturbations without reference models. |
| **Test Strategy** | Programmatic tests for clean diverse images, synthetic corner checkerboard trigger injection across samples, low-variance corner filtering, and pre-flight sample count boundaries. |

### DI-04: Distribution Shift & Out-of-Distribution (OOD) Detection

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `data.integrity.di04_ood_distribution` |
| **PS Requirement** | OOD insertion |
| **Category** | `DATA_INTEGRITY` |
| **Method** | Computes 6-dimensional perceptual feature vector per sample: aspect ratio, file size density (bytes/pixel), RGB channel means, and luminance standard deviation. Computes robust median and Interquartile Range (IQR) standardized distances. Flags samples exceeding robust distance threshold (threshold: 3.5 IQR units). |
| **Required Access** | Dataset with images (at least 5 samples required for baseline estimation) |
| **Evidence Produced** | Outlier sample listings with distance metric, threshold, baseline median, and breakdown of anomalous dimensions (`EvidenceType.STATISTICAL_TEST`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, `Pillow`, `numpy` |
| **Risk Semantics** | MEDIUM if ≥ 2 outliers or distance ≥ 5.0; LOW if single moderate outlier detected; NONE if all samples fall within in-distribution baseline. |
| **Confidence Semantics** | MODERATE: heuristic in perceptual feature space. Confidence reflects sample volume and baseline stability. |
| **Coverage Semantics** | Emits `CoverageGap` (`out_of_distribution_and_anomalous_samples_not_assessed`) if dataset has < 5 samples. |
| **Limitations** | Evaluates low-level visual and geometric distribution parameters. Does not perform high-level semantic OOD classification without large pre-trained embedding foundation models. |
| **Test Strategy** | Programmatic tests for in-distribution baseline samples, extreme aspect ratio and inverted color outliers, sample size pre-flight thresholds, and determinism. |

### DI-05: Contributor / Source Risk Aggregation

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `data.integrity.di05_contributor_risk` |
| **PS Requirement** | Contributor/source risk aggregation |
| **Category** | `DATA_INTEGRITY` |
| **Method** | Cross-correlates all sample-level findings and evidence (from DI-01, DI-02, DI-03, DI-04) grouped by contributor/source origin. Identifies disproportionate defect concentrations where contributor defect rate $R_c \ge 30\%$ with $\ge 2$ defects and $R_c > 1.5 R_{\text{all}}$. Produces global multi-contributor risk summary. |
| **Required Access** | Dataset with contributor/source attribution (COCO annotations, subdirectories, or metadata.json) |
| **Evidence Produced** | Contributor defect concentration metrics (`EvidenceType.STATISTICAL_TEST`), Multi-contributor breakdown matrix comparing all identified sources (`EvidenceType.COMPARISON`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, SQLite database |
| **Risk Semantics** | HIGH if contributor defect rate ≥ 50% with ≥ 3 defects; MEDIUM if defect rate ≥ 30% with ≥ 2 defects; NONE if defects are distributed proportionally or zero defects found. |
| **Confidence Semantics** | HIGH: based on verified sample defect records aggregated from upstream detectors. |
| **Coverage Semantics** | Emits `CoverageGap` (`contributor_source_risk_not_assessed`) when dataset lacks contributor metadata. |
| **Limitations** | Attribution relies strictly on declared dataset metadata. If attribution is absent, reports that attribution is unavailable rather than inventing origins. Does not prove malicious intent. |
| **Test Strategy** | Programmatic tests for clean multi-contributor datasets, single contributor with concentrated defects, unattributed datasets, and multi-contributor comparative breakdown evidence. |

---

## 3. Model Integrity Methods

### MI-01: Model Integrity Fingerprinting & Multi-Layer Comparison

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `model.integrity.mi01_fingerprint` |
| **PS Requirement** | Detect substituted/modified models, behavioral fingerprinting |
| **Category** | `MODEL_INTEGRITY` |
| **Method** | Multi-layer cryptographic, structural, and behavioral fingerprinting: Layer 1 (raw binary SHA-256 and file size), Layer 2 (graph topology, input/output schemas, node/initializer counts, opset versions, PyTorch state dict keys), Layer 3 (deterministic reference-input battery: zeros, ones, seeded noise, output SHA-256 and moments), Layer 4 (comparative delta against stored baseline fingerprint). |
| **Required Access** | White-Box / Black-Box (ONNX runtime for behavioral, PyTorch weights_only for state dict) |
| **Evidence Produced** | Artifact digest and metadata, structural graph properties, deterministic probe output hashes and moments (`EvidenceType.MEASUREMENT`), field-by-field difference delta (`EvidenceType.COMPARISON`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, `numpy`, `onnxruntime`, `torch` |
| **Risk Semantics** | MEDIUM if behavioral output divergence or structural mismatch detected; LOW if artifact hash differs but structure matches; NONE if all compared fields match reference or when recording baseline. |
| **Confidence Semantics** | HIGH when structural and behavioral layers execute; MODERATE if behavioral layer unavailable; LOW if framework unavailable. |
| **Coverage Semantics** | Emits explicit `CoverageGap` when model framework is unavailable or model format lacks execution class. |
| **Limitations** | Behavioral battery requires an executable model format (ONNX or TorchScript). PyTorch raw state dicts cannot be executed without architecture code and are marked unavailable for execution. Differences indicate integrity deltas, not proof of malicious intent. |
| **Test Strategy** | Programmatic tests for clean ONNX, byte modification, node count changes, operator type modifications, output value divergence, missing reference, and format loading boundaries. |

### MI-02: Model Parameter Statistics

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `model.integrity.mi02_parameter_stats` |
| **PS Requirement** | Parameter statistics, anomaly detection |
| **Category** | `MODEL_INTEGRITY` |
| **Method** | Deep white-box inspection of model parameter tensors across ONNX (initializers), PyTorch (`state_dict` via safe `weights_only=True`), and TorchScript. Computes total parameter counts, tensor counts, dtype distribution, and tensor moments (min, max, mean, std, sparsity % zeros). Detects non-finite values (NaN, +Inf, -Inf), extreme weight magnitudes ($|w| > 10,000$ or $\sigma > 1,000$), and abnormal layer collapse (> 99.9% zeros in non-bias layers). |
| **Required Access** | White-Box (model file inspectable via safe deserialization) |
| **Evidence Produced** | Global parameter summary metrics, dtype distribution, non-finite value counts, and per-tensor statistical summaries (`EvidenceType.MEASUREMENT`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, `numpy`, `torch` (for PyTorch), fallback pure-Python protobuf parser for ONNX |
| **Risk Semantics** | HIGH/CRITICAL if NaN or Inf values detected; MEDIUM if extreme weight magnitude anomaly; LOW if abnormal layer sparsity detected; NONE if parameters exhibit healthy distributions. |
| **Confidence Semantics** | HIGH: direct mathematical measurement across all extracted model parameter tensors. |
| **Coverage Semantics** | Emits `CoverageGap` (`parameter_statistics_and_weight_integrity_not_assessed`) if model file is corrupted or format unsupported. |
| **Limitations** | Deep weight inspection requires inspectable parameter tensors. Does not infer semantic functionality of custom layer operations without architectural metadata. |
| **Test Strategy** | Programmatic tests for clean ONNX/PyTorch models, synthetic NaN/Inf weight injection, extreme weight magnitude anomalies, sparsity calculation, and determinism. |

### MI-03: Model Activation & Representation Statistics

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `model.integrity.mi03_activation_stats` |
| **PS Requirement** | Activation statistics, representation collapse |
| **Category** | `MODEL_INTEGRITY` |
| **Method** | Instruments model execution across a calibrated deterministic probe battery (zeros, ones, spatial contrast gradient, seeded noise). Extracts bounded intermediate layer activations and output tensors. Computes layer activation moments (mean, std, min, max), dead representation ratios (% of zero activations across non-zero probes), and numerical instability (NaN/Inf in forward pass). |
| **Required Access** | White-Box / Black-Box execution (executable ONNX or TorchScript model) |
| **Evidence Produced** | Monitored layer activation statistics, dead activation ratios per probe, numerical overflow alerts (`EvidenceType.MEASUREMENT`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, `numpy`, `onnxruntime`, `torch` (for TorchScript) |
| **Risk Semantics** | HIGH if NaN/Inf activations detected during forward execution; MEDIUM if severe representation collapse detected (> 98% dead activations on all non-zero probes); NONE if activation dispersion is healthy. |
| **Confidence Semantics** | HIGH when executed on calibrated deterministic probe suite. |
| **Coverage Semantics** | Emits explicit `CoverageGap` (`internal_representation_and_activation_health_not_assessed`) when model is a raw PyTorch state dict without an executable computation graph. |
| **Limitations** | Requires an executable computation graph (ONNX or TorchScript). Bounded to initial monitored layers to avoid memory exhaustion on deep networks. Dynamic conditional branches not activated by the probe battery are noted. |
| **Test Strategy** | Programmatic tests for clean ONNX activation tracing, multi-layer intermediate node extraction, synthetic dead representation models, and explicit PyTorch state dict coverage gap emission. |

### MI-04: Reference Model Comparison Battery

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `model.integrity.mi04_reference_comparison` |
| **PS Requirement** | Reference model comparison, reference battery |
| **Category** | `MODEL_INTEGRITY` |
| **Method** | Multi-layer comparative assurance between an analyzed model artifact and a supplied reference baseline model or stored profile. Compares: Layer 1 (cryptographic SHA-256 byte match), Layer 2 (graph topology, input/output schemas, parameter counts), Layer 3 (parameter statistical alignment and weight distance), Layer 4 (behavioral output divergence across deterministic probe battery: MSE, Max Absolute Difference, Cosine Similarity). |
| **Required Access** | Candidate model paired with an authorized reference model file or stored reference profile |
| **Evidence Produced** | Detailed comparison table with cryptographic hashes, schema diffs, behavioral MSE, MAD, and cosine similarity (`EvidenceType.COMPARISON`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, `numpy`, `onnxruntime`, `torch` |
| **Risk Semantics** | EXACT_MATCH / EQUIVALENT (MSE ≤ 1e-6) → NONE (Confidence HIGH); BEHAVIORAL_DIVERGENCE (MSE > 1e-6) → MEDIUM (Confidence HIGH); STRUCTURAL_MODIFICATION → MEDIUM (Confidence HIGH); MODEL_SUBSTITUTION / FORMAT_MISMATCH → HIGH (Confidence HIGH). |
| **Confidence Semantics** | HIGH: direct comparative execution against ground-truth authorized reference artifact. |
| **Coverage Semantics** | Emits `CoverageGap` (`reference_model_comparison_and_drift_not_assessed`) if no reference model artifact or reference profile is supplied. |
| **Limitations** | Comparative assurance is only as reliable as the authenticity of the reference model. If reference is missing, reports an explicit gap rather than guessing. Differences indicate divergence, not automatic malice. |
| **Test Strategy** | Programmatic tests for exact cryptographic match, structural difference, weight modification/behavioral divergence, format mismatch substitution, and stored profile comparison. |

### MI-05: Model Trigger & Behavioral Perturbation Search

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `model.integrity.mi05_trigger_anomaly` |
| **PS Requirement** | Trigger search / reconstruction, backdoor detection |
| **Category** | `MODEL_INTEGRITY` |
| **Method** | Evaluates whether candidate localized spatial transformations or trigger patterns cause abnormal, consistent output behavior or Trojan-like target output convergence. Generates 4 diverse clean baseline probe inputs (neutral gray, horizontal ramp, vertical ramp, noise) and applies a bounded candidate perturbation suite (top-left checkerboard, bottom-right checkerboard, center watermark, control uniform bias). Evaluates output shift and Target Mode Convergence Ratio: $CR = \text{Diversity}(\text{perturbed}) / \text{Diversity}(\text{clean})$. When $CR < 0.15$ and shift is elevated, detects invariant target mode collapse. |
| **Required Access** | Black-Box / White-Box execution (executable ONNX or TorchScript model) |
| **Evidence Produced** | Baseline clean pairwise diversity, per-perturbation output shift, perturbed pairwise diversity, and target convergence ratio metrics (`EvidenceType.MEASUREMENT`) |
| **Implementation Status** | **IMPLEMENTED** |
| **Dependencies** | Python stdlib, `numpy`, `onnxruntime`, `torch` |
| **Risk Semantics** | HIGH if candidate perturbation induces abnormal target mode convergence ($CR < 0.15$ and elevated shift); NONE if model exhibits smooth, proportional perturbation response without target collapse. |
| **Confidence Semantics** | HIGH for tested candidate spatial trigger suite. |
| **Coverage Semantics** | Emits explicit `CoverageGap` (`trigger_sensitivity_and_backdoor_convergence_not_assessed`) when model is a non-executable format (PyTorch state dict). |
| **Limitations** | Tests concrete localized candidate patch patterns. Does NOT guarantee detection of complex blended, invisible, or semantic triggers without access to original training distributions. Honest engineering boundary: absence of detected trigger sensitivity does not prove absence of all backdoors. |
| **Test Strategy** | Programmatic tests for clean model smooth perturbation response, simulated trigger sensitivity with target mode convergence, determinism, and non-executable format coverage gaps. |
| **Confidence Semantics** | Low-Moderate: research method, not production-validated at scale. |
| **Limitations** | Computationally expensive. May fail against sophisticated attacks (composite triggers, clean-label). Assumes L_p norm trigger model. Original paper: Wang et al. (IEEE S&P 2019). PRAMAAN implements a simplified version, not the full optimization pipeline. |
| **Test Strategy** | Train a backdoored model with known trigger; verify Neural Cleanse detects target class and approximate trigger. |

---

## 4. Inference Provenance Methods

### IP-01: Manifest Construction & Binding

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `ip.manifest_binding` |
| **PS Requirement** | Bind input/model/output, timestamp, nonce |
| **Category** | INFERENCE_PROVENANCE |
| **Method** | Construct a canonical inference manifest binding input hash, model identity, model hash, preprocessing config, inference config, output hash, timestamp, nonce, and sequence number. Sign with Ed25519. |
| **Required Access** | Full inference pipeline access |
| **Evidence Produced** | Signed manifest |
| **Implementation Status** | PLANNED (Phase 1) |
| **Dependencies** | `hashlib`, `cryptography` (Ed25519) |
| **Confidence Semantics** | HIGH: cryptographic binding. |
| **Limitations** | Trust rooted in local key management. Key compromise defeats the system. |

### IP-02: Manifest Verification

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `ip.manifest_verification` |
| **PS Requirement** | Detect post-hoc alteration, detect output substitution |
| **Category** | INFERENCE_PROVENANCE |
| **Method** | Verify Ed25519 signature. Re-hash each bound element and compare against manifest hashes. Flag any mismatch. |
| **Required Access** | Manifest + original assets |
| **Evidence Produced** | Verification result per binding, overall pass/fail |
| **Implementation Status** | PLANNED (Phase 1) |
| **Dependencies** | `hashlib`, `cryptography` |
| **Confidence Semantics** | HIGH: cryptographic verification. |
| **Limitations** | Cannot verify if the signing key was compromised. |

### IP-03: Replay Detection

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `ip.replay_detection` |
| **PS Requirement** | Detect replay |
| **Category** | INFERENCE_PROVENANCE |
| **Method** | Check nonce uniqueness against history. Verify monotonic sequence numbers. Flag duplicate nonces or sequence gaps/reversals. |
| **Required Access** | Manifest history |
| **Evidence Produced** | Duplicate nonce alerts, sequence analysis |
| **Implementation Status** | PLANNED (Phase 1) |
| **Dependencies** | None beyond core |
| **Confidence Semantics** | HIGH: deterministic check. |
| **Limitations** | Requires persisted manifest history. First-run has no history to compare against. |

---

## 5. Distribution Drift Methods

### DD-01: Embedding Distribution Comparison

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `dd.embedding_distribution` |
| **PS Requirement** | Detect distribution deviation |
| **Category** | DISTRIBUTION_DRIFT |
| **Method** | Compute embeddings for reference and current datasets. Compare distributions using Maximum Mean Discrepancy (MMD) with RBF kernel. |
| **Required Access** | Reference dataset + current dataset |
| **Evidence Produced** | MMD statistic, p-value via permutation test, effect size |
| **Implementation Status** | PLANNED (Phase 2) |
| **Dependencies** | `torch`, `torchvision`, `numpy`, `scipy` |
| **Confidence Semantics** | Moderate-High: depends on embedding quality and sample size. |
| **Limitations** | Requires sufficient samples for meaningful statistics. Embedding space may not capture all relevant distribution properties. |

### DD-02: Statistical Shift Tests

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `dd.statistical_tests` |
| **PS Requirement** | Detect distribution deviation, characterize shift |
| **Category** | DISTRIBUTION_DRIFT |
| **Method** | Compute per-feature KS test and PSI (Population Stability Index) between reference and current distributions. Report per-feature and aggregate results. |
| **Required Access** | Reference distribution statistics + current dataset |
| **Evidence Produced** | Per-feature KS statistics and p-values, PSI scores, aggregate shift characterization |
| **Implementation Status** | PLANNED (Phase 2) |
| **Dependencies** | `numpy`, `scipy` |
| **Confidence Semantics** | High: well-understood statistical tests with calibrated p-values. |
| **Limitations** | Feature selection affects sensitivity. Multiple testing correction needed. Does not explain why shift occurred. |

### DD-03: Image-Level Metadata Drift

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `dd.metadata_drift` |
| **PS Requirement** | Characterize shift |
| **Category** | DISTRIBUTION_DRIFT |
| **Method** | Compare low-level image statistics between reference and current data: mean brightness, contrast, resolution distribution, aspect ratio distribution, color histogram statistics. Flag significant differences. |
| **Required Access** | Reference dataset + current dataset |
| **Evidence Produced** | Per-metric comparison, histograms, shift magnitude |
| **Implementation Status** | PLANNED (Phase 2) |
| **Dependencies** | `Pillow`, `numpy` |
| **Confidence Semantics** | Moderate: low-level statistics may miss semantic drift. |
| **Limitations** | Captures superficial properties only. Semantic content shift requires embedding-based methods. |

---

## 6. Requirements Traceability Matrix

| PS Requirement | Subsystem | Method(s) | Access | Status |
|---------------|-----------|-----------|--------|--------|
| Trigger injection / poisoned samples | Data Integrity | DI-03, DI-05 + Model: MI-05, MI-06 | Dataset + WHITE_BOX (for model methods) | PLANNED |
| Label flipping | Data Integrity | DI-03 | Dataset with labels | PLANNED |
| Near-duplicate flooding | Data Integrity | DI-01, DI-02 | Dataset with images | PLANNED |
| OOD insertion | Data Integrity | DI-02, DI-05 | Dataset with images | PLANNED |
| Contributor risk aggregation | Data Integrity | DI-04 | Dataset with contributor metadata | PLANNED |
| Model substitution | Model Integrity | MI-01, MI-02 | BLACK_BOX minimum | PLANNED |
| Behavioral anomalies | Model Integrity | MI-02, MI-03, MI-04 | BLACK_BOX minimum (more with WHITE_BOX) | PLANNED |
| Backdoor behavior | Model Integrity | MI-02, MI-04, MI-05, MI-06 | WHITE_BOX preferred | PLANNED |
| Behavioral fingerprinting | Model Integrity | MI-02 | BLACK_BOX | PLANNED |
| Trigger search | Model Integrity | MI-06 | WHITE_BOX | PLANNED (EXPERIMENTAL) |
| Parameter/activation statistics | Model Integrity | MI-03, MI-04 | WHITE_BOX | PLANNED |
| Reference battery comparison | Model Integrity | MI-02 | BLACK_BOX | PLANNED |
| Bind input/model/output | Inference Provenance | IP-01 | Full pipeline | PLANNED |
| Timestamp / nonce | Inference Provenance | IP-01 | Full pipeline | PLANNED |
| Detect post-hoc alteration | Inference Provenance | IP-02 | Manifest + assets | PLANNED |
| Detect output substitution | Inference Provenance | IP-02 | Manifest + assets | PLANNED |
| Detect replay | Inference Provenance | IP-03 | Manifest history | PLANNED |
| Distribution deviation | Distribution Drift | DD-01, DD-02, DD-03 | Reference + current dataset | PLANNED |
| Characterize shift | Distribution Drift | DD-02, DD-03 | Reference + current dataset | PLANNED |
| Calibrated confidence/risk | All | Evidence Fusion Engine | All findings | PLANNED |
| Tamper-evident audit trail | Audit | Audit Ledger | System-wide | PLANNED |
| Reproducible assessments | All | Reproducibility framework | Configuration + seeds | PLANNED |
| Verifiable reports | Report | Report signing | Assessment output | PLANNED |

---

## 7. Prior Art and Attribution

PRAMAAN acknowledges the following prior work:

| Work | Relevance | PRAMAAN's Relationship |
|------|-----------|----------------------|
| Neural Cleanse (Wang et al., 2019) | Backdoor trigger reverse-engineering | MI-06 implements a simplified version; explicitly labeled EXPERIMENTAL |
| Spectral Signatures (Tran et al., 2018) | Poisoning detection via SVD | MI-05 implements the core idea; limitations documented |
| STRIP (Gao et al., 2019) | Runtime trigger detection via entropy | Considered but NOT implemented in v1 (requires runtime inference interception) |
| IBM ART | Adversarial robustness toolkit | Referenced as prior art; PRAMAAN does not wrap ART |
| C2PA | Content provenance standard | Architectural inspiration; PRAMAAN uses a simpler local-only provenance model |
| SLSA / Sigstore | Software supply chain integrity | Conceptual influence on audit chain design |
| BackdoorBench / TrojanZoo | Backdoor research benchmarks | May be used for validation; not integrated as dependencies |

PRAMAAN's differentiators are not in individual detection algorithms but in:
1. Unified data + model + inference assurance in one platform
2. Evidence-first analyst workflow
3. Offline/air-gapped operation
4. Explicit risk/confidence/coverage separation
5. Cryptographically verifiable provenance
6. Honest method-status reporting
