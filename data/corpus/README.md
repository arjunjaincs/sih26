# PRAMAAN v1 — Training & Data Integrity Corpus

## Overview

The **PRAMAAN v1 Training and Data Integrity Corpus** is a fully offline, deterministic, reproducible benchmark dataset suite designed to validate the data integrity assurance pipeline (detectors **DI-01 through DI-05**).

The corpus comprises **9 scenarios** totaling **107 procedural images** (~500 KB total footprint). Each scenario isolates specific integrity concerns or demonstrates controlled multi-defect interactions, verifying detector sensitivity, precision, and orthogonality.

---

## Scenarios Matrix

| Scenario ID | Name | Primary Target | Total Samples | Injected Anomalies | Expected Detectors | Overall Risk |
|---|---|---|:---:|---|---|:---:|
| `01_clean_baseline` | Clean Training Baseline | Baseline control | 10 | None | None | NONE |
| `02_exact_duplicate` | Exact Duplicate Injection | DI-01 (Exact) | 10 | 2 exact duplicate pairs (SHA-256 identical) | DI-01 (MEDIUM) | MEDIUM |
| `03_near_duplicate` | Near Duplicate Injection | DI-01 (Near) | 10 | 2 near-duplicate pairs (pHash Hamming dist ~6) | DI-01 (LOW) | LOW |
| `04_label_flip` | Pairwise Label Contradiction | DI-02 (Conflict) | 10 | 1 near-identical pair with conflicting labels | DI-02 (HIGH), DI-01 (LOW) | HIGH |
| `05_systematic_mislabelling` | Systematic Mislabelling | DI-02 (Systematic) | 13 | 3 pedestrian samples labeled as vehicles | DI-02 (HIGH), DI-01 (LOW) | HIGH |
| `06_recurring_pattern` | Localized Recurring Pattern | DI-03 (Pattern) | 12 | 4 distinct images with bottom-right 16x16 checkerboard | DI-03 (HIGH) | HIGH |
| `07_ood_distribution` | Multivariate OOD Outliers | DI-04 (Distribution) | 12 | 1 tall aspect (32x128), 1 wide aspect (128x32) | DI-04 (MEDIUM) | MEDIUM |
| `08_contributor_concentration` | Contributor Risk Clustering | DI-05 (Attribution) | 12 | 4 defects concentrated in `pipeline_gamma` (100%) | DI-05 (HIGH), DI-01, DI-02 | HIGH |
| `09_mixed_scenario` | Unified Multi-Anomaly | DI-01..DI-05 | 18 | Combines duplicates, conflicts, pattern, OOD, contributor clustering | ALL 5 DETECTORS | HIGH |

---

## Design Principles & Claim Discipline

1. **Zero Ground-Truth Leakage**:
   - Ground truth metadata (`ground_truth.json`) is strictly stored outside the `input/` directory and is **never** packaged into upload archives (`scenario_XX.zip`).
   - Production manifests (`dataset_manifest.json` and `metadata.json`) contain only operational metadata (filenames, dimensions, hashes, labels, and contributors).

2. **Deterministic & Offline**:
   - Synthesized using pure mathematical drawing primitives, pseudo-random generators seeded by fixed master seed (`42`), and deterministic ZIP packaging (`(2026, 1, 1, 0, 0, 0)` timestamp).
   - Zero external downloads, network requests, or heavy external datasets.

3. **Honest Claim Boundaries**:
   - **DI-01**: Flags perceptual duplicate clusters. Does not claim malicious volume flooding.
   - **DI-02**: Identifies pairwise label contradiction or centroid deviation. Does not assert intentional mislabeling or adversary origin.
   - **DI-03**: Detects localized recurring spatial patterns across disparate images. Does not claim definitive Trojan/backdoor insertion without behavioral model verification.
   - **DI-04**: Identifies low-level geometric and photometric multivariate statistical outliers. Does not claim semantic out-of-distribution guarantee.
   - **DI-05**: Detects statistical concentration of upstream defects attributed to a single pipeline or contributor. Does not assert insider threat or intentional sabotage.

---

## Directory Layout

```
data/corpus/
├── corpus_manifest.json
├── README.md
└── scenarios/
    ├── 01_clean_baseline/
    │   ├── ground_truth/
    │   │   └── ground_truth.json
    │   ├── input/
    │   │   ├── dataset_manifest.json
    │   │   ├── metadata.json
    │   │   └── images/
    │   │       ├── clean_veh_00.png ...
    │   │       └── clean_ped_00.png ...
    │   └── scenario_01_clean_baseline.zip
    ├── ...
    └── 09_mixed_scenario/
        ├── ground_truth/
        │   └── ground_truth.json
        ├── input/
        │   ├── dataset_manifest.json
        │   ├── metadata.json
        │   └── images/
        └── scenario_09_mixed_scenario.zip
```

---

## CLI Usage

### Generate Corpus

```bash
# Generate corpus with default output directory (data/corpus) and master seed 42
python -m backend.tools.corpus_generator --output data/corpus --seed 42

# Generate and immediately run in-memory detector validation loop
python -m backend.tools.corpus_generator --output data/corpus --validate
```

### Run Test Suite

```bash
# Run all corpus scenario tests (Tests A through O)
pytest tests/corpus/ -v
```
