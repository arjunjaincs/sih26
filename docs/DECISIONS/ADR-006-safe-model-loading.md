# ADR-006: Safe Model Loading Policy

**Status**: Accepted  
**Date**: 2026-09-10  
**Context**: PyTorch's default `torch.load()` uses Python pickle, which allows arbitrary code execution. PRAMAAN must load untrusted model files.

## Decision

All model loading goes through a single controlled module
(`backend/infra/model_loader.py`). This module enforces:

1. **PyTorch**: `torch.load(path, weights_only=True)` only
2. **ONNX**: `onnxruntime.InferenceSession` (no pickle)
3. **TorchScript**: `torch.jit.load()` (restricted execution model)
4. **All others**: Rejected with clear error

## Rationale

- `torch.load()` with default settings deserializes arbitrary Python objects
  via pickle, enabling remote code execution from a crafted `.pt` file
- `weights_only=True` restricts loading to tensor data only
- ONNX format is a protobuf-based graph format, no arbitrary code execution
- TorchScript has a restricted execution environment but can still access
  filesystem; use with caution

## Enforcement

- Single entry point: `load_model(path, framework)` — no other module calls
  `torch.load` directly
- Lint rule: flag any `torch.load` call that doesn't use `weights_only=True`
- Security test: attempt to load a model file with a malicious `__reduce__` → must fail
- Import check test: verify only `model_loader.py` imports `torch.load`

## Consequences

- Some older PyTorch models saved with custom objects won't load
  (they must be re-saved with `torch.save(state_dict, ...)`)
- This is a deliberate trade-off: security over compatibility
- TorchScript models are accepted but documented as higher-risk

## Rejected Alternatives

- Allow `weights_only=False` with an "I trust this model" flag (too easy to misuse)
- Sandbox via subprocess (complex, platform-dependent)
- Don't load PyTorch models at all (too restrictive)
