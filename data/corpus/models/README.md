# PRAMAAN v1 — Model Integrity Assurance Corpus

## Overview

The **PRAMAAN v1 Model Integrity Corpus** is a fully offline, deterministic, reproducible benchmark model suite designed to validate the model integrity assurance pipeline (detectors **MI-01 through MI-05**).

The corpus comprises **9 scenarios** covering **14 procedurally synthesized model artifacts** (~50 KB total footprint). Each scenario isolates specific integrity concerns, parameter anomalies, activation representations, localized Trojan perturbations, or format coverage boundaries.

---

## Scenarios Matrix

| Scenario ID | Name | Category | Framework | Injected Mutation / Condition | Expected Risk | Expected Confidence |
|---|---|---|:---:|---|:---:|:---:|
| `01_clean_reference` | Clean Baseline with Reference | Clean Baseline | ONNX | Zero mutation; identical candidate and reference | NONE | HIGH |
| `02_model_substitution` | Architecture Substitution | Substitution | ONNX | Candidate is Relu; Reference is Add_Bias | MEDIUM | HIGH |
| `03_parameter_corruption` | Non-Finite Weight Tampering | Parameter Mod | ONNX | Initializers injected with IEEE 754 NaN weights | HIGH | HIGH |
| `04_weight_magnitude_anomaly` | Statistical Weight Outlier | Parameter Mod | ONNX | Weights exceed magnitude threshold (|w| > 10,000) | MEDIUM | HIGH |
| `05_activation_collapse` | Dead Representation Syndrome | Activation | ONNX | Heavy negative bias (-1000.0) clamping Relu outputs to 0.0 | MEDIUM | LOW |
| `06_trigger_convergence` | Trojan Shortcut Convergence | Perturbation | ONNX | Scalar input graph where corner patch collapses diversity | HIGH | HIGH |
| `07_missing_reference` | Standalone Baseline Enrollment | Missing Ref | ONNX | Healthy model enrolled without reference baseline | NONE | HIGH |
| `08_state_dict_coverage_gap` | Non-Executable State Dict | Access Gap | PyTorch | Valid state dict tensor dictionary without architecture class | NONE | LOW |
| `09_malformed_artifact` | Corrupt Binary Header | Security Boundary | ONNX | 64 bytes of invalid protobuf bytes (fail-closed) | FAIL_CLOSED | REJECT |

---

## Design Principles & Claim Discipline

1. **Zero Ground-Truth Leakage**:
   - `ground_truth.json` is stored strictly in `ground_truth/` and never inside `input/`.
   - Production manifests (`model_manifest.json`) contain only operational metadata (filenames, dimensions, hashes, roles).

2. **Deterministic & Offline**:
   - Pure mathematical synthesis using raw protobuf encoders and CPU PyTorch tensors with fixed seed (`42`).
   - Zero external downloads, network requests, or remote model dependencies.

3. **Honest Engineering Claim Discipline**:
   - **MI-01**: Computes cryptographic, structural, and behavioral fingerprints. Reports observable differences without claiming malicious tampering.
   - **MI-02**: Evaluates parameter moments and non-finite quantities. Reports numerical corruption or weight outliers without claiming intentional sabotage.
   - **MI-03**: Measures layer activation dispersion across calibrated probes. Flags representation collapse or numerical instability.
   - **MI-04**: Conducts comparative reference batteries (MSE, Cosine, hash). Reports behavioral or structural divergence.
   - **MI-05**: Tests candidate localized spatial perturbation hypotheses. Reports Trojan-like target mode convergence without claiming absolute backdoor guarantees.

---

## Directory Layout

```
data/corpus/models/
├── corpus_manifest.json
├── README.md
└── scenarios/
    ├── 01_clean_reference/
    │   ├── ground_truth/
    │   │   └── ground_truth.json
    │   ├── input/
    │   │   ├── model.onnx
    │   │   └── reference.onnx
    │   └── model_manifest.json
    ├── ...
    └── 09_malformed_artifact/
        ├── ground_truth/
        │   └── ground_truth.json
        ├── input/
        │   └── corrupt_header.onnx
        └── model_manifest.json
```

---

## CLI Usage

```bash
# Generate model corpus with default output directory (data/corpus/models) and seed 42
python -m backend.tools.model_corpus_generator --output data/corpus/models --seed 42

# Generate and immediately run in-memory detector validation loop
python -m backend.tools.model_corpus_generator --output data/corpus/models --validate
```
