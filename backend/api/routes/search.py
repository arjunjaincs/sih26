"""
PRAMAAN Global Search endpoint.

GET /api/v1/search?q={query}&limit={limit}

Provides lightweight, responsive search across persisted:
- Assessments (ID, title, description, software version, asset names)
- Findings (ID, title, detector ID, category, severity, asset names)
- Evidence (ID, detector ID, evidence type, description, finding title)

Enforces:
- Zero data mutation (read-only SQLite queries)
- Path censorship (never exposes absolute filesystem paths)
- SQL injection immunity via parameterized LIKE queries with custom ESCAPE
- Result categorization and clamped limits
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from backend.api.deps import DbDep
from backend.api.schemas import (
    GlobalSearchResponse,
    SearchCategoryCounts,
    SearchResultAssessment,
    SearchResultEvidence,
    SearchResultFinding,
)
from backend.reporting.formatting import censor_paths

router = APIRouter(prefix="/api/v1", tags=["search"])

_DETECTOR_CODE_MAP: dict[str, str] = {
    "data.integrity.di01_duplicates": "DI-01",
    "data.integrity.di02_label_integrity": "DI-02",
    "data.integrity.di03_split_leakage": "DI-03",
    "data.integrity.di04_corruption": "DI-04",
    "data.integrity.di05_demographic_balance": "DI-05",
    "model.integrity.mi01_fingerprint": "MI-01",
    "model.integrity.mi02_weight_anomalies": "MI-02",
    "model.integrity.mi03_layer_inspection": "MI-03",
    "model.integrity.mi04_attribution": "MI-04",
    "model.integrity.mi05_spectral": "MI-05",
    "provenance.pi01_verification": "PI-01",
}

# Reverse lookup dictionary for codes (e.g. "DI-01", "di01" -> "data.integrity.di01_duplicates")
_DETECTOR_REVERSE_MAP: dict[str, str] = {}
for _det_id, _code in _DETECTOR_CODE_MAP.items():
    _DETECTOR_REVERSE_MAP[_code.lower()] = _det_id
    _DETECTOR_REVERSE_MAP[_code.lower().replace("-", "")] = _det_id


def _escape_like(query: str) -> str:
    """Escape special LIKE pattern wildcards to prevent pattern injection."""
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _sanitize_name(name: str | None) -> str | None:
    if not name:
        return None
    # Strip any directory path components first to avoid leaking server structure
    safe_basename = Path(name).name or name
    return censor_paths(safe_basename)


@router.get(
    "/search",
    response_model=GlobalSearchResponse,
    summary="Lightweight global search across assessments, findings, and evidence",
)
def global_search(
    q: str = Query(default="", description="Search query string"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results per category"),
    conn: DbDep = None,
) -> GlobalSearchResponse:
    """
    Search across assessments, findings, and evidence in SQLite using parameterized queries.
    Returns categorized results with absolute server paths censored.
    """
    effective_limit = min(max(1, limit), 30)
    cleaned_query = q.strip()
    if not cleaned_query:
        return GlobalSearchResponse(
            query="",
            total_matches=0,
            counts=SearchCategoryCounts(),
            assessments=[],
            findings=[],
            evidence=[],
        )

    # Sanitize query length and control characters
    sanitized_q = cleaned_query[:200].replace("\x00", "")
    escaped = _escape_like(sanitized_q)
    like_term = f"%{escaped}%"

    # Detector code variant (e.g. "DI-01" -> "di01", or "di01" -> matching detector ID)
    q_lower = sanitized_q.lower()
    alt_q = q_lower.replace("-", "").replace(" ", "")
    alt_term = f"%{_escape_like(alt_q)}%"

    # Look up direct detector ID match if user typed code like "DI-01" or "mi05"
    mapped_det_id = _DETECTOR_REVERSE_MAP.get(q_lower) or _DETECTOR_REVERSE_MAP.get(alt_q)
    mapped_det_term = f"%{_escape_like(mapped_det_id)}%" if mapped_det_id else like_term

    # 1. Assessments
    assessment_sql = """
        SELECT DISTINCT
            a.assessment_id,
            a.title,
            a.state,
            a.created_at
        FROM assessments a
        LEFT JOIN assets ast ON ast.assessment_id = a.assessment_id
        WHERE a.assessment_id LIKE ? ESCAPE '\\'
           OR a.title LIKE ? ESCAPE '\\'
           OR (a.description IS NOT NULL AND a.description LIKE ? ESCAPE '\\')
           OR ast.name LIKE ? ESCAPE '\\'
           OR ast.asset_id LIKE ? ESCAPE '\\'
        ORDER BY a.created_at DESC
        LIMIT ?
    """
    asm_rows = conn.execute(
        assessment_sql,
        (like_term, like_term, like_term, like_term, like_term, effective_limit),
    ).fetchall()

    assessments: list[SearchResultAssessment] = [
        SearchResultAssessment(
            assessment_id=row["assessment_id"],
            title=censor_paths(row["title"]),
            state=row["state"],
            created_at=row["created_at"],
            target_url=f"/assessments/{row['assessment_id']}/result",
        )
        for row in asm_rows
    ]

    # 2. Findings
    findings_sql = """
        SELECT
            f.finding_id,
            f.assessment_id,
            f.title,
            f.detector_id,
            f.category,
            f.severity,
            ast.name AS asset_name
        FROM findings f
        LEFT JOIN assets ast ON ast.asset_id = f.asset_id
        WHERE f.finding_id LIKE ? ESCAPE '\\'
           OR f.title LIKE ? ESCAPE '\\'
           OR f.detector_id LIKE ? ESCAPE '\\'
           OR f.detector_id LIKE ? ESCAPE '\\'
           OR f.detector_id LIKE ? ESCAPE '\\'
           OR f.category LIKE ? ESCAPE '\\'
           OR (ast.name IS NOT NULL AND ast.name LIKE ? ESCAPE '\\')
        ORDER BY f.created_at DESC
        LIMIT ?
    """
    finding_rows = conn.execute(
        findings_sql,
        (like_term, like_term, like_term, alt_term, mapped_det_term, like_term, like_term, effective_limit),
    ).fetchall()

    findings: list[SearchResultFinding] = [
        SearchResultFinding(
            finding_id=row["finding_id"],
            assessment_id=row["assessment_id"],
            title=censor_paths(row["title"]),
            detector_id=row["detector_id"],
            detector_code=_DETECTOR_CODE_MAP.get(row["detector_id"]),
            severity=row["severity"],
            category=row["category"],
            asset_name=_sanitize_name(row["asset_name"]),
            target_url=f"/assessments/{row['assessment_id']}/findings",
        )
        for row in finding_rows
    ]

    # 3. Evidence
    evidence_sql = """
        SELECT
            e.evidence_id,
            e.finding_id,
            e.detector_id,
            e.evidence_type,
            e.description,
            f.assessment_id,
            f.title AS finding_title
        FROM evidence e
        JOIN findings f ON f.finding_id = e.finding_id
        WHERE e.evidence_id LIKE ? ESCAPE '\\'
           OR e.detector_id LIKE ? ESCAPE '\\'
           OR e.detector_id LIKE ? ESCAPE '\\'
           OR e.detector_id LIKE ? ESCAPE '\\'
           OR e.evidence_type LIKE ? ESCAPE '\\'
           OR e.description LIKE ? ESCAPE '\\'
           OR f.title LIKE ? ESCAPE '\\'
        ORDER BY e.rowid DESC
        LIMIT ?
    """
    evidence_rows = conn.execute(
        evidence_sql,
        (like_term, like_term, alt_term, mapped_det_term, like_term, like_term, like_term, effective_limit),
    ).fetchall()

    evidence: list[SearchResultEvidence] = [
        SearchResultEvidence(
            evidence_id=row["evidence_id"],
            finding_id=row["finding_id"],
            assessment_id=row["assessment_id"],
            detector_id=row["detector_id"],
            detector_code=_DETECTOR_CODE_MAP.get(row["detector_id"]),
            evidence_type=row["evidence_type"],
            description=censor_paths(row["description"]),
            finding_title=censor_paths(row["finding_title"]) if row["finding_title"] else None,
            target_url=f"/assessments/{row['assessment_id']}/evidence",
        )
        for row in evidence_rows
    ]

    total_matches = len(assessments) + len(findings) + len(evidence)

    return GlobalSearchResponse(
        query=sanitized_q,
        total_matches=total_matches,
        counts=SearchCategoryCounts(
            assessments=len(assessments),
            findings=len(findings),
            evidence=len(evidence),
        ),
        assessments=assessments,
        findings=findings,
        evidence=evidence,
    )
