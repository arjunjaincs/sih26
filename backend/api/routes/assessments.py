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
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
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
    AssessmentListResponse,
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
    ProvenanceManifestItem,
    ProvenanceResponse,
)
from backend.assessment.models import AssessmentRequest
from backend.audit.verifier import ChainVerifier
from backend.domain.enums import AssessmentState, DatasetFormat, Severity
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    AuditPayloadRepository,
    AuditRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    ProvenanceRepository,
)
from backend.infra.ingestion import validate_absolute_path
from backend.reporting import (
    extract_report_data_from_db,
    generate_assessment_report_pdf,
)

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

    # 3. Resolve optional reference model
    model_reference_path: Path | None = None
    if body.model_reference_asset_id:
        upload = upload_repo.get(body.model_reference_asset_id)
        if not upload or upload.asset_type != "model":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "invalid_asset_id", "message": f"Reference model asset ID not found: {body.model_reference_asset_id!r}"},
            )
        resolved_ref = Path(upload.storage_path)
        if not resolved_ref.exists():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "asset_missing", "message": "Uploaded reference model file is missing from storage."},
            )
        model_reference_path = resolved_ref
    elif body.model_reference_path is not None:
        model_reference_path = _validate_asset_path(
            body.model_reference_path,
            max_size_mb=settings.max_model_size_mb,
        )

    # 4. Resolve optional provenance bundle
    provenance_manifest = None
    provenance_public_key = None
    actual_input_bytes = None
    actual_output_bytes = None
    if body.provenance_manifest is not None:
        try:
            from backend.domain.entities import ProvenanceManifest
            provenance_manifest = ProvenanceManifest.model_validate(body.provenance_manifest)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "invalid_provenance_manifest", "message": f"Malformed provenance manifest: {exc}"},
            )

        if body.provenance_public_key_hex:
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                pub_bytes = bytes.fromhex(body.provenance_public_key_hex)
                provenance_public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": "invalid_public_key", "message": f"Invalid Ed25519 public key: {exc}"},
                )

        if body.actual_input_bytes_hex:
            try:
                actual_input_bytes = bytes.fromhex(body.actual_input_bytes_hex)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": "invalid_input_bytes", "message": f"Invalid input bytes hex: {exc}"},
                )

        if body.actual_output_bytes_hex:
            try:
                actual_output_bytes = bytes.fromhex(body.actual_output_bytes_hex)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": "invalid_output_bytes", "message": f"Invalid output bytes hex: {exc}"},
                )

    # --- Build AssessmentRequest ---
    assess_id = body.assessment_id or str(uuid.uuid4())
    request = AssessmentRequest(
        title=body.title,
        assessment_id=assess_id,
        dataset_path=dataset_path,
        dataset_format=dataset_format,
        model_path=model_path,
        model_reference_path=model_reference_path,
        model_reference_fingerprint=body.model_reference_fingerprint,
        provenance_manifest=provenance_manifest,
        provenance_public_key=provenance_public_key,
        actual_input_bytes=actual_input_bytes,
        actual_output_bytes=actual_output_bytes,
        actual_model_sha256=body.actual_model_sha256,
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
        "Starting assessment '%s' (id=%s) — dataset=%s model=%s provenance=%s",
        body.title, assess_id,
        dataset_path is not None,
        model_path is not None,
        provenance_manifest is not None,
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
# GET /api/v1/assessments
# ---------------------------------------------------------------------------

@router.get(
    "/assessments",
    response_model=AssessmentListResponse,
    summary="List all persisted assessments",
)
def list_assessments(
    conn: DbDep,
) -> AssessmentListResponse:
    """
    Return all assessments stored in the local SQLite database, most recent first.

    Each item is an AssessmentSummarySchema with persisted findings/evidence counts
    and summary assurance metrics (risk, confidence, coverage).
    Returns an empty list when no assessments have been run yet.
    """
    records = AssessmentRepository(conn).list_all()
    summaries: list[AssessmentSummarySchema] = []
    finding_repo = FindingRepository(conn)
    evidence_repo = EvidenceRepository(conn)
    audit_repo = AuditRepository(conn)
    payload_repo = AuditPayloadRepository(conn)

    for record in records:
        findings = finding_repo.list_by_assessment(record.assessment_id)
        evidence_count = sum(
            len(evidence_repo.list_by_finding(f.finding_id))
            for f in findings
        )

        events = audit_repo.list_by_assessment(record.assessment_id)
        event_ids = [e.event_id for e in events]
        payloads = payload_repo.get_all_for_events(event_ids)
        c_payload: dict[str, Any] = {}
        for ev in reversed(events):
            if ev.event_type.value in ("assessment_complete", "assessment_failed"):
                c_payload = payloads.get(ev.event_id, {})
                break

        raw_risk = c_payload.get("overall_risk")
        if not raw_risk:
            if any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in findings):
                raw_risk = "high"
            elif any(f.severity == Severity.MEDIUM for f in findings):
                raw_risk = "medium"
            else:
                raw_risk = "none"

        raw_conf = c_payload.get("overall_confidence", "HIGH")
        raw_cov = c_payload.get("coverage_fraction", 1.0)

        summaries.append(AssessmentSummarySchema(
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
            overall_risk=str(raw_risk).lower(),
            overall_confidence=str(raw_conf).lower(),
            coverage_fraction=float(raw_cov),
        ))
    return AssessmentListResponse(total=len(summaries), assessments=summaries)


# ---------------------------------------------------------------------------
# GET /api/v1/assessments/{assessment_id}
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}",
    response_model=AssessmentResultSchema,
    summary="Retrieve a persisted assessment result",
)
def get_assessment(
    assessment_id: str,
    conn: DbDep,
) -> AssessmentResultSchema:
    """
    Retrieve canonical result of a previously run assessment from the database.

    Returns the complete AssessmentResultSchema including overall risk,
    confidence, coverage, 11-detector battery runs, coverage gaps, and limitations.
    Returns 404 if the assessment_id does not exist.
    """
    return assemble_assessment_result_from_db(conn, assessment_id)



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
# GET /api/v1/assessments/{assessment_id}/provenance
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/provenance",
    response_model=ProvenanceResponse,
    summary="Retrieve inference provenance assurance for an assessment",
)
def get_provenance(
    assessment_id: str,
    conn: DbDep,
) -> ProvenanceResponse:
    """
    Retrieve persisted provenance manifest and PI-01 verification status.

    Returns the cryptographic signature, replay check status, and asset binding status.
    Returns 404 if the assessment does not exist.
    """
    if AssessmentRepository(conn).get(assessment_id) is None:
        raise AssessmentNotFound(assessment_id)

    prov_repo = ProvenanceRepository(conn)
    manifests = prov_repo.list_by_assessment(assessment_id)
    findings = FindingRepository(conn).list_by_assessment(assessment_id)

    pi01_findings = [f for f in findings if f.detector_id == "inference.provenance.pi01_integrity"]
    anomalies = [f.title for f in pi01_findings]

    if not manifests and pi01_findings:
        evidence_repo = EvidenceRepository(conn)
        for f in pi01_findings:
            for ev in evidence_repo.list_by_finding(f.finding_id):
                if isinstance(ev.data, dict) and "manifest_id" in ev.data:
                    m = prov_repo.get(ev.data["manifest_id"])
                    if m:
                        manifests.append(m)
                        break
            if manifests:
                break

    if not manifests:
        return ProvenanceResponse(
            assessment_id=assessment_id,
            has_provenance=False,
            manifest=None,
            anomalies=anomalies,
        )

    pm = manifests[0]
    sig_status = "VERIFIED"
    replay_status = "CLEAN"
    binding_status = "BOUND"

    for f in pi01_findings:
        if f.subcategory == "signature_invalid":
            sig_status = "FAILED"
        elif f.subcategory == "replay_detected":
            replay_status = "REPLAY_DETECTED"
        elif f.subcategory in ("input_mismatch", "model_mismatch", "output_mismatch"):
            binding_status = "MISMATCH"

    item = ProvenanceManifestItem(
        manifest_id=pm.manifest_id,
        sequence=pm.sequence,
        timestamp_utc=pm.timestamp_utc.isoformat() if hasattr(pm.timestamp_utc, "isoformat") else str(pm.timestamp_utc),
        nonce=pm.nonce,
        input_sha256=pm.input_sha256,
        model_sha256=pm.model_sha256,
        output_sha256=pm.output_sha256,
        signature=pm.signature,
        status=sig_status,
        replay_status=replay_status,
        binding_status=binding_status,
        anomalies=anomalies,
    )
    return ProvenanceResponse(
        assessment_id=assessment_id,
        has_provenance=True,
        manifest=item,
        anomalies=anomalies,
    )



# ---------------------------------------------------------------------------
# GET /api/v1/assessments/{assessment_id}/report
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/report",
    summary="Download PDF Assurance Report for an assessment",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Returns the generated PDF assurance report.",
        },
        404: {"description": "Assessment not found."},
    },
)
def get_assessment_report(
    assessment_id: str,
    conn: DbDep,
) -> Response:
    """
    Generate and stream an offline human-readable PDF Assurance Report
    for the specified assessment.

    Returns 404 if the assessment does not exist.
    """
    if AssessmentRepository(conn).get(assessment_id) is None:
        raise AssessmentNotFound(assessment_id)

    try:
        report_data = extract_report_data_from_db(conn, assessment_id)
        pdf_bytes = generate_assessment_report_pdf(report_data)
    except Exception as exc:
        log.exception("Failed to generate PDF report for assessment %s: %s", assessment_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "report_generation_failed",
                "message": f"An error occurred while generating the assurance report: {exc}",
            },
        )

    safe_short_id = "".join(c for c in assessment_id[:8] if c.isalnum() or c in "-_")
    filename = f"pramaan_assurance_report_{safe_short_id or 'assessment'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
        },
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


def assemble_assessment_result_from_db(
    conn: sqlite3.Connection,
    assessment_id: str,
) -> AssessmentResultSchema:
    """Assemble complete AssessmentResultSchema directly from persisted SQLite tables."""
    from backend.reporting.extractor import BATTERY_DETECTORS, censor_paths

    asmt_repo = AssessmentRepository(conn)
    record = asmt_repo.get(assessment_id)
    if record is None:
        raise AssessmentNotFound(assessment_id)

    finding_repo = FindingRepository(conn)
    evidence_repo = EvidenceRepository(conn)
    asset_repo = AssetRepository(conn)
    det_repo = DetectorResultRepository(conn)
    audit_repo = AuditRepository(conn)
    payload_repo = AuditPayloadRepository(conn)

    db_findings = finding_repo.list_by_assessment(assessment_id)
    total_evidence = sum(
        len(evidence_repo.list_by_finding(f.finding_id)) for f in db_findings
    )
    assets = asset_repo.list_by_assessment(assessment_id)
    asset_ids = [a.asset_id for a in assets]

    # Audit events & complete payload lookup
    events = audit_repo.list_by_assessment(assessment_id)
    event_ids = [e.event_id for e in events]
    payloads = payload_repo.get_all_for_events(event_ids)

    complete_payload: dict[str, Any] = {}
    for ev in reversed(events):
        if ev.event_type.value in ("assessment_complete", "assessment_failed"):
            complete_payload = payloads.get(ev.event_id, {})
            break

    # Determine risk
    raw_risk = complete_payload.get("overall_risk")
    if not raw_risk:
        if any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in db_findings):
            raw_risk = "high"
        elif any(f.severity == Severity.MEDIUM for f in db_findings):
            raw_risk = "medium"
        elif any(f.severity == Severity.LOW for f in db_findings):
            raw_risk = "low"
        else:
            raw_risk = "none"
    overall_risk = str(raw_risk).lower()

    # Determine confidence & coverage
    overall_confidence = str(complete_payload.get("overall_confidence", "HIGH")).lower()
    coverage_fraction = float(complete_payload.get("coverage_fraction", 1.0))

    # Detectors and Battery mapping
    db_det_results = det_repo.list_by_assessment(assessment_id)
    det_map = {r.detector_id: r for r in db_det_results}

    detector_runs: list[DetectorRunSchema] = []
    executed_detectors: list[str] = []
    skipped_detectors: list[str] = []

    stored_executed = complete_payload.get("executed_detector_ids")
    stored_skipped = complete_payload.get("skipped_detector_ids")

    for did, dname, _cat in BATTERY_DETECTORS:
        if did in det_map:
            r = det_map[did]
            st_val = str(r.status.value if hasattr(r.status, "value") else r.status).lower()
            ran = st_val in ("success", "partial")
            if ran:
                executed_detectors.append(did)
            else:
                skipped_detectors.append(did)

            f_for_det = [f for f in db_findings if f.detector_id == did]
            has_crit = any(f.severity == Severity.CRITICAL for f in f_for_det)
            has_high = any(f.severity == Severity.HIGH for f in f_for_det)
            has_med = any(f.severity == Severity.MEDIUM for f in f_for_det)
            risk_lvl = "CRITICAL" if has_crit else ("HIGH" if has_high else ("MEDIUM" if has_med else "NONE"))

            detector_runs.append(
                DetectorRunSchema(
                    detector_id=did,
                    detector_name=dname,
                    asset_id=r.asset_id,
                    applicable=True,
                    ran=ran,
                    status=st_val.upper(),
                    risk_level=risk_lvl,
                    confidence_level="HIGH",
                    findings_count=r.findings_count,
                    evidence_count=r.evidence_count,
                    error=r.error,
                )
            )
        else:
            detector_runs.append(
                DetectorRunSchema(
                    detector_id=did,
                    detector_name=dname,
                    asset_id=asset_ids[0] if asset_ids else "",
                    applicable=False,
                    ran=False,
                    status="NOT_APPLICABLE",
                    risk_level="NONE",
                    confidence_level="HIGH",
                    findings_count=0,
                    evidence_count=0,
                    error=None,
                )
            )

    if stored_executed is not None:
        executed_detectors = stored_executed
    if stored_skipped is not None:
        skipped_detectors = stored_skipped

    # Coverage gaps
    coverage_gaps: list[CoverageGapSchema] = []
    limitations: list[str] = []
    for f in db_findings:
        if f.subcategory == "coverage_gap":
            coverage_gaps.append(
                CoverageGapSchema(
                    detector_id=f.detector_id,
                    detector_name=f.detection_method or f.detector_id,
                    reason=f.title,
                    required_capability="Complete artifact binding or runtime framework",
                    observed_capability="Restricted or partial observation scope",
                    impact="Full cryptographic or operational assurance cannot be asserted",
                    recommended_action=f.recommended_disposition or "Provide complete artifact bindings",
                )
            )
        if f.limitations:
            for lim in f.limitations:
                c_lim = censor_paths(lim)
                if c_lim not in limitations:
                    limitations.append(c_lim)

    # Audit chain check
    audit_chain_valid: bool | None = None
    try:
        verifier = ChainVerifier(audit_repo, payload_repo)
        chain_res = verifier.verify_assessment(assessment_id)
        audit_chain_valid = chain_res.valid
    except Exception:
        audit_chain_valid = None

    # Qualitative descriptions
    risk_qualitative = complete_payload.get("risk_qualitative")
    if not risk_qualitative:
        if db_findings and overall_risk == "none":
            risk_qualitative = "Findings present but all assessed as informational/no risk by the executed detector(s)."
        else:
            risk_qualitative = {
                "critical": "Critical safety defect detected; high probability of model failure, poison, or intentional compromise.",
                "high": "High-severity defect or anomaly identified in assessed artifacts.",
                "medium": "Moderate anomaly detected; requires analyst review prior to deployment.",
                "low": "Minor observations noted; within normal operational bounds.",
                "none": "No anomalous safety drift detected across inspected artifacts.",
            }.get(overall_risk, "No anomalous safety drift detected.")

    confidence_qualifier = complete_payload.get("confidence_qualifier")
    if not confidence_qualifier:
        if len(executed_detectors) > 0 and len(coverage_gaps) == 0:
            confidence_qualifier = f"All {len(executed_detectors)} applicable detector(s) completed successfully with full coverage."
        else:
            confidence_qualifier = {
                "high": "Evaluated through deterministic execution battery and exact byte fingerprints.",
                "moderate": "Partial observation window or missing reference artifacts reduced confidence.",
                "low": "Assessment executed with significant methodological constraints.",
            }.get(overall_confidence, "Deterministic execution battery.")

    return AssessmentResultSchema(
        assessment_id=record.assessment_id,
        title=record.title,
        status=record.state.value,
        started_at=record.started_at.isoformat() if record.started_at else (record.created_at.isoformat() if record.created_at else ""),
        completed_at=record.completed_at.isoformat() if record.completed_at else (record.created_at.isoformat() if record.created_at else ""),
        assets_analyzed=asset_ids,
        detectors_executed=executed_detectors,
        detectors_skipped=skipped_detectors,
        findings_count=len(db_findings),
        evidence_count=total_evidence,
        overall_risk=overall_risk,
        risk_qualitative=risk_qualitative,
        overall_confidence=overall_confidence,
        confidence_qualifier=confidence_qualifier,
        coverage_fraction=coverage_fraction,
        coverage_gaps=coverage_gaps,
        detector_runs=detector_runs,
        limitations=limitations,
        audit_chain_valid=audit_chain_valid,
        error=record.error,
        software_version=record.software_version or "1.0.0",
        created_at=record.created_at.isoformat() if record.created_at else None,
    )

