# ADR-007: Demo/Live Strict Separation

**Status**: Accepted  
**Date**: 2026-09-10  
**Context**: The v1 codebase was entirely fixture-driven with hardcoded findings. PRAMAAN v2 must never conflate demonstration data with real analysis.

## Decision

Demo and live analysis are strictly separated at the module level, the data
level, and the UI level.

## Module Separation

```
backend/
├── engines/       # LIVE only — imports detectors, runs real analysis
├── detectors/     # LIVE only — real detection algorithms
└── demo/          # DEMO only — deterministic fixtures, scenario runner
```

- `demo/` never imports from `engines/` or `detectors/`
- `engines/` and `detectors/` never import from `demo/`
- This is enforced by automated import-graph tests

## Data Separation

| Field | Live | Demo |
|-------|------|------|
| `assessment_type` | `LIVE` | `DEMO` |
| `finding.source` | `LIVE_ANALYSIS` | `DEMO_FIXTURE` |

## UI Separation

- Demo assessments display a prominent, non-dismissable `DEMO MODE` banner
- Demo findings have a visual badge indicating fixture origin
- No UI element merges demo and live data into the same view without clear labeling

## Rationale

- v1 shipped entirely hardcoded findings that looked like real analysis
- This is the #1 credibility risk for SIH evaluation
- Evaluators who inspect the code must see clear separation
- A demo that pretends to be real analysis is worse than no demo

## Consequences

- Demo scenarios require separate fixture generation effort
- Demo cannot dynamically evolve with live analysis improvements (acceptable)
- More code to maintain (acceptable for credibility)
