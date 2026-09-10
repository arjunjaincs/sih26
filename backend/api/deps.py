"""
PRAMAAN API FastAPI dependencies.

Uses FastAPI's Depends() pattern to provide:
  - Database connections (one per request, closed after)
  - AssessmentService instances (constructed from the DB connection)

No singleton connection — SQLite WAL mode handles concurrent reads fine.
Each request gets its own connection from the same DB file.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends

from backend.api.config import settings
from backend.assessment.orchestrator import AssessmentService
from backend.infra.db import open_db


# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Yield an open database connection for the duration of one request.

    The connection is always closed in the finally block — even if the
    route raises an exception.
    """
    conn = open_db(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


DbDep = Annotated[sqlite3.Connection, Depends(get_db)]


# ---------------------------------------------------------------------------
# Service dependency
# ---------------------------------------------------------------------------

def get_service(conn: DbDep) -> AssessmentService:
    """Build an AssessmentService from the request's DB connection."""
    return AssessmentService(conn)


ServiceDep = Annotated[AssessmentService, Depends(get_service)]
