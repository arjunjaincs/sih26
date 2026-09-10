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
| **Detector ID** | `di.phash_duplicates` |
| **PS Requirement** | Near-duplicate flooding |
| **Category** | DATA_INTEGRITY |
| **Method** | Compute pHash and dHash for every sample. Flag pairs with Hamming distance ≤ threshold (default: 10 bits for pHash-64). Cluster near-duplicates. |
| **Required Access** | Dataset with images |
| **Evidence Produced** | List of near-duplicate pairs/clusters with distances, visualization of clusters |
| **Implementation Status** | PLANNED (Phase 1) |
| **Dependencies** | `imagehash`, `Pillow` |
| **Confidence Semantics** | High: threshold is deterministic. Confidence reflects sample coverage, not detection accuracy. |
| **Limitations** | Cannot detect semantic duplicates with different visual appearance. Threshold is heuristic. Very large datasets may be slow without LSH indexing. |
| **Test Strategy** | Inject known duplicate pairs at various Hamming distances; verify detection at each threshold. |

### DI-02: Embedding-Based Similarity Analysis

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `di.embedding_similarity` |
| **PS Requirement** | Near-duplicate flooding, OOD insertion |
| **Category** | DATA_INTEGRITY |
| **Method** | Extract embeddings from a pretrained vision model (e.g., ResNet-50 penultimate layer). Compute pairwise cosine similarity. Flag clusters of unusually high similarity (flooding) or samples far from any cluster centroid (OOD). |
| **Required Access** | Dataset with images |
| **Evidence Produced** | Similarity matrix statistics, identified clusters, OOD candidates with distances |
| **Implementation Status** | PLANNED (Phase 2) |
| **Dependencies** | `torch`, `torchvision` |
| **Confidence Semantics** | Moderate: embedding quality depends on backbone model and domain fit. |
| **Limitations** | Backbone model may not capture domain-specific features. Requires loading a pretrained model (but this is a PRAMAAN internal model, not the model under assessment). |
| **Test Strategy** | Insert known OOD images from a different domain; verify they are flagged. Insert duplicates with augmentation; verify clustering. |

### DI-03: Label Anomaly Detection

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `di.label_anomaly` |
| **PS Requirement** | Label flipping / systematic mislabelling |
| **Category** | DATA_INTEGRITY |
| **Method** | Cross-reference image embeddings against assigned labels. Identify samples whose embedding is far from the centroid of their assigned class but close to another class. Report as candidate label flips. Statistical test for systematic class-to-class flipping patterns. |
| **Required Access** | Dataset with images AND labels |
| **Evidence Produced** | List of suspect samples, embedding distances, suggested correct labels, class confusion matrix |
| **Implementation Status** | PLANNED (Phase 2) |
| **Dependencies** | `torch`, `torchvision`, `numpy`, `scipy` |
| **Confidence Semantics** | Moderate: depends on embedding quality and class separability. |
| **Limitations** | Ambiguous samples near class boundaries will generate false positives. Requires classes to be visually distinguishable. |
| **Test Strategy** | Flip labels for N% of samples in a known dataset; measure recall and precision at various N. |

### DI-04: Contributor Risk Aggregation

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `di.contributor_aggregation` |
| **PS Requirement** | Contributor/source-level risk aggregation |
| **Category** | DATA_INTEGRITY |
| **Method** | Aggregate sample-level findings by contributor. Compute per-contributor risk metrics: flagged sample rate, dominant finding categories, severity distribution. Flag contributors whose flagged rate exceeds threshold. |
| **Required Access** | Dataset with contributor attribution |
| **Evidence Produced** | Per-contributor risk summary, comparison to overall dataset rates |
| **Implementation Status** | PLANNED (Phase 2) |
| **Dependencies** | None beyond core domain |
| **Confidence Semantics** | Depends on confidence of underlying sample-level detectors. |
| **Limitations** | Requires contributor metadata in dataset manifest. Small contributors have insufficient statistical power. |
| **Test Strategy** | Create dataset with one "malicious" contributor inserting known-bad samples; verify contributor is flagged. |

### DI-05: OOD / Anomaly Detection (Statistical)

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `di.ood_statistical` |
| **PS Requirement** | OOD insertion |
| **Category** | DATA_INTEGRITY |
| **Method** | Fit a multivariate Gaussian (or GMM) to the embedding distribution of the declared dataset. Score each sample by Mahalanobis distance. Flag samples exceeding a threshold (e.g., 99.5th percentile of the fitted distribution). |
| **Required Access** | Dataset with images |
| **Evidence Produced** | Mahalanobis distance per sample, threshold used, distribution fit statistics |
| **Implementation Status** | PLANNED (Phase 2) |
| **Dependencies** | `torch`, `torchvision`, `numpy`, `scipy` |
| **Confidence Semantics** | Moderate: Gaussian assumption may not hold for complex distributions. |
| **Limitations** | Assumes approximately Gaussian embedding distribution. High dimensionality may degrade Mahalanobis distance. |
| **Test Strategy** | Insert images from ImageNet into a COCO subset; verify they are flagged as OOD. |

---

## 3. Model Integrity Methods

### MI-01: Artifact Fingerprinting

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `mi.artifact_fingerprint` |
| **PS Requirement** | Model substitution |
| **Category** | MODEL_INTEGRITY |
| **Method** | SHA-256 hash of the model file. Compare against declared/registered hash. Flag mismatch. |
| **Required Access** | BLACK_BOX (file-level) |
| **Evidence Produced** | Expected hash, actual hash, match/mismatch |
| **Implementation Status** | PLANNED (Phase 1) |
| **Dependencies** | `hashlib` (stdlib) |
| **Confidence Semantics** | HIGH: SHA-256 collision is infeasible. |
| **Limitations** | Only detects file-level substitution. Does not detect partial weight modification within a valid model file. |
| **Test Strategy** | Modify one byte of a model file; verify hash mismatch is detected. |

### MI-02: Behavioral Consistency Testing

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `mi.behavioral_consistency` |
| **PS Requirement** | Behavioral anomalies, backdoor-like behavior |
| **Category** | MODEL_INTEGRITY |
| **Method** | Run model on a reference battery of curated test inputs. Compare outputs against expected reference outputs. Flag significant deviations in accuracy, confidence distribution, or class distribution. |
| **Required Access** | BLACK_BOX (inference access) |
| **Evidence Produced** | Per-input output comparison, aggregate statistics, deviation metrics |
| **Implementation Status** | PLANNED (Phase 2) |
| **Dependencies** | `torch` or `onnxruntime`, `numpy` |
| **Confidence Semantics** | Moderate: limited by reference battery coverage. Targeted backdoors may not activate on clean inputs. |
| **Limitations** | Cannot detect backdoors that only trigger on specific inputs not in the reference battery. Battery design is critical. |
| **Test Strategy** | Substitute a model with different weights; verify behavioral deviation is detected. |

### MI-03: Parameter Statistics Analysis

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `mi.parameter_statistics` |
| **PS Requirement** | Behavioral anomalies, backdoor detection |
| **Category** | MODEL_INTEGRITY |
| **Method** | Extract per-layer weight statistics (mean, std, min, max, sparsity, Frobenius norm). Compare against expected ranges or reference model. Flag anomalous layers. |
| **Required Access** | WHITE_BOX |
| **Evidence Produced** | Per-layer statistics table, anomalous layers, comparison to reference |
| **Implementation Status** | PLANNED (Phase 2) |
| **Dependencies** | `torch`, `numpy` |
| **Confidence Semantics** | Low-Moderate: statistical anomalies do not confirm malicious modification. |
| **Limitations** | No ground truth for "normal" parameter distributions without a reference. Fine-tuned models naturally deviate. |
| **Test Strategy** | Inject a small trigger pattern into model weights; verify statistical anomaly in affected layer. |

### MI-04: Activation Analysis

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `mi.activation_analysis` |
| **PS Requirement** | Behavioral anomalies, backdoor detection |
| **Category** | MODEL_INTEGRITY |
| **Method** | Register forward hooks on model layers. Pass reference inputs and collect activation maps. Analyze for unusual patterns: dead neurons, abnormally high activations, spatial concentration (trigger indicators). |
| **Required Access** | WHITE_BOX (or GRAY_BOX if hooks are externally available) |
| **Evidence Produced** | Activation statistics, spatial heat maps, anomaly scores per layer |
| **Implementation Status** | PLANNED (Phase 3) |
| **Dependencies** | `torch`, `numpy` |
| **Confidence Semantics** | Low-Moderate: activation anomalies have many benign causes. |
| **Limitations** | Only works with PyTorch models (hook API). Interpretation requires domain expertise. |
| **Test Strategy** | Train a model with a known trigger patch; verify activation anomaly near trigger location. |

### MI-05: Spectral Signature Analysis

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `mi.spectral_signatures` |
| **PS Requirement** | Backdoor detection (Tran et al., 2018) |
| **Category** | MODEL_INTEGRITY |
| **Method** | Compute representation vectors for a dataset of clean inputs. Perform SVD on the covariance matrix of representations. Outlier score based on top singular vector correlations. Poisoned samples correlate strongly with the top singular vector. |
| **Required Access** | WHITE_BOX + reference dataset |
| **Evidence Produced** | Singular value decomposition results, outlier scores, flagged samples |
| **Implementation Status** | PLANNED (Phase 3) |
| **Dependencies** | `torch`, `numpy`, `scipy` |
| **Confidence Semantics** | Moderate: validated in research literature but depends on attack type. |
| **Limitations** | Assumes poisoned samples form a separable cluster in representation space. May not detect all backdoor types (e.g., clean-label attacks). Requires reference dataset. Original paper: Tran, Li, Madry (NeurIPS 2018). |
| **Test Strategy** | Insert known poisoned samples; verify spectral separation. Test against clean dataset for false positive rate. |

### MI-06: Neural Cleanse (Simplified)

| Attribute | Value |
|-----------|-------|
| **Detector ID** | `mi.neural_cleanse` |
| **PS Requirement** | Backdoor/trigger search (Wang et al., 2019) |
| **Category** | MODEL_INTEGRITY |
| **Method** | For each output class, optimize a minimal perturbation (trigger pattern) that causes misclassification to that class. If one class requires an anomalously small perturbation, suspect a backdoor targeting that class. Anomaly Index = median(L1_norms) / min(L1_norms). |
| **Required Access** | WHITE_BOX (requires gradient access) |
| **Evidence Produced** | Per-class trigger L1 norms, anomaly index, reconstructed trigger pattern if found |
| **Implementation Status** | PLANNED (Phase 3) — **EXPERIMENTAL** |
| **Dependencies** | `torch`, `numpy` |
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
