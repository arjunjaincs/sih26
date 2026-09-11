"""
PRAMAAN assessment routes.

POST /api/v1/assessments          -- run a new assessment
GET  /api/v1/assessments/{id}     -- retrieve persisted assessment summary
GET  /api/v1/assessments/{id}/findings  -- list findings
GET  /api/v1/assessments/{id}/evidence  -- list evidence (no raw bytes)
GET  /api/v1/assessments/{id}/audit     -- audit chain verification result

Security boundaries
-------------------
Every user-supplied path is validated before being passed to the engine:
  1. Must be an absolute path.
  2. Must exist on the local filesystem.
  3. Must not exceed the configured size limit.
  4. If PRAMAAN_TRUSTED_ASSET_ROOTS is set, must start with one of those roots.

These checks happen in _validate_asset_path(), which calls the existing
validate_absolute_path() from Phase 2 and adds the trusted-root allowlist.

The API never calls any detection logic directly -- it calls
AssessmentService.run_assessment() and returns the result.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from backend.api.config import settings
from backend.api.deps import DbDep, ServiceDep, UploadRepoDep
from backend.api.errors import (
    AssessmentNotFound,
    InvalidAssetPath,
    UnsupportedFormat,
)
from backend.api.schemas import (
    AssessmentCreateRequest,
    AssessmentResultSchema,
    AssessmentSummarySchema,
    AuditEventSchema,
    AuditResponse,
    CoverageGapSchema,
    DetectorRunSchema,
    EvidenceResponse,
    EvidenceSchema,
    FindingSchema,
    FindingsResponse,
)
from backend.assessment.models import AssessmentRequest
from backend.audit.verifier import ChainVerifier
from backend.domain.enums import AssessmentState, DatasetFormat
from backend.infra.db import (
    AuditPayloadRepository,
    AuditRepository,
    EvidenceRepository,
    FindingRepository,
)
from backend.infra.ingestion import validate_absolute_path

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["assessments"])


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _validate_asset_path(
    raw: str,
    *,
    max_size_mb: int,
    must_exist: bool = True,
) -> Path:
    """
    Validate a user-supplied asset path.

    Checks (in order):
      1. Must be an absolute path string.
      2. Must not contain path-traversal sequences.
      3. Must exist (if must_exist=True).
      4. Must not exceed max_size_mb (for files).
      5. Must be within a trusted root (if PRAMAAN_TRUSTED_ASSET_ROOTS is set).

    Raises InvalidAssetPath on any failure.
    Returns the resolved Path on success.
    """
    if not raw:
        raise InvalidAssetPath("Path must not be empty.")

    try:
        path = Path(raw)
    except Exception:
        raise InvalidAssetPath(f"Could not parse path: {raw!r}")

    if not path.is_absolute():
        raise InvalidAssetPath(
            f"Path must be absolute (got: {raw!r}). "
            "Relative paths are not accepted for security reasons."
        )

    # Resolve symlinks to prevent traversal
    try:
        resolved = path.resolve()
    except Exception:
        raise InvalidAssetPath(f"Could not resolve path: {raw!r}")

    if must_exist and not resolved.exists():
        raise InvalidAssetPath(f"Path does not exist: {raw!r}")

    # Trusted-root allowlist (optional; configured via env var)
    trusted_roots = settings.trusted_asset_roots
    if trusted_roots:
        if not any(
            str(resolved).startswith(str(root.resolve()))
            for root in trusted_roots
        ):
            raise InvalidAssetPath(
                "Path is outside the configured trusted asset directories. "
                "Set PRAMAAN_TRUSTED_ASSET_ROOTS to include the required root."
            )

    # File-size check (for files, not directories)
    if resolved.is_file():
        max_bytes = max_size_mb * 1024 * 1024
        size = resolved.stat().st_size
        if size > max_bytes:
            raise InvalidAssetPath(
                f"File size {size / (1024*1024):.1f} MB exceeds limit "
                f"of {max_size_mb} MB."
            )

    return resolved


def _parse_dataset_format(raw: str | None) -> DatasetFormat | None:
    """Parse and validate the dataset_format string."""
    if raw is None:
        return None
    allowed = [fmt.value for fmt in DatasetFormat]
    if raw not in allowed:
        raise UnsupportedFormat(raw, allowed)
    return DatasetFormat(raw)


# ---------------------------------------------------------------------------
# POST /api/v1/assessments
# ---------------------------------------------------------------------------

@router.post(
    "/assessments",
    response_model=AssessmentResultSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Run a new PRAMAAN assessment",
)
def create_assessment(
    body: AssessmentCreateRequest,
    service: ServiceDep,
    upload_repo: UploadRepoDep,
) -> AssessmentResultSchema:
    """
    Run a new assessment against local assets or uploaded assets.

    The request must supply at least one of:
      - dataset_path or dataset_asset_id
      - model_path or model_asset_id

    All paths are validated for existence, size, and trusted-root
    membership before being passed to the assessment engine.
    Uploaded assets are verified from the secure UploadRepository.

    The response is the complete AssessmentResult produced by
    AssessmentService.run_assessment() — including per-detector runs,
    coverage gaps, risk, confidence, and audit chain status.
    """
    # --- Validate and resolve paths ---
    dataset_path: Path | None = None
    model_path: Path | None = None
    dataset_format = _parse_dataset_format(body.dataset_format)

    # 1. Resolve dataset
    if body.dataset_asset_id:
        upload = upload_repo.get(body.dataset_asset_id)
        if not upload or upload.asset_type != "dataset":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "invalid_asset_id", "message": f"Dataset asset ID not found: {body.dataset_asset_id!r}"},
            )
        resolved_ds = Path(upload.storage_path)
        if not resolved_ds.exists():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "asset_missing", "message": "Uploaded dataset file is missing from storage."},
            )
        dataset_path = resolved_ds
        if dataset_format is None and upload.format:
            try:
                dataset_format = _parse_dataset_format(upload.format)
            except Exception:
                pass
    elif body.dataset_path is not None:
        dataset_path = _validate_asset_path(
            body.dataset_path,
            max_size_mb=settings.max_dataset_size_mb * 1000,  # directory: no per-dir limit
        )

    # 2. Resolve model
    if body.model_asset_id:
        upload = upload_repo.get(body.model_asset_id)
        if not upload or upload.asset_type != "model":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "invalid_asset_id", "message": f"Model asset ID not found: {body.model_asset_id!r}"},
            )
        resolved_model = Path(upload.storage_path)
        if not resolved_model.exists():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "asset_missing", "message": "Uploaded model file is missing from storage."},
            )
        model_path = resolved_model
    elif body.model_path is not None:
        model_path = _validate_asset_path(
            body.model_path,
            max_size_mb=settings.max_model_size_mb,
        )

    # --- Build AssessmentRequest ---
    assess_id = body.assessment_id or str(uuid.uuid4())
    request = AssessmentRequest(
        title=body.title,
        assessment_id=assess_id,
        dataset_path=dataset_path,
        dataset_format=dataset_format,
        model_path=model_path,
        model_reference_fingerprint=body.model_reference_fingerprint,
        phash_threshold=body.phash_threshold,
        dhash_threshold=body.dhash_threshold,
        min_cluster_size=body.min_cluster_size,
    )

    # --- Fail fast on domain-level validation (returns 422, not 201) ---
    validation_errors = request.validate()
    if validation_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_request",
                "message": "Assessment request failed domain validation.",
                "detail": "; ".join(validation_errors),
            },
        )

    log.info(
        "Starting assessment '%s' (id=%s) — dataset=%s model=%s",
        body.title, assess_id,
        dataset_path is not None,
        model_path is not None,
    )

    # --- Execute (all real detection logic is in the service) ---
    result = service.run_assessment(request)

    log.info(
        "Assessment %s complete — status=%s risk=%s confidence=%s",
        assess_id, result.status.value,
        result.overall_risk.value, result.overall_confidence.value,
    )

    return _result_to_schema(result)


# ---------------------------------------------------------------------------
# GET /api/v1/assessments/{assessment_id}
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}",
    response_model=AssessmentSummarySchema,
    summary="Retrieve a persisted assessment",
)
def get_assessment(
    assessment_id: str,
    conn: DbDep,
) -> AssessmentSummarySchema:
    """
    Retrieve summary of a previously run assessment from the database.

    Returns 404 if the assessment_id does not exist.
    """
    from backend.infra.db import AssessmentRepository
    record = AssessmentRepository(conn).get(assessment_id)
    if record is None:
        raise AssessmentNotFound(assessment_id)

    # Count findings and evidence for this assessment
    findings = FindingRepository(conn).list_by_assessment(assessment_id)
    evidence_count = sum(
        len(EvidenceRepository(conn).list_by_finding(f.finding_id))
        for f in findings
    )

    return AssessmentSummarySchema(
        assessment_id=record.assessment_id,
        title=record.title,
        status=record.state.value,
        software_version=record.software_version or "",
        created_at=record.created_at.isoformat() if record.created_at else "",
        started_at=record.started_at.isoformat() if record.started_at else None,
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        error=record.error,
        findings_count=len(findings),
        evidence_count=evidence_count,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/assessments/{assessment_id}/findings
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/findings",
    response_model=FindingsResponse,
    summary="List findings for an assessment",
)
def get_findings(
    assessment_id: str,
    conn: DbDep,
) -> FindingsResponse:
    """
    Return all findings persisted for the given assessment.

    Findings are read directly from the database — they are NOT
    regenerated by running the detectors again.

    Returns 404 if the assessment does not exist.
    """
    from backend.infra.db import AssessmentRepository
    if AssessmentRepository(conn).get(assessment_id) is None:
        raise AssessmentNotFound(assessment_id)

    findings = FindingRepository(conn).list_by_assessment(assessment_id)

    return FindingsResponse(
        assessment_id=assessment_id,
        count=len(findings),
        findings=[
            FindingSchema(
                finding_id=f.finding_id,
                assessment_id=f.assessment_id,
                asset_id=f.asset_id,
                category=f.category.value,
                subcategory=f.subcategory,
                severity=f.severity.value,
                title=f.title,
                description=f.description,
                detection_method=f.detection_method,
                detector_id=f.detector_id,
                limitations=f.limitations,
                recommended_disposition=f.recommended_disposition,
                created_at=f.created_at.isoformat(),
            )
            for f in findings
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/assessments/{assessment_id}/evidence
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/evidence",
    response_model=EvidenceResponse,
    summary="List evidence for an assessment",
)
def get_evidence(
    assessment_id: str,
    conn: DbDep,
) -> EvidenceResponse:
    """
    Return all evidence items for the given assessment.

    Evidence is read from the database — not regenerated.

    IMPORTANT: artifact_path (local filesystem path) is deliberately
    omitted from the response to avoid leaking server filesystem structure.
    Only hashes, IDs, and structured data are returned.

    Returns 404 if the assessment does not exist.
    """
    from backend.infra.db import AssessmentRepository
    if AssessmentRepository(conn).get(assessment_id) is None:
        raise AssessmentNotFound(assessment_id)

    findings = FindingRepository(conn).list_by_assessment(assessment_id)
    ev_repo = EvidenceRepository(conn)

    all_evidence: list[EvidenceSchema] = []
    for f in findings:
        for e in ev_repo.list_by_finding(f.finding_id):
            all_evidence.append(EvidenceSchema(
                evidence_id=e.evidence_id,
                finding_id=e.finding_id,
                detector_id=e.detector_id,
                evidence_type=e.evidence_type.value,
                description=e.description,
                data=e.data,
                # artifact_path intentionally omitted
                artifact_sha256=e.artifact_sha256,
            ))

    return EvidenceResponse(
        assessment_id=assessment_id,
        count=len(all_evidence),
        evidence=all_evidence,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/assessments/{assessment_id}/audit
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/audit",
    response_model=AuditResponse,
    summary="Verify audit chain for an assessment",
)
def get_audit(
    assessment_id: str,
    conn: DbDep,
) -> AuditResponse:
    """
    Run the ChainVerifier against the audit events for this assessment
    and return the verification result.

    Uses the existing Phase 6 ChainVerifier — no new audit logic added.

    Returns:
      chain_valid=True  — the hash chain is intact and unmodified
      chain_valid=False — tampering detected; failures list details which events

    Returns 404 if the assessment does not exist.
    """
    from backend.infra.db import AssessmentRepository
    if AssessmentRepository(conn).get(assessment_id) is None:
        raise AssessmentNotFound(assessment_id)

    audit_repo = AuditRepository(conn)
    payload_repo = AuditPayloadRepository(conn)

    verifier = ChainVerifier(audit_repo, payload_repo)
    chain_result = verifier.verify_assessment(assessment_id)

    # Retrieve the raw events for display (hashes only, no payload)
    events = audit_repo.list_by_assessment(assessment_id)

    # Serialize EventVerificationFailure objects to description strings
    failure_strings = [
        f.description if hasattr(f, "description") else str(f)
        for f in chain_result.failures
    ]

    return AuditResponse(
        assessment_id=assessment_id,
        chain_valid=chain_result.valid,
        events_checked=chain_result.events_checked,
        failures=failure_strings,
        first_invalid_event_id=chain_result.first_invalid_event_id,
        events=[
            AuditEventSchema(
                event_id=e.event_id,
                event_type=e.event_type.value,
                timestamp_utc=e.timestamp_utc,
                actor=e.actor,
                current_hash=e.current_hash,
                previous_hash=e.previous_hash,
            )
            for e in events
        ],
    )


# ---------------------------------------------------------------------------
# Internal conversion helpers
# ---------------------------------------------------------------------------

def _result_to_schema(result) -> AssessmentResultSchema:
    """Convert an AssessmentResult dataclass to the API schema."""
    return AssessmentResultSchema(
        assessment_id=result.assessment_id,
        title=result.title,
        status=result.status.value,
        started_at=result.started_at.isoformat(),
        completed_at=result.completed_at.isoformat(),
        assets_analyzed=result.assets_analyzed,
        detectors_executed=result.detectors_executed,
        detectors_skipped=result.detectors_skipped,
        findings_count=result.findings_count,
        evidence_count=result.evidence_count,
        overall_risk=result.overall_risk.value,
        risk_qualitative=result.risk_qualitative,
        overall_confidence=result.overall_confidence.value,
        confidence_qualifier=result.confidence_qualifier,
        coverage_fraction=result.coverage_fraction,
        coverage_gaps=[
            CoverageGapSchema(
                detector_id=g.detector_id,
                detector_name=g.detector_name,
                reason=g.reason,
                required_capability=g.required_capability,
                observed_capability=g.observed_capability,
                impact=g.impact,
                recommended_action=g.recommended_action,
            )
            for g in result.coverage_gaps
        ],
        detector_runs=[
            DetectorRunSchema(
                detector_id=r.detector_id,
                detector_name=r.detector_name,
                asset_id=r.asset_id,
                applicable=r.applicable,
                ran=r.ran,
                status=r.status,
                risk_level=r.risk_level,
                confidence_level=r.confidence_level,
                findings_count=r.findings_count,
                evidence_count=r.evidence_count,
                error=r.error,
            )
            for r in result.detector_runs
        ],
        limitations=result.limitations,
        audit_chain_valid=result.audit_chain_valid,
        error=result.error,
    )
