# ADR-002: SQLite for All Structured Persistence

**Status**: Accepted  
**Date**: 2026-09-10  
**Context**: PRAMAAN needs a database that works offline, requires zero configuration, and fits on a laptop.

## Decision

Use SQLite with WAL mode for all structured data. Use a content-addressed
filesystem blob store for large binary artifacts.

## Rationale

- **Zero configuration**: No database server to install, configure, or manage
- **Single file**: Trivially backed up, moved, inspected
- **Air-gapped**: No network dependency
- **WAL mode**: Concurrent reads don't block writes; adequate for single-user
- **Proven**: SQLite handles datasets up to ~100 GB; PRAMAAN datasets are far smaller
- **Blob store separation**: Keeps SQLite file small and fast; binary artifacts stored by hash

## Consequences

- No multi-user concurrent write access (acceptable for single-user prototype)
- No full-text search without FTS5 extension (can enable if needed)
- Large BLOBs stored in filesystem, not database
- No automatic replication

## Rejected Alternatives

- PostgreSQL (requires server, unnecessary for single-machine)
- MongoDB (requires server, schemaless is wrong for this domain)
- Pure filesystem (loses relational query capability)
- DuckDB (analytical focus, less mature for OLTP patterns)
