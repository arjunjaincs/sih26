# ADR-001: Modular Monolith over Microservices

**Status**: Accepted  
**Date**: 2026-09-10  
**Context**: PRAMAAN must run on a single developer laptop, fully offline.

## Decision

PRAMAAN is a modular monolith: single Python process, single SQLite database,
logically separated modules with clean interfaces.

## Rationale

- **Offline/air-gapped**: No service discovery, no message queues, no orchestration
- **Single machine**: No benefit from distributed architecture
- **Simplicity**: One process to start, debug, and deploy
- **Performance**: No serialization overhead between services
- **Prototype**: Research prototype; complexity budget should go to detection quality

## Consequences

- All modules share a process; a crash in one affects all
- Scaling to multiple machines would require refactoring (acceptable for research prototype)
- Module boundaries must be enforced by convention and testing (import checks)

## Rejected Alternatives

- Microservices (unnecessary for single-machine, adds operational complexity)
- Serverless (incompatible with offline requirement)
