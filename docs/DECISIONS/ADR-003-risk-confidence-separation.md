# ADR-003: Risk and Confidence as Separate Concepts

**Status**: Accepted  
**Date**: 2026-09-10  
**Context**: SIH problem statement requires trustworthy risk assessment. Collapsing risk and confidence into a single "trust score" is misleading and technically indefensible.

## Decision

Risk and confidence are represented as separate, independently computed values
throughout PRAMAAN. There is no single "trust score" or "safety percentage".

## Rationale

- **Semantic clarity**: "High risk, low confidence" means something fundamentally
  different from "low risk, high confidence" — a single number cannot represent both
- **Honest reporting**: A system that hasn't run enough tests should NOT report "safe"
- **Analyst utility**: Analysts need to distinguish "we found a problem" from
  "we didn't look hard enough"
- **Defensibility**: In SIH evaluation, a nuanced risk model withstands scrutiny
  better than a magic number

## Model

| Concept | Type | Meaning |
|---------|------|---------|
| Risk Level | Enum (NONE/LOW/MEDIUM/HIGH/CRITICAL) | Estimated threat given observed evidence |
| Confidence Level | Enum (LOW/MODERATE/HIGH) | Trust in the risk estimate |
| Coverage | Float (0.0–1.0) | Fraction of applicable methods that actually ran |
| Severity | Enum (INFO/LOW/MEDIUM/HIGH/CRITICAL) | Potential impact if the risk materializes |

## Rules

1. LOW risk + LOW confidence = **INCONCLUSIVE**, not "safe"
2. NONE risk + HIGH confidence = The system found no evidence of threat after thorough testing
3. HIGH risk + LOW confidence = **INVESTIGATE** — suspicious but more evidence needed
4. Coverage < 1.0 always reduces confidence
5. Absent detectors produce CoverageGap entries, never implicit "pass"

## Consequences

- UI must display risk and confidence separately (more complex UI)
- Reports must explain both dimensions
- No single-number ranking of assets (analysts must interpret)
- More honest, but more complex to communicate

## Rejected Alternatives

- Single "trust score" (misleading, indefensible)
- Bayesian posterior probability (requires well-calibrated priors we don't have)
- Simple weighted average (hides meaning)
