"""
PRAMAAN Assessment Orchestrator.

This module is the single point of entry for running a PRAMAAN assessment.
It coordinates the existing Phase 1-6 capabilities:

  Phase 2 - Secure dataset ingestion
  Phase 3 - DI-01 duplicate/near-duplicate detection
  Phase 4 - MI-01 model integrity/fingerprinting
  Phase 5 - PI-01 cryptographic provenance/output integrity
  Phase 6 - Tamper-evident audit trail

The orchestrator does NOT contain detection algorithms. It:
  1. Validates the request (fail-closed)
  2. Creates the Assessment record and audit event
  3. Ingests assets through the existing ingestion pipeline
  4. Selects applicable detectors from the registry
  5. Builds per-detector contexts
  6. Runs each detector through run_detector()
  7. Aggregates risk / confidence / coverage (ADR-003)
  8. Verifies the audit chain
  9. Returns a structured AssessmentResult

Design rules
------------
- An unavailable detector -> CoverageGap, NOT a silent clean result.
- Detector failures -> visible in result, orchestration continues for independent detectors.
- Invalid input -> FAILED assessment (fail-closed).
- Same inputs -> same risk/confidence/coverage (deterministic).
- No randomness in aggregation.
- Private keys are never stored in any record.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.assessment.aggregator import (
    aggregate_confidence,
    aggregate_risk,
    compute_coverage,
    derive_limitations,
)
from backend.assessment.models import (
    AssessmentRequest,
    AssessmentResult,
    CoverageGapRecord,
    DetectorRunRecord,
)
from backend.audit.integration import make_audit_service
from backend.audit.verifier import ChainVerifier
from backend.detectors.base import DetectorContext, DetectorOutput
from backend.detectors.data.di01_duplicates import DI01DuplicateDetector
from backend.detectors.data.di02_label_integrity import DI02LabelIntegrityDetector
from backend.detectors.data.di03_trigger_anomaly import DI03TriggerAnomalyDetector
from backend.detectors.data.di04_ood_distribution import DI04DistributionOODDetector
from backend.detectors.data.di05_contributor_risk import DI05ContributorRiskDetector
from backend.detectors.model.mi01_fingerprint import MI01Context, MI01FingerprintDetector
from backend.detectors.model.mi02_parameter_stats import MI02Context, MI02ParameterStatsDetector
from backend.detectors.model.mi03_activation_stats import MI03Context, MI03ActivationStatsDetector
from backend.detectors.model.mi04_reference_comparison import MI04Context, MI04ReferenceComparisonDetector
from backend.detectors.model.mi05_trigger_anomaly import MI05Context, MI05TriggerAnomalyDetector
from backend.detectors.provenance.pi01_integrity import PI01Context, PI01ProvenanceIntegrityDetector
from backend.detectors.runner import run_detector
from backend.domain.entities import Assessment, Asset, Dataset, ModelArtifact
from backend.domain.enums import (
    AccessLevel,
    AssessmentState,
    AssetType,
    AuditEventType,
    ConfidenceLevel,
    DatasetFormat,
    DetectorStatus,
    ModelFramework,
    RiskLevel,
)
from backend.infra.db import (
    AssetRepository,
    AssessmentRepository,
    AuditPayloadRepository,
    AuditRepository,
    DatasetRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    ModelArtifactRepository,
    SampleRepository,
)
from backend.infra.ingestion import (
    IngestionResult,
    ingest_coco_dataset,
    ingest_image_directory,
    register_dataset,
)

log = logging.getLogger(__name__)

_PRAMAAN_VERSION = "1.0.0"

# Detectors that completed (ran), for counting coverage
_RAN_STATUSES = {DetectorStatus.SUCCESS.value, DetectorStatus.PARTIAL.value}

# Detectors that count as "not ran" even if applicable
_SKIP_STATUSES = {
    DetectorStatus.SKIPPED.value,
    DetectorStatus.NOT_APPLICABLE.value,
    DetectorStatus.UNAVAILABLE.value,
}


# ---------------------------------------------------------------------------
# AssessmentService
# ---------------------------------------------------------------------------

class AssessmentService:
    """
    Orchestrates end-to-end PRAMAAN assessments.

    Usage
    -----
        service = AssessmentService(conn)
        result = service.run_assessment(request)

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection with the PRAMAAN schema initialised (via open_db()).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._assessment_repo = AssessmentRepository(conn)
        self._asset_repo = AssetRepository(conn)
        self._dataset_repo = DatasetRepository(conn)
        self._sample_repo = SampleRepository(conn)
        self._model_artifact_repo = ModelArtifactRepository(conn)
        self._finding_repo = FindingRepository(conn)
        self._evidence_repo = EvidenceRepository(conn)
        self._result_repo = DetectorResultRepository(conn)
        self._audit_repo = AuditRepository(conn)
        self._payload_repo = AuditPayloadRepository(conn)
        self._audit_svc = make_audit_service(conn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_assessment(self, request: AssessmentRequest) -> AssessmentResult:
        """
        Run a PRAMAAN assessment end-to-end.

        This is the primary entry point. It coordinates every phase of the
        assessment lifecycle. The same inputs will always produce the same
        analytical result (deterministic).

        Parameters
        ----------
        request : AssessmentRequest
            Fully populated request object.

        Returns
        -------
        AssessmentResult - structured result with risk, confidence, coverage,
        findings count, gaps, and audit verification status.
        """
        started_at = datetime.now(timezone.utc)

        # ----------------------------------------------------------------
        # 1. Validate request (fail-closed)
        # ----------------------------------------------------------------
        errors = request.validate()
        if errors:
            err_msg = "; ".join(errors)
            log.error("Assessment request validation failed: %s", err_msg)
            return self._failed_result(
                request=request,
                started_at=started_at,
                error=f"Invalid request: {err_msg}",
            )

        assess_id = request.assessment_id

        # ----------------------------------------------------------------
        # 2. Create assessment record + audit event
        # ----------------------------------------------------------------
        try:
            assessment = Assessment(
                assessment_id=assess_id,
                title=request.title,
                state=AssessmentState.CREATED,
                software_version=_PRAMAAN_VERSION,
            )
            self._assessment_repo.insert(assessment)
            self._assessment_repo.update_state(assess_id, AssessmentState.ANALYZING)

            self._audit_svc.record_assessment_created(
                assessment_id=assess_id,
                title=request.title,
                assessment_type="live",
            )
        except Exception as exc:
            log.exception("Failed to create assessment record")
            return self._failed_result(request, started_at, f"Assessment creation failed: {exc}")

        # ----------------------------------------------------------------
        # 3. Ingest / register assets
        # ----------------------------------------------------------------
        asset_ids: list[str] = []
        dataset_asset_id: str | None = None
        model_asset_id: str | None = None
        inference_bundle_asset_id: str | None = None

        # --- Dataset ingestion ---
        if request.dataset_path is not None:
            try:
                dataset_asset_id = self._ingest_dataset(request, assess_id)
                asset_ids.append(dataset_asset_id)
            except Exception as exc:
                log.exception("Dataset ingestion failed")
                err = str(exc)
                self._assessment_repo.update_state(
                    assess_id, AssessmentState.FAILED, error=err
                )
                return self._failed_result(request, started_at, f"Dataset ingestion failed: {err}")

        # --- Model asset registration ---
        if request.model_path is not None:
            try:
                model_asset_id = self._register_model(request, assess_id)
                asset_ids.append(model_asset_id)
            except Exception as exc:
                log.exception("Model registration failed")
                err = str(exc)
                self._assessment_repo.update_state(
                    assess_id, AssessmentState.FAILED, error=err
                )
                return self._failed_result(request, started_at, f"Model registration failed: {err}")

        # --- Provenance bundle registration ---
        if request.provenance_manifest is not None:
            try:
                inference_bundle_asset_id = self._register_inference_bundle(request, assess_id)
                asset_ids.append(inference_bundle_asset_id)
            except Exception as exc:
                log.exception("Provenance bundle registration failed")
                err = str(exc)
                self._assessment_repo.update_state(
                    assess_id, AssessmentState.FAILED, error=err
                )
                return self._failed_result(
                    request, started_at, f"Provenance registration failed: {err}"
                )

        # ----------------------------------------------------------------
        # 4. Detector selection
        # ----------------------------------------------------------------
        detector_plans = self._select_detectors(
            request=request,
            assess_id=assess_id,
            dataset_asset_id=dataset_asset_id,
            model_asset_id=model_asset_id,
            inference_bundle_asset_id=inference_bundle_asset_id,
        )

        # ----------------------------------------------------------------
        # 5. Execute detectors
        # ----------------------------------------------------------------
        all_outputs: list[DetectorOutput] = []
        run_records: list[DetectorRunRecord] = []
        gaps: list[CoverageGapRecord] = []

        for plan in detector_plans:
            record, output = self._execute_detector_plan(plan, assess_id)
            run_records.append(record)
            if output is not None:
                all_outputs.append(output)
            if record.coverage_gap is not None:
                gaps.append(record.coverage_gap)

        # ----------------------------------------------------------------
        # 6. Aggregate
        # ----------------------------------------------------------------
        total_applicable = sum(1 for r in run_records if r.applicable)
        executed_applicable = sum(
            1 for r in run_records
            if r.applicable and r.status in _RAN_STATUSES
        )
        coverage_fraction = compute_coverage(total_applicable, executed_applicable)

        overall_risk, risk_qualitative = aggregate_risk(all_outputs)
        overall_confidence, confidence_qualifier, _ = aggregate_confidence(
            all_outputs, gaps, coverage_fraction
        )
        limitations = derive_limitations(gaps, all_outputs)

        detectors_executed = [r.detector_id for r in run_records if r.ran]
        detectors_skipped = [r.detector_id for r in run_records if r.applicable and not r.ran]

        total_findings = sum(r.findings_count for r in run_records if r.ran)
        total_evidence = sum(r.evidence_count for r in run_records if r.ran)

        # ----------------------------------------------------------------
        # 7. Verify audit chain
        # ----------------------------------------------------------------
        audit_chain_valid: bool | None = None
        try:
            verifier = ChainVerifier(self._audit_repo, self._payload_repo)
            chain_result = verifier.verify_assessment(assess_id)
            audit_chain_valid = chain_result.valid

            self._audit_svc.record_audit_verified(
                assessment_id=assess_id,
                events_checked=chain_result.events_checked,
                chain_valid=chain_result.valid,
                failure_count=len(chain_result.failures),
                first_invalid_event_id=chain_result.first_invalid_event_id,
            )
        except Exception as exc:
            log.warning("Audit chain verification failed: %s", exc)
            audit_chain_valid = None

        # ----------------------------------------------------------------
        # 8. Finalize
        # ----------------------------------------------------------------
        completed_at = datetime.now(timezone.utc)
        self._assessment_repo.update_state(assess_id, AssessmentState.COMPLETE)

        try:
            self._audit_svc.emit_event(
                AuditEventType.ASSESSMENT_COMPLETE,
                payload={
                    "assessment_id":          assess_id,
                    "overall_risk":           overall_risk.value,
                    "overall_confidence":     overall_confidence.value,
                    "coverage_fraction":      round(coverage_fraction, 4),
                    "findings_count":         total_findings,
                    "evidence_count":         total_evidence,
                    "detectors_executed":     len(detectors_executed),
                    "coverage_gaps_count":    len(gaps),
                },
                assessment_id=assess_id,
            )
        except Exception as exc:
            log.warning("Failed to emit ASSESSMENT_COMPLETE audit event: %s", exc)

        return AssessmentResult(
            assessment_id=assess_id,
            title=request.title,
            status=AssessmentState.COMPLETE,
            started_at=started_at,
            completed_at=completed_at,
            assets_analyzed=asset_ids,
            detectors_executed=detectors_executed,
            detectors_skipped=detectors_skipped,
            findings_count=total_findings,
            evidence_count=total_evidence,
            overall_risk=overall_risk,
            risk_qualitative=risk_qualitative,
            overall_confidence=overall_confidence,
            confidence_qualifier=confidence_qualifier,
            coverage_fraction=coverage_fraction,
            coverage_gaps=gaps,
            detector_runs=run_records,
            limitations=limitations,
            audit_chain_valid=audit_chain_valid,
            error=None,
        )

    # ------------------------------------------------------------------
    # Private -- asset ingestion / registration
    # ------------------------------------------------------------------

    def _ingest_dataset(
        self,
        request: AssessmentRequest,
        assess_id: str,
    ) -> str:
        """
        Register and ingest a dataset through the existing ingestion pipeline.

        Returns the dataset_asset_id.
        """
        path = request.dataset_path
        fmt = request.dataset_format
        name = path.name if hasattr(path, "name") else str(path)

        # Register asset + dataset records first
        asset, dataset = register_dataset(
            assessment_id=assess_id,
            name=name,
            source_path=path,
            fmt=fmt,
            conn=self._conn,
        )
        dataset_id = dataset.dataset_id

        # Now ingest images into the registered dataset
        if fmt == DatasetFormat.IMAGE_DIR:
            result: IngestionResult = ingest_image_directory(
                directory=path,
                dataset_id=dataset_id,
                conn=self._conn,
                skip_invalid_images=False,
            )
        elif fmt == DatasetFormat.COCO_JSON:
            # For COCO_JSON: path is the JSON file; images_dir is its parent
            result = ingest_coco_dataset(
                coco_json_path=path,
                images_dir=path.parent,
                dataset_id=dataset_id,
                conn=self._conn,
                skip_invalid_images=False,
            )
        else:
            raise ValueError(f"Unsupported dataset format: {fmt!r}")

        # Emit audit events
        try:
            self._audit_svc.record_asset_registered(
                assessment_id=assess_id,
                asset_id=dataset_id,
                asset_type=AssetType.DATASET.value,
                name=name,
                sha256=asset.sha256,
                size_bytes=result.samples_ingested,
            )
            self._audit_svc.record_ingestion_complete(
                assessment_id=assess_id,
                dataset_id=dataset_id,
                sample_count=result.samples_ingested,
            )
        except Exception as exc:
            log.warning("Failed to emit dataset audit events: %s", exc)

        return dataset_id

    def _register_model(
        self,
        request: AssessmentRequest,
        assess_id: str,
    ) -> str:
        """Register a model file as an asset (does not run MI-01 yet)."""
        model_path = request.model_path
        sha256 = _hash_file(model_path)
        size_bytes = model_path.stat().st_size
        asset_id = _deterministic_id(sha256, assess_id, "model")

        # Detect framework from extension
        suffix = model_path.suffix.lower()
        framework_map: dict[str, ModelFramework] = {
            ".onnx": ModelFramework.ONNX,
            ".pt":   ModelFramework.PYTORCH,
            ".pth":  ModelFramework.PYTORCH,
            ".ts":   ModelFramework.TORCHSCRIPT,
        }
        framework = framework_map.get(suffix, ModelFramework.UNKNOWN)

        asset = Asset(
            asset_id=asset_id,
            assessment_id=assess_id,
            asset_type=AssetType.MODEL,
            name=model_path.name,
            sha256=sha256,
            size_bytes=size_bytes,
        )
        model_artifact = ModelArtifact(
            model_id=asset_id,
            assessment_id=assess_id,
            framework=framework,
            access_level=AccessLevel.WHITE_BOX,
            source_path=str(model_path),
        )

        self._asset_repo.insert(asset)
        self._model_artifact_repo.insert(model_artifact)

        try:
            self._audit_svc.record_asset_registered(
                assessment_id=assess_id,
                asset_id=asset_id,
                asset_type=AssetType.MODEL.value,
                name=model_path.name,
                sha256=sha256,
                size_bytes=size_bytes,
            )
        except Exception as exc:
            log.warning("Failed to emit model asset audit event: %s", exc)

        return asset_id

    def _register_inference_bundle(
        self,
        request: AssessmentRequest,
        assess_id: str,
    ) -> str:
        """Register a provenance manifest as an inference-bundle asset."""
        manifest = request.provenance_manifest
        # Stable fingerprint for the manifest itself
        manifest_sha = hashlib.sha256(
            (manifest.manifest_id + (manifest.digest or "")).encode()
        ).hexdigest()
        asset_id = _deterministic_id(manifest_sha, assess_id, "inference_bundle")

        asset = Asset(
            asset_id=asset_id,
            assessment_id=assess_id,
            asset_type=AssetType.INFERENCE_BUNDLE,
            name=f"manifest_{manifest.manifest_id[:8]}",
            sha256=manifest_sha,
            size_bytes=0,
        )
        self._asset_repo.insert(asset)

        try:
            self._audit_svc.record_asset_registered(
                assessment_id=assess_id,
                asset_id=asset_id,
                asset_type=AssetType.INFERENCE_BUNDLE.value,
                name=asset.name,
                sha256=manifest_sha,
                size_bytes=0,
            )
        except Exception as exc:
            log.warning("Failed to emit inference bundle audit event: %s", exc)

        return asset_id

    # ------------------------------------------------------------------
    # Private -- detector selection
    # ------------------------------------------------------------------

    def _select_detectors(
        self,
        request: AssessmentRequest,
        assess_id: str,
        dataset_asset_id: str | None,
        model_asset_id: str | None,
        inference_bundle_asset_id: str | None,
    ) -> list[dict[str, Any]]:
        """
        Determine which detectors are applicable and build execution plans.

        An execution plan is a dict:
          detector       -- detector instance
          asset_id       -- which asset it runs against
          context_extras -- extra context attributes (mi01, pi01, ...)
          applicable     -- bool

        A detector is applicable when the relevant asset was provided.
        It may still fail can_run() later (framework unavailable etc.).
        can_run() failure -> CoverageGap, not silence.
        """
        plans: list[dict[str, Any]] = []

        # --- DI-01..DI-05: dataset integrity suite ---
        dataset_detectors = [
            (
                DI01DuplicateDetector(),
                {
                    "phash_threshold": request.phash_threshold,
                    "dhash_threshold": request.dhash_threshold,
                },
            ),
            (DI02LabelIntegrityDetector(), {}),
            (DI03TriggerAnomalyDetector(), {}),
            (DI04DistributionOODDetector(), {}),
            (DI05ContributorRiskDetector(), {}),
        ]
        for det, extras in dataset_detectors:
            if dataset_asset_id is not None:
                plans.append({
                    "detector":       det,
                    "asset_id":       dataset_asset_id,
                    "applicable":     True,
                    "context_extras": extras,
                })
            else:
                plans.append({
                    "detector":              det,
                    "asset_id":              None,
                    "applicable":            False,
                    "context_extras":        {},
                    "not_applicable_reason": "no_dataset_provided",
                })

        # --- MI-01, MI-02, MI-03, MI-05: general model integrity detectors ---
        has_model = model_asset_id is not None
        base_mi_detectors = [
            (
                MI01FingerprintDetector(),
                {
                    "mi01": MI01Context(
                        model_path=request.model_path,
                        reference_fingerprint=request.model_reference_fingerprint,
                    )
                },
            ),
            (
                MI02ParameterStatsDetector(),
                {"mi02": MI02Context(model_path=request.model_path)},
            ),
            (
                MI03ActivationStatsDetector(),
                {"mi03": MI03Context(model_path=request.model_path)},
            ),
            (
                MI05TriggerAnomalyDetector(),
                {"mi05": MI05Context(model_path=request.model_path)},
            ),
        ]
        for det, extras in base_mi_detectors:
            if has_model:
                plans.append({
                    "detector":       det,
                    "asset_id":       model_asset_id,
                    "applicable":     True,
                    "context_extras": extras,
                })
            else:
                plans.append({
                    "detector":              det,
                    "asset_id":              None,
                    "applicable":            False,
                    "context_extras":        {},
                    "not_applicable_reason": "no_model_provided",
                })

        # --- MI-04: reference model comparison (applicable only when reference supplied) ---
        has_reference = (
            request.model_reference_path is not None
            or request.model_reference_fingerprint is not None
        )
        if has_model and has_reference:
            plans.append({
                "detector":       MI04ReferenceComparisonDetector(),
                "asset_id":       model_asset_id,
                "applicable":     True,
                "context_extras": {
                    "mi04": MI04Context(
                        model_path=request.model_path,
                        reference_model_path=request.model_reference_path,
                        reference_fingerprint=request.model_reference_fingerprint,
                    )
                },
            })
        elif has_model:
            plans.append({
                "detector":              MI04ReferenceComparisonDetector(),
                "asset_id":              model_asset_id,
                "applicable":            False,
                "context_extras":        {},
                "not_applicable_reason": "no_reference_model_provided",
            })
        else:
            plans.append({
                "detector":              MI04ReferenceComparisonDetector(),
                "asset_id":              None,
                "applicable":            False,
                "context_extras":        {},
                "not_applicable_reason": "no_model_provided",
            })

        # --- PI-01: provenance manifest ---
        if inference_bundle_asset_id is not None:
            pi01_ctx = PI01Context(
                manifest=request.provenance_manifest,
                public_key=request.provenance_public_key,
                actual_input_bytes=request.actual_input_bytes,
                actual_output_bytes=request.actual_output_bytes,
                actual_model_sha256=request.actual_model_sha256,
                known_manifests=[],   # V1: no prior manifests tracked by orchestrator
            )
            plans.append({
                "detector":       PI01ProvenanceIntegrityDetector(),
                "asset_id":       inference_bundle_asset_id,
                "applicable":     True,
                "context_extras": {"pi01": pi01_ctx},
            })
        else:
            plans.append({
                "detector":              PI01ProvenanceIntegrityDetector(),
                "asset_id":              None,
                "applicable":            False,
                "context_extras":        {},
                "not_applicable_reason": "no_provenance_manifest_provided",
            })

        return plans

    # ------------------------------------------------------------------
    # Private -- detector execution
    # ------------------------------------------------------------------

    def _execute_detector_plan(
        self,
        plan: dict[str, Any],
        assess_id: str,
    ) -> tuple[DetectorRunRecord, DetectorOutput | None]:
        """
        Execute one detector plan.

        Returns (DetectorRunRecord, DetectorOutput | None).
        DetectorOutput is None when the detector is not applicable or skipped.
        """
        detector = plan["detector"]
        meta = detector.metadata
        applicable = plan["applicable"]

        if not applicable:
            # Not applicable -- not a gap, just not relevant for this assessment
            return (
                DetectorRunRecord(
                    detector_id=meta.detector_id,
                    detector_name=meta.name,
                    asset_id="",
                    applicable=False,
                    ran=False,
                    status=DetectorStatus.NOT_APPLICABLE.value,
                    risk_level=RiskLevel.NONE.value,
                    confidence_level=ConfidenceLevel.LOW.value,
                    findings_count=0,
                    evidence_count=0,
                    error=None,
                    coverage_gap=None,
                ),
                None,
            )

        asset_id = plan["asset_id"]
        context_extras: dict[str, Any] = plan.get("context_extras", {})

        # Build context — use thresholds from extras or defaults
        phash_threshold = context_extras.pop("phash_threshold", 10)
        dhash_threshold = context_extras.pop("dhash_threshold", 10)

        ctx = DetectorContext(
            assessment_id=assess_id,
            asset_id=asset_id,
            conn=self._conn,
            phash_threshold=phash_threshold,
            dhash_threshold=dhash_threshold,
        )
        for k, v in context_extras.items():
            setattr(ctx, k, v)

        # Emit DETECTOR_STARTED audit event (best-effort)
        try:
            self._audit_svc.emit_event(
                AuditEventType.DETECTOR_STARTED,
                payload={
                    "detector_id":      meta.detector_id,
                    "detector_version": meta.version,
                    "asset_id":         asset_id,
                },
                assessment_id=assess_id,
            )
        except Exception as exc:
            log.warning("Failed to emit DETECTOR_STARTED: %s", exc)

        # Execute via existing run_detector() (handles can_run + persist)
        try:
            output = run_detector(detector, ctx, self._conn)
        except Exception as exc:
            log.exception("Unexpected error running detector %s", meta.detector_id)
            output = DetectorOutput(
                status=DetectorStatus.FAILED,
                error=str(exc),
            )
            output.finalize()

        # Emit DETECTOR_COMPLETE audit event (best-effort)
        try:
            self._audit_svc.record_detector_complete(
                assessment_id=assess_id,
                asset_id=asset_id,
                detector_id=meta.detector_id,
                detector_version=meta.version,
                status=output.status.value,
                findings_count=len(output.findings),
                evidence_count=len(output.evidence),
                duration_ms=None,
                result_id="",
            )
        except Exception as exc:
            log.warning("Failed to emit DETECTOR_COMPLETE: %s", exc)

        # Determine if this is a coverage gap
        ran = output.status.value not in _SKIP_STATUSES
        gap: CoverageGapRecord | None = None

        if not ran:
            # Applicable detector could not run -> CoverageGap
            reason_map = {
                DetectorStatus.SKIPPED.value:        "detector_skipped",
                DetectorStatus.UNAVAILABLE.value:    "detector_unavailable",
                DetectorStatus.NOT_APPLICABLE.value: "not_applicable",
            }
            reason = reason_map.get(output.status.value, "detector_could_not_run")
            gap = self._make_gap(meta, reason, output.error or reason)

        record = DetectorRunRecord(
            detector_id=meta.detector_id,
            detector_name=meta.name,
            asset_id=asset_id,
            applicable=True,
            ran=ran,
            status=output.status.value,
            risk_level=output.risk_level.value,
            confidence_level=output.confidence_level.value,
            findings_count=len(output.findings),
            evidence_count=len(output.evidence),
            error=output.error,
            coverage_gap=gap,
        )

        return record, output

    @staticmethod
    def _make_gap(meta: Any, reason: str, detail: str) -> CoverageGapRecord:
        """Build a CoverageGapRecord for a detector that could not run."""
        _templates: dict[str, dict[str, str]] = {
            "data.integrity.di01_duplicates": {
                "required_capability": "dataset with ingested samples and fingerprints",
                "impact":              "duplicate_flooding_not_assessed",
                "recommended_action":  "provide a dataset and run ingestion before assessment",
            },
            "data.integrity.di02_label_integrity": {
                "required_capability": "dataset with annotated class labels (>= 2 labeled samples)",
                "impact":              "label_flipping_and_mislabelling_not_assessed",
                "recommended_action":  "provide a dataset with annotations (COCO format or label metadata) to evaluate label integrity",
            },
            "data.integrity.di03_trigger_anomaly": {
                "required_capability": "dataset with >= 3 image samples for recurring spatial patch analysis",
                "impact":              "trigger_injection_and_backdoor_patterns_not_assessed",
                "recommended_action":  "provide at least 3 samples to evaluate spatial trigger anomalies",
            },
            "data.integrity.di04_ood_distribution": {
                "required_capability": "dataset with >= 5 image samples for statistical distribution analysis",
                "impact":              "out_of_distribution_and_anomalous_samples_not_assessed",
                "recommended_action":  "provide at least 5 samples to establish distribution baseline",
            },
            "data.integrity.di05_contributor_risk": {
                "required_capability": "dataset with contributor/source attribution metadata on samples",
                "impact":              "contributor_source_risk_not_assessed",
                "recommended_action":  "include contributor/source attribution in dataset metadata or directory structure",
            },
            "model.integrity.mi01_fingerprint": {
                "required_capability": "compatible model file (.onnx/.pt/.pth/.ts) and model_path in request",
                "impact":              "model_integrity_not_assessed",
                "recommended_action":  "provide a compatible model file (ONNX preferred for full analysis)",
            },
            "model.integrity.mi02_parameter_stats": {
                "required_capability": "compatible model file (.onnx/.pt/.pth/.ts) with inspectable parameter tensors",
                "impact":              "parameter_statistics_and_weight_integrity_not_assessed",
                "recommended_action":  "provide a compatible model file to inspect parameter distributions and corruption",
            },
            "model.integrity.mi03_activation_stats": {
                "required_capability": "executable model graph (.onnx or .ts) for intermediate activation tracing",
                "impact":              "internal_representation_and_activation_health_not_assessed",
                "recommended_action":  "provide an executable ONNX or TorchScript model to evaluate activation health",
            },
            "model.integrity.mi04_reference_comparison": {
                "required_capability": "baseline reference model file or stored reference fingerprint profile",
                "impact":              "reference_model_comparison_and_drift_not_assessed",
                "recommended_action":  "supply a reference model artifact or reference fingerprint for comparative battery",
            },
            "model.integrity.mi05_trigger_anomaly": {
                "required_capability": "executable model (.onnx or .ts) for behavioral perturbation testing",
                "impact":              "trigger_sensitivity_and_backdoor_convergence_not_assessed",
                "recommended_action":  "provide an executable ONNX or TorchScript model to test candidate trigger perturbations",
            },
            "inference.provenance.pi01_integrity": {
                "required_capability": "signed ProvenanceManifest and Ed25519 public key",
                "impact":              "inference_provenance_not_verified",
                "recommended_action":  "provide a signed manifest and the corresponding verification key",
            },
        }
        tmpl = _templates.get(meta.detector_id, {})
        return CoverageGapRecord(
            detector_id=meta.detector_id,
            detector_name=meta.name,
            reason=reason,
            required_capability=tmpl.get("required_capability", "unknown"),
            observed_capability=detail,
            impact=tmpl.get("impact", "unknown_impact"),
            recommended_action=tmpl.get("recommended_action", "contact support"),
        )

    # ------------------------------------------------------------------
    # Private -- helpers
    # ------------------------------------------------------------------

    def _failed_result(
        self,
        request: AssessmentRequest,
        started_at: datetime,
        error: str,
    ) -> AssessmentResult:
        """Build a failed AssessmentResult without requiring a DB connection."""
        return AssessmentResult(
            assessment_id=request.assessment_id,
            title=request.title,
            status=AssessmentState.FAILED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            assets_analyzed=[],
            detectors_executed=[],
            detectors_skipped=[],
            findings_count=0,
            evidence_count=0,
            overall_risk=RiskLevel.NONE,
            risk_qualitative="Assessment failed before analysis. Risk cannot be determined.",
            overall_confidence=ConfidenceLevel.LOW,
            confidence_qualifier="Assessment failed -- no evidence gathered.",
            coverage_fraction=0.0,
            coverage_gaps=[],
            detector_runs=[],
            limitations=[f"Assessment failed before detectors could run. Error: {error}"],
            audit_chain_valid=None,
            error=error,
        )


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def run_assessment(
    request: AssessmentRequest,
    conn: sqlite3.Connection,
) -> AssessmentResult:
    """
    Module-level convenience wrapper around AssessmentService.run_assessment().

    Equivalent to:
        service = AssessmentService(conn)
        return service.run_assessment(request)
    """
    return AssessmentService(conn).run_assessment(request)


# ---------------------------------------------------------------------------
# Private module-level utilities
# ---------------------------------------------------------------------------

def _hash_file(path: Path) -> str:
    """SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _deterministic_id(sha256: str, assess_id: str, kind: str) -> str:
    """
    Generate a deterministic asset_id from content hash + context.

    Same SHA-256 + assessment + kind always produces the same asset_id,
    ensuring re-ingesting the same artifact is idempotent within one assessment.
    """
    seed = f"{sha256}:{assess_id}:{kind}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, seed))
