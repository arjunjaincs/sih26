"""
PI-01: Inference Provenance Integrity Detector.

Detector ID  : inference.provenance.pi01_integrity
Version      : 1.0.0
Category     : INFERENCE_PROVENANCE

What this detector does
-----------------------
Verifies the cryptographic integrity of a signed ProvenanceManifest and
its bound artefacts (input, model, output).

Verification pipeline:
  1. Ed25519 signature over the manifest's canonical form
  2. Input binding  — supplied input bytes hash == manifest.input_sha256
  3. Model binding  — supplied model SHA-256 == manifest.model_sha256
  4. Output binding — supplied output bytes hash == manifest.output_sha256
  5. Replay / consistency detection

Finding subcategories:
  "signature_invalid"      — Ed25519 verification failed
  "input_mismatch"         — input hash does not match manifest
  "model_mismatch"         — model hash does not match manifest
  "output_mismatch"        — output hash does not match manifest
  "replay_detected"        — nonce reuse, duplicate manifest, or sequence anomaly
  "coverage_gap"           — binding data not supplied; cannot fully verify
  "provenance_valid"       — INFO: all supplied checks passed

Risk / Confidence semantics (ADR-003)
--------------------------------------
Evidence quality drives confidence; observation drives risk.
They are computed independently.

  Observation                         Risk     Confidence
  ──────────────────────────────────  ───────  ──────────
  Valid sig + all bindings match       NONE     HIGH
  Valid sig + some bindings missing    NONE     MODERATE
  Invalid signature                    HIGH     HIGH
  Input / output / model mismatch      HIGH     HIGH
  Replay / sequence anomaly            MEDIUM   HIGH
  Manifest unsigned                    → can_run() returns False

Findings never assert "malicious", "backdoor", or "attack" automatically.
Cryptographic failures are evidence of integrity differences; human review
is required to determine intent.

Context
-------
Detectors receive a DetectorContext with a .pi01 attribute of type PI01Context.
The runner (run_detector) persists findings, evidence, and DetectorResult.
This detector does NOT write to the database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from backend.detectors.base import (
    CanRunResult,
    DetectorContext,
    DetectorMetadata,
    DetectorOutput,
)
from backend.domain.entities import Evidence, Finding, ProvenanceManifest
from backend.domain.enums import (
    AssetType,
    ConfidenceLevel,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    RiskLevel,
    Severity,
)
from backend.provenance.replay import ReplayAnomaly, detect_replay
from backend.provenance.signing import (
    VerificationCheck,
    VerificationResult,
    verify_manifest,
)

log = logging.getLogger(__name__)

_METADATA = DetectorMetadata(
    detector_id="inference.provenance.pi01_integrity",
    version="1.0.0",
    name="PI-01: Inference Provenance Integrity",
    description=(
        "Verifies the cryptographic integrity of a signed ProvenanceManifest. "
        "Checks the Ed25519 signature, and optionally verifies that the supplied "
        "input, model, and output artefacts match the hashes bound in the manifest. "
        "Detects replay/nonce reuse and sequence inconsistencies."
    ),
    applicable_asset_types=frozenset({AssetType.INFERENCE_BUNDLE.value}),
)


# ---------------------------------------------------------------------------
# PI-01 Context
# ---------------------------------------------------------------------------

@dataclass
class PI01Context:
    """
    Additional PI-01 context attached to DetectorContext.pi01.

    manifest : ProvenanceManifest
        The signed manifest to verify. Must have digest and signature set.
    public_key : Ed25519PublicKey
        Key used to verify the signature. Must be the public half of the key
        that was used to sign the manifest.
    actual_input_bytes : bytes | None
        The raw input data (e.g. image bytes) that was fed to the model.
        If None, input binding verification is skipped (coverage gap recorded).
    actual_output_bytes : bytes | None
        The canonical output bytes (e.g. JSON-encoded predictions).
        If None, output binding verification is skipped (coverage gap recorded).
    actual_model_sha256 : str | None
        The SHA-256 hex digest of the model file used for inference.
        If None, model binding verification is skipped (coverage gap recorded).
    known_manifests : list[ProvenanceManifest]
        Previously accepted manifests for replay detection.
        If empty, replay detection is skipped (no anomalies claimed).
    """
    manifest: ProvenanceManifest
    public_key: Ed25519PublicKey
    actual_input_bytes: bytes | None = None
    actual_output_bytes: bytes | None = None
    actual_model_sha256: str | None = None
    known_manifests: list[ProvenanceManifest] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Evidence helpers
# ---------------------------------------------------------------------------

def _make_check_evidence(
    check: VerificationCheck,
    manifest_id: str,
    finding_id: str,
    detector_id: str,
) -> Evidence:
    """Build an Evidence record from a VerificationCheck."""
    ev_type = EvidenceType.HASH_MATCH if check.passed else EvidenceType.HASH_MISMATCH
    return Evidence(
        finding_id=finding_id,
        detector_id=detector_id,
        evidence_type=ev_type,
        description=check.description,
        data={
            "check": check.check_name,
            "manifest_id": manifest_id,
            "expected": check.expected,
            "observed": check.observed,
            "result": "PASS" if check.passed else "FAIL",
            "detector_version": _METADATA.version,
        },
    )


def _make_replay_evidence(
    anomaly: ReplayAnomaly,
    finding_id: str,
    detector_id: str,
) -> Evidence:
    """Build an Evidence record from a ReplayAnomaly."""
    return Evidence(
        finding_id=finding_id,
        detector_id=detector_id,
        evidence_type=EvidenceType.ANOMALY,
        description=anomaly.description,
        data={
            "check": "replay_detection",
            "anomaly_type": anomaly.anomaly_type,
            "candidate_manifest_id": anomaly.candidate_manifest_id,
            "conflicting_manifest_id": anomaly.conflicting_manifest_id,
            **anomaly.evidence,
            "result": "ANOMALY",
            "detector_version": _METADATA.version,
        },
    )


# ---------------------------------------------------------------------------
# Risk / Confidence derivation (ADR-003)
# ---------------------------------------------------------------------------

def _derive_risk_confidence(
    verification: VerificationResult,
    replay_anomalies: list[ReplayAnomaly],
    coverage_gaps: list[str],
) -> tuple[RiskLevel, ConfidenceLevel, str]:
    """
    Derive risk and confidence independently per ADR-003.

    Risk is driven by what was observed (cryptographic failures, mismatches).
    Confidence is driven by evidence completeness (how much was checked).
    They are NEVER combined into a single score.
    """
    failed = verification.failed_checks

    # --- Risk ---
    if not verification.valid:
        sig_failed = any(c.check_name == "signature" and not c.passed for c in failed)
        binding_failed = any(
            c.check_name in ("input_binding", "model_binding", "output_binding")
            and not c.passed
            for c in failed
        )
        if sig_failed or binding_failed:
            risk = RiskLevel.HIGH
        else:
            risk = RiskLevel.MEDIUM
    elif replay_anomalies:
        risk = RiskLevel.MEDIUM
    else:
        risk = RiskLevel.NONE

    # --- Confidence ---
    # Coverage gaps reduce confidence regardless of risk
    if coverage_gaps:
        # Some checks were not performed
        if len(coverage_gaps) >= 2:
            confidence = ConfidenceLevel.LOW
        else:
            confidence = ConfidenceLevel.MODERATE
    elif verification.error:
        # Verification encountered an unexpected error
        confidence = ConfidenceLevel.MODERATE
    elif not verification.valid:
        # Cryptographic failures are strong evidence → HIGH confidence
        confidence = ConfidenceLevel.HIGH
    elif replay_anomalies:
        confidence = ConfidenceLevel.HIGH
    else:
        confidence = ConfidenceLevel.HIGH

    # --- Qualifier ---
    if risk == RiskLevel.NONE and confidence == ConfidenceLevel.HIGH:
        qualifier = "All verification checks passed. Provenance is cryptographically valid."
    elif risk == RiskLevel.NONE and confidence != ConfidenceLevel.HIGH:
        qualifier = (
            f"Signature valid. Binding verification incomplete "
            f"({len(coverage_gaps)} gap(s): {', '.join(coverage_gaps)}). "
            f"Provenance cannot be fully asserted without all binding data."
        )
    elif risk == RiskLevel.MEDIUM:
        qualifier = "Replay or consistency anomalies detected. Human review required."
    else:
        n_failed = len(failed)
        qualifier = (
            f"{n_failed} verification check(s) FAILED. "
            f"The manifest may have been tampered with or artefacts substituted. "
            f"Analyst review required."
        )

    return risk, confidence, qualifier


# ---------------------------------------------------------------------------
# PI-01 Detector
# ---------------------------------------------------------------------------

class PI01ProvenanceIntegrityDetector:
    """
    PI-01: Inference Provenance Integrity Detector.

    Implements the Detector protocol (ADR-004, structural subtyping).
    Does NOT write to the database — that is the runner's responsibility.
    """

    @property
    def metadata(self) -> DetectorMetadata:
        return _METADATA

    def can_run(self, context: DetectorContext) -> CanRunResult:
        pi01 = getattr(context, "pi01", None)
        if pi01 is None:
            return CanRunResult(
                ok=False,
                reason="PI-01 requires context.pi01 (PI01Context) to be set.",
            )

        manifest: ProvenanceManifest = pi01.manifest
        if manifest.digest is None or manifest.signature is None:
            return CanRunResult(
                ok=False,
                reason=(
                    f"Manifest {manifest.manifest_id!r} is unsigned "
                    f"(digest={manifest.digest!r}, signature={manifest.signature!r}). "
                    f"Sign the manifest with sign_manifest() before running PI-01."
                ),
            )

        return CanRunResult(ok=True)

    def run(self, context: DetectorContext) -> DetectorOutput:
        """
        Run the provenance integrity verification pipeline.

        Does NOT persist. Caller uses run_detector() for persistence.
        """
        output = DetectorOutput()
        did = _METADATA.detector_id
        pi01: PI01Context = context.pi01  # type: ignore[attr-defined]
        manifest = pi01.manifest

        # -----------------------------------------------------------------------
        # 1. Cryptographic verification (signature + bindings)
        # -----------------------------------------------------------------------
        try:
            verification = verify_manifest(
                manifest,
                pi01.public_key,
                actual_input_bytes=pi01.actual_input_bytes,
                actual_output_bytes=pi01.actual_output_bytes,
                actual_model_sha256=pi01.actual_model_sha256,
            )
        except Exception as exc:
            log.exception("PI-01 verification raised unexpected exception")
            output.status = DetectorStatus.FAILED
            output.error = f"Verification raised unexpected exception: {exc}"
            return output.finalize()

        # -----------------------------------------------------------------------
        # 2. Replay detection
        # -----------------------------------------------------------------------
        replay_anomalies: list[ReplayAnomaly] = []
        if pi01.known_manifests:
            try:
                replay_anomalies = detect_replay(manifest, pi01.known_manifests)
            except Exception as exc:
                log.warning("PI-01 replay detection failed: %s", exc)

        # -----------------------------------------------------------------------
        # 3. Determine coverage gaps
        # -----------------------------------------------------------------------
        coverage_gaps: list[str] = []
        if pi01.actual_input_bytes is None:
            coverage_gaps.append("input_binding")
        if pi01.actual_model_sha256 is None:
            coverage_gaps.append("model_binding")
        if pi01.actual_output_bytes is None:
            coverage_gaps.append("output_binding")

        # -----------------------------------------------------------------------
        # 4. Derive risk and confidence (ADR-003)
        # -----------------------------------------------------------------------
        risk, confidence, qualifier = _derive_risk_confidence(
            verification, replay_anomalies, coverage_gaps
        )
        output.risk_level = risk
        output.confidence_level = confidence

        # -----------------------------------------------------------------------
        # 5. Build findings and evidence
        # -----------------------------------------------------------------------

        # --- Signature finding ---
        sig_check = next(
            (c for c in verification.checks if c.check_name == "signature"), None
        )
        if sig_check and not sig_check.passed:
            finding = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.INFERENCE_PROVENANCE,
                subcategory="signature_invalid",
                severity=Severity.HIGH,
                title=f"Invalid Ed25519 signature on manifest {manifest.manifest_id[:8]}…",
                description=(
                    f"The Ed25519 signature on provenance manifest {manifest.manifest_id!r} "
                    f"failed verification. The manifest may have been tampered with after "
                    f"signing, or the wrong public key was used for verification."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=[
                    "Signature failure does not by itself identify the attacker or method.",
                    "May indicate key mismatch rather than tampering.",
                ],
                recommended_disposition=(
                    "Verify that the correct public key is being used. "
                    "If the key is correct, treat the manifest as compromised and "
                    "do not trust the inference result."
                ),
            )
            output.findings.append(finding)
            output.evidence.append(
                _make_check_evidence(sig_check, manifest.manifest_id, finding.finding_id, did)
            )

        # --- Per-binding findings ---
        _binding_meta = {
            "input_binding":  ("input_mismatch",  Severity.HIGH,
                               "Input hash mismatch on manifest"),
            "model_binding":  ("model_mismatch",  Severity.HIGH,
                               "Model identity mismatch on manifest"),
            "output_binding": ("output_mismatch", Severity.HIGH,
                               "Output hash mismatch on manifest"),
        }
        for check in verification.checks:
            if check.check_name in _binding_meta and not check.passed:
                subcat, sev, title_prefix = _binding_meta[check.check_name]
                finding = Finding(
                    assessment_id=context.assessment_id,
                    asset_id=context.asset_id,
                    category=FindingCategory.INFERENCE_PROVENANCE,
                    subcategory=subcat,
                    severity=sev,
                    title=f"{title_prefix} {manifest.manifest_id[:8]}…",
                    description=check.description,
                    detection_method=_METADATA.name,
                    detector_id=did,
                    limitations=[
                        "Hash mismatch does not prove malicious substitution without "
                        "further investigation.",
                        "May indicate a preprocessing or serialization inconsistency.",
                    ],
                    recommended_disposition=(
                        "Compare the expected hash in the manifest against the "
                        "actual artefact. Verify the artefact has not been modified. "
                        "If unexplained, do not trust the inference result."
                    ),
                )
                output.findings.append(finding)
                output.evidence.append(
                    _make_check_evidence(
                        check, manifest.manifest_id, finding.finding_id, did
                    )
                )

        # --- Replay findings ---
        for anomaly in replay_anomalies:
            sev = Severity.HIGH if anomaly.anomaly_type in (
                "duplicate_nonce", "duplicate_manifest_id"
            ) else Severity.MEDIUM

            finding = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.INFERENCE_PROVENANCE,
                subcategory="replay_detected",
                severity=sev,
                title=f"Provenance replay anomaly: {anomaly.anomaly_type}",
                description=anomaly.description,
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=[
                    "Replay detection requires complete known_manifests history.",
                    "An attacker generating a fresh nonce for a replayed event "
                    "will not be detected by nonce comparison alone.",
                    "Cross-assessment replay is not detected.",
                ],
                recommended_disposition=(
                    "Investigate the event sequence. Confirm that all expected "
                    "inference events are present and in correct order. "
                    "Treat missing or duplicated events as potential tampering."
                ),
            )
            output.findings.append(finding)
            output.evidence.append(
                _make_replay_evidence(anomaly, finding.finding_id, did)
            )

        # --- Coverage gap finding ---
        if coverage_gaps:
            finding = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.INFERENCE_PROVENANCE,
                subcategory="coverage_gap",
                severity=Severity.INFO,
                title=(
                    f"PI-01 coverage gap: {len(coverage_gaps)} binding(s) "
                    f"not verified for manifest {manifest.manifest_id[:8]}…"
                ),
                description=(
                    f"The following bindings could not be verified because the "
                    f"actual artefact data was not supplied: {', '.join(coverage_gaps)}. "
                    f"A valid signature proves the manifest has not been tampered with, "
                    f"but does not prove that the correct artefacts were used."
                ),
                detection_method=_METADATA.name,
                detector_id=did,
                limitations=[
                    "Coverage gap does not mean the provenance is invalid.",
                    "It means binding verification was incomplete.",
                ],
            )
            output.findings.append(finding)
            ev = Evidence(
                finding_id=finding.finding_id,
                detector_id=did,
                evidence_type=EvidenceType.MEASUREMENT,
                description="Coverage gap in provenance binding verification.",
                data={
                    "check": "coverage",
                    "manifest_id": manifest.manifest_id,
                    "unverified_bindings": coverage_gaps,
                    "result": "COVERAGE_GAP",
                    "detector_version": _METADATA.version,
                },
            )
            output.evidence.append(ev)

        # --- Valid provenance INFO finding ---
        # Always record whether signature is valid, even if no problems found.
        if sig_check and sig_check.passed:
            passed_binding_names = [
                c.check_name for c in verification.passed_checks
                if c.check_name != "signature"
            ]
            info_title = (
                f"Provenance valid: manifest {manifest.manifest_id[:8]}…"
                + (f" ({len(passed_binding_names)} binding(s) verified)" if passed_binding_names else "")
            )
            finding = Finding(
                assessment_id=context.assessment_id,
                asset_id=context.asset_id,
                category=FindingCategory.INFERENCE_PROVENANCE,
                subcategory="provenance_valid",
                severity=Severity.INFO,
                title=info_title,
                description=(
                    f"Ed25519 signature verified. {qualifier}"
                ),
                detection_method=_METADATA.name,
                detector_id=did,
            )
            output.findings.append(finding)
            # Evidence for each passed check
            for check in verification.passed_checks:
                output.evidence.append(
                    _make_check_evidence(
                        check, manifest.manifest_id, finding.finding_id, did
                    )
                )

        # -----------------------------------------------------------------------
        # 6. Final status
        # -----------------------------------------------------------------------
        if not verification.valid:
            output.status = DetectorStatus.SUCCESS  # Ran successfully; found problems
        elif coverage_gaps:
            output.status = DetectorStatus.PARTIAL
        else:
            output.status = DetectorStatus.SUCCESS

        log.info(
            "PI-01 complete: manifest=%s risk=%s confidence=%s "
            "sig_valid=%s replay_anomalies=%d coverage_gaps=%s",
            manifest.manifest_id[:8],
            risk.value, confidence.value,
            sig_check.passed if sig_check else "N/A",
            len(replay_anomalies),
            coverage_gaps,
        )

        return output.finalize()
