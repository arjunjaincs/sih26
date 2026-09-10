# ADR-004: Detector Protocol over Plugin Framework

**Status**: Accepted  
**Date**: 2026-09-10  
**Context**: PRAMAAN needs extensible detection capabilities. Individual detectors should be addable without modifying orchestration code.

## Decision

Detectors implement a Python `Protocol` (structural subtyping). Discovery
is via a simple registry module that imports and registers detector classes.
No dynamic plugin loading, no entry points, no plugin framework.

## Rationale

- **Simplicity**: A Protocol is 10 lines of code; a plugin framework is thousands
- **Type safety**: Protocol compliance is checked by mypy at static analysis time
- **Debuggability**: Standard Python imports; stack traces are clear
- **Sufficient**: For a research prototype with ~15 detectors, explicit registration is fine
- **No security risk**: No dynamic code loading from arbitrary paths

## Protocol

```python
class Detector(Protocol):
    @property
    def metadata(self) -> DetectorMetadata: ...
    def can_run(self, context: DetectorContext) -> CanRunResult: ...
    def run(self, context: DetectorContext) -> DetectorResult: ...
```

## Registry

```python
# detectors/registry.py
from detectors.data.phash_duplicates import PHashDuplicateDetector
from detectors.model.artifact_fingerprint import ArtifactFingerprintDetector
# ... explicit imports ...

ALL_DETECTORS: list[Detector] = [
    PHashDuplicateDetector(),
    ArtifactFingerprintDetector(),
    # ...
]
```

## Consequences

- Adding a new detector requires: (1) create class, (2) add import to registry
- No hot-loading of detectors at runtime (acceptable)
- No third-party detector plugins (acceptable for research prototype)
- Easy to upgrade to entry_points or plugin framework later if needed

## Rejected Alternatives

- `importlib` / `pkg_resources` entry points (overkill, adds complexity)
- Abstract base class (Protocol is more Pythonic, less coupling)
- Decorator-based auto-registration (implicit, harder to debug)
