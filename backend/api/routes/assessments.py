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

import json
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse

from backend.api.config import settings
from backend.api.deps import DbDep, ServiceDep, UploadRepoDep, BlobStoreDep
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
    EvidenceImagePreview,
    EvidencePreviewResponse,
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
    DatasetRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    ProvenanceRepository,
    SampleRepository,
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

    # 1b. Resolve optional dataset reference for DI-04 shift analysis
    dataset_reference_path: Path | None = None
    dataset_reference_format = _parse_dataset_format(body.dataset_reference_format)
    if body.dataset_reference_asset_id:
        upload = upload_repo.get(body.dataset_reference_asset_id)
        if upload and upload.asset_type == "dataset":
            resolved_ds_ref = Path(upload.storage_path)
            if resolved_ds_ref.exists():
                dataset_reference_path = resolved_ds_ref
                if dataset_reference_format is None and upload.format:
                    try:
                        dataset_reference_format = _parse_dataset_format(upload.format)
                    except Exception:
                        pass
    elif body.dataset_reference_path is not None:
        dataset_reference_path = _validate_asset_path(
            body.dataset_reference_path,
            max_size_mb=settings.max_dataset_size_mb * 1000,
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
        dataset_reference_path=dataset_reference_path,
        dataset_reference_format=dataset_reference_format,
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
# GET /api/v1/assessments/{assessment_id}/evidence/{evidence_id}/preview
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/evidence/{evidence_id}/preview",
    response_model=EvidencePreviewResponse,
    summary="Get safe preview metadata for an evidence record",
)
def get_evidence_preview(
    assessment_id: str,
    evidence_id: str,
    conn: DbDep,
    blob_store: BlobStoreDep,
) -> EvidencePreviewResponse:
    """
    Return structured or image preview metadata for an evidence record.
    Security: Strictly scoped to the assessment and evidence record.
    Does not expose absolute server filesystem paths.
    """
    if AssessmentRepository(conn).get(assessment_id) is None:
        raise AssessmentNotFound(assessment_id)

    ev_repo = EvidenceRepository(conn)
    evidence = ev_repo.get(evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "evidence_not_found", "message": f"Evidence {evidence_id!r} not found"},
        )

    finding = FindingRepository(conn).get(evidence.finding_id)
    if finding is None or finding.assessment_id != assessment_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "evidence_not_found", "message": f"Evidence {evidence_id!r} does not belong to assessment {assessment_id!r}"},
        )

    data = evidence.data or {}
    images: list[EvidenceImagePreview] = []
    dataset_repo = DatasetRepository(conn)
    sample_repo = SampleRepository(conn)
    datasets = dataset_repo.list_by_assessment(assessment_id)
    dataset_map = {d.dataset_id: d for d in datasets}

    def _try_resolve_sample(sample: Any, caption: str | None = None) -> EvidenceImagePreview | None:
        ds = dataset_map.get(sample.dataset_id)
        if not ds or not ds.source_path:
            return None
        ds_root = Path(ds.source_path).resolve()
        if ds_root.is_file():
            ds_root = ds_root.parent
        target = (ds_root / sample.file_name).resolve()
        try:
            target.relative_to(ds_root)
        except ValueError:
            return None  # Path traversal attempt rejected
        if not target.is_file():
            return None
        file_size = target.stat().st_size
        if file_size > 10 * 1024 * 1024:
            return None  # Oversized (>10MB)
        preview_url = f"/api/v1/assessments/{assessment_id}/evidence/{evidence_id}/samples/{sample.sample_id}/preview-file"
        return EvidenceImagePreview(
            sample_id=sample.sample_id,
            file_name=sample.file_name,
            preview_url=preview_url,
            width=sample.width,
            height=sample.height,
            size_bytes=sample.file_size_bytes or file_size,
            sha256=sample.sha256,
            caption=caption or f"Sample: {sample.file_name}",
        )

    # 1. Sample ID / File Name lookups from evidence.data
    # Check DI-01 duplicate cluster
    if "sample_ids" in data and isinstance(data["sample_ids"], list):
        for sid in data["sample_ids"][:8]:
            s = sample_repo.get(str(sid))
            if s:
                img_prev = _try_resolve_sample(s, caption=f"Cluster duplicate ({s.file_name})")
                if img_prev:
                    images.append(img_prev)

    if not images and "file_names" in data and isinstance(data["file_names"], list):
        for fn in data["file_names"][:8]:
            for ds in datasets:
                s = sample_repo.get_by_dataset_and_filename(ds.dataset_id, str(fn))
                if s:
                    img_prev = _try_resolve_sample(s, caption=f"Cluster duplicate ({s.file_name})")
                    if img_prev:
                        images.append(img_prev)
                        break

    # Check DI-03 affected_samples
    if not images and "affected_samples" in data and isinstance(data["affected_samples"], list):
        for item in data["affected_samples"][:8]:
            if isinstance(item, dict):
                sid = item.get("sample_id")
                fn = item.get("file_name")
                s = sample_repo.get(str(sid)) if sid else None
                if not s and fn:
                    for ds in datasets:
                        s = sample_repo.get_by_dataset_and_filename(ds.dataset_id, str(fn))
                        if s:
                            break
                if s:
                    cap = f"Trigger anomaly in {data.get('trigger_location', 'patch')} ({s.file_name})"
                    img_prev = _try_resolve_sample(s, caption=cap)
                    if img_prev:
                        images.append(img_prev)

    # Check single sample_id (DI-02, etc.)
    if not images and "sample_id" in data and isinstance(data["sample_id"], str):
        s = sample_repo.get(data["sample_id"])
        if s:
            img_prev = _try_resolve_sample(s)
            if img_prev:
                images.append(img_prev)

    if images:
        p_type = "image_cluster" if len(images) > 1 else "image"
        title = f"Perceptual Duplicate Cluster ({len(images)} images)" if "cluster" in evidence.evidence_type.value else f"Image Sample Preview ({len(images)} images)"
        return EvidencePreviewResponse(
            evidence_id=evidence_id,
            assessment_id=assessment_id,
            finding_id=finding.finding_id,
            detector_id=evidence.detector_id,
            evidence_type=evidence.evidence_type.value,
            preview_type=p_type,
            title=title,
            description=evidence.description,
            artifact_sha256=evidence.artifact_sha256,
            images=images,
            structured_content=evidence.data,
        )

    # 2. Attached artifact in BlobStore
    if evidence.artifact_sha256 and blob_store.exists(evidence.artifact_sha256):
        blob_path = blob_store.blob_path(evidence.artifact_sha256)
        size = blob_path.stat().st_size
        if size > 10 * 1024 * 1024:
            return EvidencePreviewResponse(
                evidence_id=evidence_id,
                assessment_id=assessment_id,
                finding_id=finding.finding_id,
                detector_id=evidence.detector_id,
                evidence_type=evidence.evidence_type.value,
                preview_type="unsupported",
                size_bytes=size,
                title="Artifact Exceeds Preview Size Limit",
                description=evidence.description,
                artifact_sha256=evidence.artifact_sha256,
                unsupported_reason="Artifact size exceeds maximum 10MB preview threshold",
                structured_content=evidence.data,
                truncated=True,
            )

        with open(blob_path, "rb") as bf:
            header = bf.read(512)

        # Check image formats
        img_mime = None
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            img_mime = "image/png"
        elif header.startswith(b"\xff\xd8\xff"):
            img_mime = "image/jpeg"
        elif header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
            img_mime = "image/gif"
        elif header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            img_mime = "image/webp"
        elif header.startswith(b"BM"):
            img_mime = "image/bmp"

        if img_mime:
            preview_url = f"/api/v1/assessments/{assessment_id}/evidence/{evidence_id}/artifact-file"
            return EvidencePreviewResponse(
                evidence_id=evidence_id,
                assessment_id=assessment_id,
                finding_id=finding.finding_id,
                detector_id=evidence.detector_id,
                evidence_type=evidence.evidence_type.value,
                preview_type="image",
                mime_type=img_mime,
                size_bytes=size,
                title="Evidence Artifact Image",
                description=evidence.description,
                artifact_sha256=evidence.artifact_sha256,
                images=[EvidenceImagePreview(
                    file_name=f"artifact_{evidence.artifact_sha256[:8]}",
                    preview_url=preview_url,
                    size_bytes=size,
                    sha256=evidence.artifact_sha256,
                    caption="Attached evidence artifact",
                )],
                structured_content=evidence.data,
            )

        # Check text / JSON
        try:
            text = blob_path.read_text(encoding="utf-8")
            truncated = len(text) > 65536
            bounded_text = text[:65536]
            try:
                jdata = json.loads(bounded_text)
                return EvidencePreviewResponse(
                    evidence_id=evidence_id,
                    assessment_id=assessment_id,
                    finding_id=finding.finding_id,
                    detector_id=evidence.detector_id,
                    evidence_type=evidence.evidence_type.value,
                    preview_type="json",
                    mime_type="application/json",
                    size_bytes=size,
                    title="Evidence Artifact JSON",
                    description=evidence.description,
                    artifact_sha256=evidence.artifact_sha256,
                    structured_content=jdata if isinstance(jdata, dict) else {"content": jdata},
                    text_content=bounded_text,
                    truncated=truncated,
                )
            except json.JSONDecodeError:
                return EvidencePreviewResponse(
                    evidence_id=evidence_id,
                    assessment_id=assessment_id,
                    finding_id=finding.finding_id,
                    detector_id=evidence.detector_id,
                    evidence_type=evidence.evidence_type.value,
                    preview_type="structured_text",
                    mime_type="text/plain",
                    size_bytes=size,
                    title="Evidence Artifact Text",
                    description=evidence.description,
                    artifact_sha256=evidence.artifact_sha256,
                    text_content=bounded_text,
                    truncated=truncated,
                )
        except UnicodeDecodeError:
            return EvidencePreviewResponse(
                evidence_id=evidence_id,
                assessment_id=assessment_id,
                finding_id=finding.finding_id,
                detector_id=evidence.detector_id,
                evidence_type=evidence.evidence_type.value,
                preview_type="unsupported",
                mime_type="application/octet-stream",
                size_bytes=size,
                title="Binary Evidence Artifact",
                description=evidence.description,
                artifact_sha256=evidence.artifact_sha256,
                unsupported_reason="Binary model weights or serialized tensor artifact (.onnx / .pt) cannot be previewed inline for security and memory safety. Inspect layer structure below.",
                structured_content=evidence.data,
            )

    # 3. Structured telemetry preview (default)
    return EvidencePreviewResponse(
        evidence_id=evidence_id,
        assessment_id=assessment_id,
        finding_id=finding.finding_id,
        detector_id=evidence.detector_id,
        evidence_type=evidence.evidence_type.value,
        preview_type="structured",
        mime_type="application/json",
        title=f"{evidence.evidence_type.value.replace('_', ' ').title()} Telemetry Preview",
        description=evidence.description,
        artifact_sha256=evidence.artifact_sha256,
        structured_content=evidence.data,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/assessments/{assessment_id}/evidence/{evidence_id}/artifact-file
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/evidence/{evidence_id}/artifact-file",
    summary="Stream safe previewable artifact file bytes",
)
def get_evidence_artifact_file(
    assessment_id: str,
    evidence_id: str,
    conn: DbDep,
    blob_store: BlobStoreDep,
):
    if AssessmentRepository(conn).get(assessment_id) is None:
        raise AssessmentNotFound(assessment_id)

    evidence = EvidenceRepository(conn).get(evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "evidence_not_found", "message": f"Evidence {evidence_id!r} not found"},
        )

    finding = FindingRepository(conn).get(evidence.finding_id)
    if finding is None or finding.assessment_id != assessment_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "evidence_not_found", "message": f"Evidence {evidence_id!r} does not belong to assessment {assessment_id!r}"},
        )

    if not evidence.artifact_sha256 or not blob_store.exists(evidence.artifact_sha256):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "artifact_not_found", "message": "Evidence artifact is not stored in blob repository"},
        )

    blob_path = blob_store.blob_path(evidence.artifact_sha256)
    file_size = blob_path.stat().st_size
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": "file_too_large", "message": "Artifact exceeds maximum preview limit (10MB)"},
        )

    with open(blob_path, "rb") as f:
        header = f.read(512)

    media_type = None
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        media_type = "image/png"
    elif header.startswith(b"\xff\xd8\xff"):
        media_type = "image/jpeg"
    elif header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        media_type = "image/gif"
    elif header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        media_type = "image/webp"
    elif header.startswith(b"BM"):
        media_type = "image/bmp"
    else:
        try:
            blob_path.read_text(encoding="utf-8")
            media_type = "text/plain; charset=utf-8"
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "unsupported_preview_format", "message": "Binary artifact cannot be streamed as preview"},
            )

    return Response(
        content=blob_path.read_bytes(),
        media_type=media_type,
        headers={
            "Content-Security-Policy": "default-src 'none'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="artifact_{evidence.artifact_sha256[:8]}"',
        },
    )


# ---------------------------------------------------------------------------
# GET /api/v1/assessments/{assessment_id}/evidence/{evidence_id}/samples/{sample_id}/preview-file
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/evidence/{evidence_id}/samples/{sample_id}/preview-file",
    summary="Stream safe previewable sample image bytes",
)
def get_evidence_sample_file(
    assessment_id: str,
    evidence_id: str,
    sample_id: str,
    conn: DbDep,
):
    if AssessmentRepository(conn).get(assessment_id) is None:
        raise AssessmentNotFound(assessment_id)

    evidence = EvidenceRepository(conn).get(evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "evidence_not_found", "message": f"Evidence {evidence_id!r} not found"},
        )

    finding = FindingRepository(conn).get(evidence.finding_id)
    if finding is None or finding.assessment_id != assessment_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "evidence_not_found", "message": f"Evidence {evidence_id!r} does not belong to assessment {assessment_id!r}"},
        )

    sample = SampleRepository(conn).get(sample_id)
    if sample is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "sample_not_found", "message": f"Sample {sample_id!r} not found"},
        )

    # Verify sample is referenced in evidence.data
    data = evidence.data or {}
    ref_ids = set()
    ref_files = set()
    if isinstance(data.get("sample_ids"), list):
        ref_ids.update(str(x) for x in data["sample_ids"])
    if isinstance(data.get("file_names"), list):
        ref_files.update(str(x) for x in data["file_names"])
    if isinstance(data.get("affected_samples"), list):
        for s_item in data["affected_samples"]:
            if isinstance(s_item, dict):
                if s_item.get("sample_id"):
                    ref_ids.add(str(s_item["sample_id"]))
                if s_item.get("file_name"):
                    ref_files.add(str(s_item["file_name"]))
    if isinstance(data.get("sample_id"), str):
        ref_ids.add(data["sample_id"])

    if sample.sample_id not in ref_ids and sample.file_name not in ref_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "sample_not_in_evidence", "message": f"Sample {sample_id!r} is not referenced in evidence {evidence_id!r}"},
        )

    dataset = DatasetRepository(conn).get(sample.dataset_id)
    if dataset is None or dataset.assessment_id != assessment_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "dataset_not_found", "message": "Dataset not found or does not belong to assessment"},
        )

    # Strict containment check
    ds_root = Path(dataset.source_path).resolve()
    if ds_root.is_file():
        ds_root = ds_root.parent
    target_path = (ds_root / sample.file_name).resolve()

    try:
        target_path.relative_to(ds_root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "path_traversal", "message": "Access denied: file path escapes dataset root directory"},
        )

    if not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "file_not_found", "message": "Sample file not found on disk"},
        )

    file_size = target_path.stat().st_size
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": "file_too_large", "message": "Sample image exceeds maximum preview limit (10MB)"},
        )

    with open(target_path, "rb") as f:
        header = f.read(512)

    media_type = None
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        media_type = "image/png"
    elif header.startswith(b"\xff\xd8\xff"):
        media_type = "image/jpeg"
    elif header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        media_type = "image/gif"
    elif header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        media_type = "image/webp"
    elif header.startswith(b"BM"):
        media_type = "image/bmp"

    if not media_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "unsupported_preview_format", "message": "File is not a supported previewable image format"},
        )

    return Response(
        content=target_path.read_bytes(),
        media_type=media_type,
        headers={
            "Content-Security-Policy": "default-src 'none'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{sample.file_name}"',
        },
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
# GET /api/v1/assessments/{assessment_id}/audit/export
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/audit/export",
    summary="Export verified audit trail as structured JSON",
    response_class=Response,
    responses={
        200: {
            "content": {"application/json": {}},
            "description": "Returns the machine-readable verified audit trail export package.",
        },
        404: {"description": "Assessment not found."},
    },
)
def export_audit_json_endpoint(
    assessment_id: str,
    conn: DbDep,
) -> Response:
    """
    Export the cryptographically verified audit trail for an assessment as structured JSON.
    Includes genesis hash, sequential events, hashes, payload digests, pre-signature hashes,
    Ed25519 signature statuses, and ChainVerifier outcome.
    Ensures zero leakage of server filesystem paths, private keys, or credentials.
    """
    from backend.reporting.exporter import export_audit_trail_json

    export_dict = export_audit_trail_json(conn, assessment_id)
    json_bytes = json.dumps(export_dict, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")

    safe_short_id = "".join(c for c in assessment_id[:8] if c.isalnum() or c in "-_")
    filename = f"pramaan_audit_export_{safe_short_id or 'assessment'}.json"
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/json; charset=utf-8",
        },
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
# GET /api/v1/assessments/{assessment_id}/export/json
# ---------------------------------------------------------------------------

@router.get(
    "/assessments/{assessment_id}/export/json",
    summary="Export machine-readable structured JSON assurance package",
    response_class=Response,
    responses={
        200: {
            "content": {"application/json": {}},
            "description": "Returns the machine-readable JSON assurance export package.",
        },
        404: {"description": "Assessment not found."},
    },
)
def export_assessment_json_endpoint(
    assessment_id: str,
    conn: DbDep,
) -> Response:
    """
    Export a machine-readable JSON assurance package for the specified assessment.
    Contains metadata, assets, findings, evidence references, provenance, and audit trail.
    Ensures zero leakage of server filesystem paths, private keys, API keys, or raw artifact bytes.
    """
    from backend.reporting.exporter import export_assessment_json

    export_dict = export_assessment_json(conn, assessment_id)
    json_bytes = json.dumps(export_dict, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8")

    safe_short_id = "".join(c for c in assessment_id[:8] if c.isalnum() or c in "-_")
    filename = f"pramaan_assurance_export_{safe_short_id or 'assessment'}.json"
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/json; charset=utf-8",
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

