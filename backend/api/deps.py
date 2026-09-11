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
from backend.infra.blob_store import BlobStore
from backend.infra.db import UploadRepository, open_db


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


# ---------------------------------------------------------------------------
# BlobStore dependency
# ---------------------------------------------------------------------------

def get_blob_store() -> BlobStore:
    """Provide a BlobStore configured to the active blob directory."""
    return BlobStore(settings.blob_dir)


BlobStoreDep = Annotated[BlobStore, Depends(get_blob_store)]


# ---------------------------------------------------------------------------
# Upload repository dependency
# ---------------------------------------------------------------------------

def get_upload_repo(conn: DbDep) -> UploadRepository:
    """Provide an UploadRepository instance using the request's DB connection."""
    return UploadRepository(conn)


UploadRepoDep = Annotated[UploadRepository, Depends(get_upload_repo)]

