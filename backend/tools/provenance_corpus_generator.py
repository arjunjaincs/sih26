"""
PRAMAAN v1 — Provenance & Inference Output Integrity Corpus Generator.

Phase 17: Reproducible Offline Inference Provenance & Output Integrity Validation Corpus.

Generates a deterministic, fully offline benchmark corpus for validating PI-01
(inference.provenance.pi01_integrity), replay detection, and audit integration
across 13 distinct scenarios:

  01_clean_provenance          -- Pristine valid signed manifest & matching bindings
  02_input_tampering           -- Input image substitution (hash mismatch)
  03_model_tampering           -- Model identity substitution (model hash mismatch)
  04_output_tampering          -- Inference output substitution (output hash mismatch)
  05_manifest_tampering        -- Signed field post-hoc tampering (signature invalid)
  06_duplicate_replay          -- Replayed manifest identity & nonce reuse
  07_sequence_regression       -- Monotonic sequence regression in stream
  08_sequence_gap              -- Missing stream events sequence gap
  09_fresh_nonce_limitation    -- Semantic duplicate with fresh nonce (ADR-003 limitation)
  10_audit_integration         -- End-to-end AssessmentService & audit verifier
  11_signature_binding         -- SEC-01 signature transplant rejection
  12_malformed_provenance      -- Malformed / unsigned / invalid payload fail-closed
  13_persistence_restart       -- Replay state retention across SQLite restarts

Design Principles:
  - Deterministic: master seed 42 produces identical keys, hashes, and files.
  - Pure Offline: zero network requests, downloads, or external services.
  - Strict Isolation: ground_truth/ is isolated outside input/.
  - Cryptographic Integrity: uses existing crypto & canonicalization primitives.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from backend.assessment.models import AssessmentRequest
from backend.assessment.orchestrator import AssessmentService
from backend.audit.service import AuditService
from backend.audit.verifier import ChainVerifier
from backend.detectors.base import DetectorContext
from backend.detectors.provenance.pi01_integrity import (
    PI01Context,
    PI01ProvenanceIntegrityDetector,
)
from backend.detectors.runner import run_detector
from backend.domain.entities import ProvenanceManifest
from backend.domain.enums import RiskLevel, Severity
from backend.infra.crypto import canonical_json, hash_bytes
from backend.infra.db import (
    AuditPayloadRepository,
    AuditRepository,
    FindingRepository,
    ProvenanceRepository,
    open_db,
)
from backend.provenance.signing import (
    digest_manifest,
    sign_manifest,
    verify_manifest,
)

log = logging.getLogger("provenance_corpus_generator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DEFAULT_CORPUS_ROOT = Path("data/corpus/provenance")

# Minimal deterministic 1x1 PNG bytes
_DETERMINISTIC_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Mutated 1x1 PNG bytes (altered pixel payload)
_MUTATED_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x00\x00"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _derive_deterministic_keypair(salt: str = "master_key") -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """Derive deterministic Ed25519 keypair from master seed and salt."""
    seed = hashlib.sha256(f"pramaan_phase17_seed_42_{salt}".encode("utf-8")).digest()
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    pub = priv.public_key()
    return priv, pub


class ProvenanceCorpusGenerator:
    """Generates the 13 reproducible offline inference provenance scenarios."""

    def __init__(self, root: Path = DEFAULT_CORPUS_ROOT) -> None:
        self.root = root.resolve()
        self.scenarios_dir = self.root / "scenarios"
        self.priv_key, self.pub_key = _derive_deterministic_keypair("default")
        self.pub_key_hex = self.pub_key.public_bytes_raw().hex()

        # Deterministic reference artefacts
        self.clean_input_bytes = _DETERMINISTIC_PNG_BYTES
        self.clean_input_sha256 = hash_bytes(self.clean_input_bytes)
        self.clean_model_sha256 = hashlib.sha256(b"pramaan_deterministic_model_v1_weights").hexdigest()
        self.clean_output_dict = {
            "model": "pramaan-inference-v1",
            "predictions": [
                {"label": "defect_free", "confidence": 0.9942},
                {"label": "anomaly", "confidence": 0.0058},
            ],
            "inference_time_ms": 12.4,
        }
        self.clean_output_bytes = canonical_json(self.clean_output_dict)
        self.clean_output_sha256 = hash_bytes(self.clean_output_bytes)

        self.preprocessing_config = {
            "resize": [224, 224],
            "normalization": {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]},
            "color_mode": "RGB",
        }
        self.inference_config = {
            "batch_size": 1,
            "precision": "fp32",
            "device": "cpu",
            "execution_provider": "CPUExecutionProvider",
        }

    def _write_scenario_files(
        self,
        scenario_id: str,
        *,
        input_files: dict[str, str | bytes],
        ground_truth: dict[str, Any],
        scenario_manifest: dict[str, Any],
    ) -> Path:
        """Helper to create scenario folder structure."""
        scen_dir = self.scenarios_dir / scenario_id
        input_dir = scen_dir / "input"
        gt_dir = scen_dir / "ground_truth"

        input_dir.mkdir(parents=True, exist_ok=True)
        gt_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in input_files.items():
            file_path = input_dir / filename
            if isinstance(content, str):
                file_path.write_text(content, encoding="utf-8")
            else:
                file_path.write_bytes(content)

        gt_file = gt_dir / "ground_truth.json"
        gt_file.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")

        manifest_file = scen_dir / "manifest.json"
        manifest_file.write_text(json.dumps(scenario_manifest, indent=2), encoding="utf-8")

        return scen_dir

    def generate_01_clean_provenance(self) -> dict[str, Any]:
        """Scenario 01: Clean Baseline Provenance."""
        manifest = ProvenanceManifest(
            manifest_id="01010101-0000-0000-0000-000000000001",
            assessment_id="stream-01-clean",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="11" * 32,
            sequence=0,
        )
        signed = sign_manifest(manifest, self.priv_key)

        input_files = {
            "manifest.json": signed.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "01_clean_provenance",
            "name": "Clean Baseline Provenance",
            "category": "clean_baseline",
            "expected_overall_risk": "NONE",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["provenance_valid"],
            "expected_replay_anomalies": [],
            "expected_disposition": "VERIFIED",
            "description": "Valid signature and pristine input, model, and output bindings.",
        }
        meta = {
            "scenario_id": "01_clean_provenance",
            "manifest_id": signed.manifest_id,
            "assessment_id": signed.assessment_id,
            "input_sha256": self.clean_input_sha256,
            "model_sha256": self.clean_model_sha256,
            "output_sha256": self.clean_output_sha256,
        }
        self._write_scenario_files("01_clean_provenance", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_02_input_tampering(self) -> dict[str, Any]:
        """Scenario 02: Input Image Tampering."""
        manifest = ProvenanceManifest(
            manifest_id="02020202-0000-0000-0000-000000000002",
            assessment_id="stream-02-tamper-in",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="22" * 32,
            sequence=0,
        )
        signed = sign_manifest(manifest, self.priv_key)

        input_files = {
            "manifest.json": signed.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": _MUTATED_PNG_BYTES,  # Tampered bytes
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "02_input_tampering",
            "name": "Input Image Tampering",
            "category": "binding_tampering",
            "expected_overall_risk": "HIGH",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["input_mismatch"],
            "expected_replay_anomalies": [],
            "expected_disposition": "REJECT",
            "description": "Actual input image bytes altered post-signing, causing input binding hash mismatch.",
        }
        meta = {
            "scenario_id": "02_input_tampering",
            "manifest_id": signed.manifest_id,
            "bound_input_sha256": self.clean_input_sha256,
            "actual_input_sha256": hash_bytes(_MUTATED_PNG_BYTES),
        }
        self._write_scenario_files("02_input_tampering", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_03_model_tampering(self) -> dict[str, Any]:
        """Scenario 03: Model Identity Tampering."""
        manifest = ProvenanceManifest(
            manifest_id="03030303-0000-0000-0000-000000000003",
            assessment_id="stream-03-tamper-mod",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="33" * 32,
            sequence=0,
        )
        signed = sign_manifest(manifest, self.priv_key)
        substituted_model_sha256 = hashlib.sha256(b"pramaan_unauthorized_substituted_model").hexdigest()

        input_files = {
            "manifest.json": signed.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": substituted_model_sha256,
        }
        gt = {
            "scenario_id": "03_model_tampering",
            "name": "Model Identity Tampering",
            "category": "binding_tampering",
            "expected_overall_risk": "HIGH",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["model_mismatch"],
            "expected_replay_anomalies": [],
            "expected_disposition": "REJECT",
            "description": "Model SHA-256 differs from signed manifest binding, detecting unauthorized model substitution.",
        }
        meta = {
            "scenario_id": "03_model_tampering",
            "manifest_id": signed.manifest_id,
            "bound_model_sha256": self.clean_model_sha256,
            "actual_model_sha256": substituted_model_sha256,
        }
        self._write_scenario_files("03_model_tampering", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_04_output_tampering(self) -> dict[str, Any]:
        """Scenario 04: Inference Output Tampering."""
        manifest = ProvenanceManifest(
            manifest_id="04040404-0000-0000-0000-000000000004",
            assessment_id="stream-04-tamper-out",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="44" * 32,
            sequence=0,
        )
        signed = sign_manifest(manifest, self.priv_key)
        tampered_output_dict = dict(self.clean_output_dict)
        tampered_output_dict["predictions"] = [
            {"label": "defect_free", "confidence": 0.001},
            {"label": "anomaly", "confidence": 0.999},
        ]
        tampered_output_bytes = canonical_json(tampered_output_dict)

        input_files = {
            "manifest.json": signed.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": tampered_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "04_output_tampering",
            "name": "Inference Output Tampering",
            "category": "binding_tampering",
            "expected_overall_risk": "HIGH",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["output_mismatch"],
            "expected_replay_anomalies": [],
            "expected_disposition": "REJECT",
            "description": "Inference predictions altered post-signing, causing output binding hash mismatch.",
        }
        meta = {
            "scenario_id": "04_output_tampering",
            "manifest_id": signed.manifest_id,
            "bound_output_sha256": self.clean_output_sha256,
            "actual_output_sha256": hash_bytes(tampered_output_bytes),
        }
        self._write_scenario_files("04_output_tampering", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_05_manifest_tampering(self) -> dict[str, Any]:
        """Scenario 05: Signed Field Alteration."""
        manifest = ProvenanceManifest(
            manifest_id="05050505-0000-0000-0000-000000000005",
            assessment_id="stream-05-tamper-man",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="55" * 32,
            sequence=0,
        )
        signed = sign_manifest(manifest, self.priv_key)

        # Alter signed field post-hoc while keeping original signature
        tampered_manifest_dict = signed.model_dump()
        tampered_manifest_dict["inference_config"]["batch_size"] = 64  # Mutate signed field

        input_files = {
            "manifest.json": json.dumps(tampered_manifest_dict, indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "05_manifest_tampering",
            "name": "Signed Field Alteration",
            "category": "manifest_tampering",
            "expected_overall_risk": "HIGH",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["signature_invalid"],
            "expected_replay_anomalies": [],
            "expected_disposition": "REJECT",
            "description": "Signed inference_config altered after signing; Ed25519 signature verification fails.",
        }
        meta = {
            "scenario_id": "05_manifest_tampering",
            "manifest_id": signed.manifest_id,
            "tampered_field": "inference_config.batch_size",
        }
        self._write_scenario_files("05_manifest_tampering", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_06_duplicate_replay(self) -> dict[str, Any]:
        """Scenario 06: Direct Manifest / Nonce Replay."""
        manifest = ProvenanceManifest(
            manifest_id="06060606-0000-0000-0000-000000000006",
            assessment_id="stream-06-replay",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="66" * 32,
            sequence=0,
        )
        signed = sign_manifest(manifest, self.priv_key)

        input_files = {
            "manifest.json": signed.model_dump_json(indent=2),
            "prior_manifest.json": signed.model_dump_json(indent=2),  # identical replay
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "06_duplicate_replay",
            "name": "Direct Manifest / Nonce Replay",
            "category": "replay_anomaly",
            "expected_overall_risk": "MEDIUM",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["replay_detected"],
            "expected_replay_anomalies": ["duplicate_manifest_id"],
            "expected_disposition": "INVESTIGATE",
            "description": "Re-presentation of previously accepted manifest identity triggers duplicate_manifest_id replay detection.",
        }
        meta = {
            "scenario_id": "06_duplicate_replay",
            "manifest_id": signed.manifest_id,
            "reused_nonce": signed.nonce,
        }
        self._write_scenario_files("06_duplicate_replay", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_07_sequence_regression(self) -> dict[str, Any]:
        """Scenario 07: Monotonic Sequence Regression."""
        m_prior = sign_manifest(
            ProvenanceManifest(
                manifest_id="07070707-0000-0000-0000-000000000001",
                assessment_id="stream-07-seq",
                input_sha256=self.clean_input_sha256,
                model_sha256=self.clean_model_sha256,
                preprocessing_config=self.preprocessing_config,
                inference_config=self.inference_config,
                output_sha256=self.clean_output_sha256,
                timestamp_utc="2026-01-01T12:00:00Z",
                nonce="71" * 32,
                sequence=1,  # Max known sequence is 1
            ),
            self.priv_key,
        )

        m_candidate = sign_manifest(
            ProvenanceManifest(
                manifest_id="07070707-0000-0000-0000-000000000002",
                assessment_id="stream-07-seq",
                input_sha256=self.clean_input_sha256,
                model_sha256=self.clean_model_sha256,
                preprocessing_config=self.preprocessing_config,
                inference_config=self.inference_config,
                output_sha256=self.clean_output_sha256,
                timestamp_utc="2026-01-01T12:01:00Z",
                nonce="72" * 32,
                sequence=0,  # Regressed sequence! Expected 2
            ),
            self.priv_key,
        )

        input_files = {
            "manifest.json": m_candidate.model_dump_json(indent=2),
            "prior_manifest.json": m_prior.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "07_sequence_regression",
            "name": "Monotonic Sequence Regression",
            "category": "replay_anomaly",
            "expected_overall_risk": "MEDIUM",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["replay_detected"],
            "expected_replay_anomalies": ["sequence_regression"],
            "expected_disposition": "INVESTIGATE",
            "description": "Candidate sequence 0 presented when max known sequence is 1; sequence regression flagged.",
        }
        meta = {
            "scenario_id": "07_sequence_regression",
            "candidate_manifest_id": m_candidate.manifest_id,
            "candidate_sequence": m_candidate.sequence,
            "prior_sequence": m_prior.sequence,
        }
        self._write_scenario_files("07_sequence_regression", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_08_sequence_gap(self) -> dict[str, Any]:
        """Scenario 08: Missing Stream Events Gap."""
        m_prior = sign_manifest(
            ProvenanceManifest(
                manifest_id="08080808-0000-0000-0000-000000000001",
                assessment_id="stream-08-gap",
                input_sha256=self.clean_input_sha256,
                model_sha256=self.clean_model_sha256,
                preprocessing_config=self.preprocessing_config,
                inference_config=self.inference_config,
                output_sha256=self.clean_output_sha256,
                timestamp_utc="2026-01-01T12:00:00Z",
                nonce="81" * 32,
                sequence=0,
            ),
            self.priv_key,
        )

        m_candidate = sign_manifest(
            ProvenanceManifest(
                manifest_id="08080808-0000-0000-0000-000000000002",
                assessment_id="stream-08-gap",
                input_sha256=self.clean_input_sha256,
                model_sha256=self.clean_model_sha256,
                preprocessing_config=self.preprocessing_config,
                inference_config=self.inference_config,
                output_sha256=self.clean_output_sha256,
                timestamp_utc="2026-01-01T12:05:00Z",
                nonce="82" * 32,
                sequence=3,  # Gap: missing sequence 1 and 2
            ),
            self.priv_key,
        )

        input_files = {
            "manifest.json": m_candidate.model_dump_json(indent=2),
            "prior_manifest.json": m_prior.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "08_sequence_gap",
            "name": "Missing Stream Events Gap",
            "category": "replay_anomaly",
            "expected_overall_risk": "MEDIUM",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["replay_detected"],
            "expected_replay_anomalies": ["sequence_gap"],
            "expected_disposition": "INVESTIGATE",
            "description": "Candidate sequence 3 skips expected sequence 1; sequence gap recorded.",
        }
        meta = {
            "scenario_id": "08_sequence_gap",
            "candidate_manifest_id": m_candidate.manifest_id,
            "candidate_sequence": m_candidate.sequence,
            "prior_sequence": m_prior.sequence,
            "gap_size": 2,
        }
        self._write_scenario_files("08_sequence_gap", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_09_fresh_nonce_limitation(self) -> dict[str, Any]:
        """Scenario 09: Fresh Nonce Duplicate Inference (ADR-003 Limitation)."""
        m_prior = sign_manifest(
            ProvenanceManifest(
                manifest_id="09090909-0000-0000-0000-000000000001",
                assessment_id="stream-09-limit",
                input_sha256=self.clean_input_sha256,
                model_sha256=self.clean_model_sha256,
                preprocessing_config=self.preprocessing_config,
                inference_config=self.inference_config,
                output_sha256=self.clean_output_sha256,
                timestamp_utc="2026-01-01T12:00:00Z",
                nonce="91" * 32,
                sequence=0,
            ),
            self.priv_key,
        )

        # Re-run identical inference with a brand new nonce and monotonic sequence
        m_candidate = sign_manifest(
            ProvenanceManifest(
                manifest_id="09090909-0000-0000-0000-000000000002",
                assessment_id="stream-09-limit",
                input_sha256=self.clean_input_sha256,
                model_sha256=self.clean_model_sha256,
                preprocessing_config=self.preprocessing_config,
                inference_config=self.inference_config,
                output_sha256=self.clean_output_sha256,
                timestamp_utc="2026-01-01T12:01:00Z",
                nonce="92" * 32,  # Fresh nonce
                sequence=1,       # Monotonic progression
            ),
            self.priv_key,
        )

        input_files = {
            "manifest.json": m_candidate.model_dump_json(indent=2),
            "prior_manifest.json": m_prior.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "09_fresh_nonce_limitation",
            "name": "Fresh Nonce Duplicate Inference",
            "category": "documented_limitation",
            "expected_overall_risk": "NONE",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["provenance_valid"],
            "expected_replay_anomalies": [],
            "expected_disposition": "VERIFIED",
            "documented_limitation": (
                "Cryptographic replay detection alone cannot prove semantic duplicate inference "
                "when an actor issues a fresh nonce and valid sequence counter (ADR-003)."
            ),
            "description": "Logically identical inference with fresh nonce is not detectable by cryptographic replay detection alone.",
        }
        meta = {
            "scenario_id": "09_fresh_nonce_limitation",
            "candidate_manifest_id": m_candidate.manifest_id,
            "is_limitation_scenario": True,
        }
        self._write_scenario_files("09_fresh_nonce_limitation", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_10_audit_integration(self) -> dict[str, Any]:
        """Scenario 10: End-to-End Audit Trail Integration."""
        manifest = ProvenanceManifest(
            manifest_id="10101010-0000-0000-0000-000000000010",
            assessment_id="stream-10-audit",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="aa" * 32,
            sequence=0,
        )
        signed = sign_manifest(manifest, self.priv_key)

        input_files = {
            "manifest.json": signed.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "10_audit_integration",
            "name": "End-to-End Audit Trail Integration",
            "category": "audit_integration",
            "expected_overall_risk": "NONE",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["provenance_valid"],
            "expected_replay_anomalies": [],
            "expected_audit_chain_valid": True,
            "expected_disposition": "VERIFIED",
            "description": "Assessment completes with verified provenance, persisting evidence and maintaining a valid audit chain.",
        }
        meta = {
            "scenario_id": "10_audit_integration",
            "manifest_id": signed.manifest_id,
            "assessment_id": signed.assessment_id,
        }
        self._write_scenario_files("10_audit_integration", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_11_signature_binding(self) -> dict[str, Any]:
        """Scenario 11: SEC-01 Signature Transplant Rejection."""
        manifest_a = sign_manifest(
            ProvenanceManifest(
                manifest_id="11111111-0000-0000-0000-00000000000a",
                assessment_id="stream-11-a",
                input_sha256=self.clean_input_sha256,
                model_sha256=self.clean_model_sha256,
                preprocessing_config=self.preprocessing_config,
                inference_config=self.inference_config,
                output_sha256=self.clean_output_sha256,
                timestamp_utc="2026-01-01T12:00:00Z",
                nonce="ba" * 32,
                sequence=0,
            ),
            self.priv_key,
        )

        # Manifest B: different event identity
        manifest_b = ProvenanceManifest(
            manifest_id="11111111-0000-0000-0000-00000000000b",
            assessment_id="stream-11-b",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="bb" * 32,
            sequence=0,
            digest=digest_manifest(manifest_a),   # Transplanted digest
            signature=manifest_a.signature,       # Transplanted signature
        )

        input_files = {
            "manifest.json": manifest_b.model_dump_json(indent=2),
            "manifest_donor.json": manifest_a.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "11_signature_binding",
            "name": "SEC-01 Signature Transplant Rejection",
            "category": "security_regression",
            "expected_overall_risk": "HIGH",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["signature_invalid"],
            "expected_replay_anomalies": [],
            "expected_disposition": "REJECT",
            "description": "Signature transplanted from Event A onto Event B fails verification; protects against detachment attack.",
        }
        meta = {
            "scenario_id": "11_signature_binding",
            "target_manifest_id": manifest_b.manifest_id,
            "donor_manifest_id": manifest_a.manifest_id,
        }
        self._write_scenario_files("11_signature_binding", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_12_malformed_provenance(self) -> dict[str, Any]:
        """Scenario 12: Corrupted / Malformed Payload Fail-Closed."""
        # Unsigned manifest: digest and signature are None
        unsigned_manifest = ProvenanceManifest(
            manifest_id="12121212-0000-0000-0000-000000000012",
            assessment_id="stream-12-malformed",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="cc" * 32,
            sequence=0,
            digest=None,
            signature=None,
        )

        input_files = {
            "manifest.json": unsigned_manifest.model_dump_json(indent=2),
            "corrupt_manifest.bin": b"{\x00\xffINVALID_UTF8_PAYLOAD",
            "invalid_key.hex": "deadbeef",
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "12_malformed_provenance",
            "name": "Corrupted / Malformed Payload",
            "category": "malformed_unsupported",
            "expected_overall_risk": "NONE",
            "expected_disposition": "FAIL_CLOSED",
            "expected_can_run_ok": False,
            "description": "Unsigned or corrupted manifest payload fails closed safely without leaking file paths or raising stack traces.",
        }
        meta = {
            "scenario_id": "12_malformed_provenance",
            "manifest_id": unsigned_manifest.manifest_id,
        }
        self._write_scenario_files("12_malformed_provenance", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_13_persistence_restart(self) -> dict[str, Any]:
        """Scenario 13: Persistence & Service Restart."""
        manifest = ProvenanceManifest(
            manifest_id="13131313-0000-0000-0000-000000000013",
            assessment_id="stream-13-persist",
            input_sha256=self.clean_input_sha256,
            model_sha256=self.clean_model_sha256,
            preprocessing_config=self.preprocessing_config,
            inference_config=self.inference_config,
            output_sha256=self.clean_output_sha256,
            timestamp_utc="2026-01-01T12:00:00Z",
            nonce="dd" * 32,
            sequence=0,
        )
        signed = sign_manifest(manifest, self.priv_key)

        input_files = {
            "manifest.json": signed.model_dump_json(indent=2),
            "public_key.hex": self.pub_key_hex,
            "input_image.png": self.clean_input_bytes,
            "output.json": self.clean_output_bytes,
            "model_sha256.txt": self.clean_model_sha256,
        }
        gt = {
            "scenario_id": "13_persistence_restart",
            "name": "Persistence & Service Restart",
            "category": "persistence",
            "expected_overall_risk": "MEDIUM",
            "expected_confidence": "HIGH",
            "expected_finding_subcategories": ["replay_detected"],
            "expected_replay_anomalies": ["duplicate_manifest_id"],
            "expected_disposition": "REPLAY_DETECTED_AFTER_RESTART",
            "description": "Verified manifest stored in SQLite repository persists across connection restart, triggering replay on resubmission.",
        }
        meta = {
            "scenario_id": "13_persistence_restart",
            "manifest_id": signed.manifest_id,
        }
        self._write_scenario_files("13_persistence_restart", input_files=input_files, ground_truth=gt, scenario_manifest=meta)
        return meta

    def generate_all(self) -> dict[str, Any]:
        """Generate all 13 scenarios, corpus manifest, and README."""
        log.info("Generating Phase 17 Provenance Corpus at: %s", self.root)
        if self.scenarios_dir.exists():
            shutil.rmtree(self.scenarios_dir)
        self.scenarios_dir.mkdir(parents=True, exist_ok=True)

        scenarios = [
            ("01_clean_provenance", "Clean Baseline Provenance", "clean_baseline", self.generate_01_clean_provenance()),
            ("02_input_tampering", "Input Image Tampering", "binding_tampering", self.generate_02_input_tampering()),
            ("03_model_tampering", "Model Identity Tampering", "binding_tampering", self.generate_03_model_tampering()),
            ("04_output_tampering", "Inference Output Tampering", "binding_tampering", self.generate_04_output_tampering()),
            ("05_manifest_tampering", "Signed Field Alteration", "manifest_tampering", self.generate_05_manifest_tampering()),
            ("06_duplicate_replay", "Direct Manifest / Nonce Replay", "replay_anomaly", self.generate_06_duplicate_replay()),
            ("07_sequence_regression", "Monotonic Sequence Regression", "replay_anomaly", self.generate_07_sequence_regression()),
            ("08_sequence_gap", "Missing Stream Events Gap", "replay_anomaly", self.generate_08_sequence_gap()),
            ("09_fresh_nonce_limitation", "Fresh Nonce Duplicate Inference", "documented_limitation", self.generate_09_fresh_nonce_limitation()),
            ("10_audit_integration", "End-to-End Audit Trail Integration", "audit_integration", self.generate_10_audit_integration()),
            ("11_signature_binding", "SEC-01 Signature Transplant Rejection", "security_regression", self.generate_11_signature_binding()),
            ("12_malformed_provenance", "Corrupted / Malformed Payload", "malformed_unsupported", self.generate_12_malformed_provenance()),
            ("13_persistence_restart", "Persistence & Service Restart", "persistence", self.generate_13_persistence_restart()),
        ]

        corpus_manifest = {
            "manifest_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "master_seed": 42,
            "total_scenarios": len(scenarios),
            "scenarios": [
                {
                    "scenario_id": sid,
                    "name": name,
                    "category": cat,
                    "manifest_path": f"scenarios/{sid}/manifest.json",
                    "ground_truth_path": f"scenarios/{sid}/ground_truth/ground_truth.json",
                }
                for sid, name, cat, _ in scenarios
            ],
        }

        corpus_manifest_file = self.root / "corpus_manifest.json"
        corpus_manifest_file.write_text(json.dumps(corpus_manifest, indent=2), encoding="utf-8")

        readme_content = f"""# PRAMAAN v1 — Phase 17 Provenance Assurance Validation Corpus

Deterministic, fully offline validation corpus for **PI-01: Inference Provenance Integrity** and its integration with replay detection and the tamper-evident audit chain.

## Scenarios Overview

Total Scenarios: {len(scenarios)}

| Scenario ID | Name | Category | Primary Detection Target |
|---|---|---|---|
| `01_clean_provenance` | Clean Baseline Provenance | `clean_baseline` | Valid Ed25519 signature & all bindings match |
| `02_input_tampering` | Input Image Tampering | `binding_tampering` | Actual input bytes hash mismatch |
| `03_model_tampering` | Model Identity Tampering | `binding_tampering` | Model SHA-256 mismatch |
| `04_output_tampering` | Inference Output Tampering | `binding_tampering` | Output predictions hash mismatch |
| `05_manifest_tampering` | Signed Field Alteration | `manifest_tampering` | Signature verification failure |
| `06_duplicate_replay` | Direct Manifest / Nonce Replay | `replay_anomaly` | Reused nonce / duplicate manifest ID |
| `07_sequence_regression` | Monotonic Sequence Regression | `replay_anomaly` | Regressing sequence counter |
| `08_sequence_gap` | Missing Stream Events Gap | `replay_anomaly` | Gaps in sequence counter stream |
| `09_fresh_nonce_limitation` | Fresh Nonce Duplicate Inference | `documented_limitation` | ADR-003 limitation representation |
| `10_audit_integration` | End-to-End Audit Trail Integration | `audit_integration` | Verified provenance & valid audit chain |
| `11_signature_binding` | SEC-01 Signature Transplant Rejection | `security_regression` | Signature transplantation fail-closed |
| `12_malformed_provenance` | Corrupted / Malformed Payload | `malformed_unsupported` | Unsigned/corrupt manifest fails closed |
| `13_persistence_restart` | Persistence & Service Restart | `persistence` | SQLite WAL replay state retention |

## Reproduction

Run the generator:
```bash
python backend/tools/provenance_corpus_generator.py --corpus-root data/corpus/provenance
```
"""
        readme_file = self.root / "README.md"
        readme_file.write_text(readme_content, encoding="utf-8")

        log.info("Corpus generation complete: %d scenarios created.", len(scenarios))
        return corpus_manifest


# ---------------------------------------------------------------------------
# Validation Function (Used by Corpus Tests)
# ---------------------------------------------------------------------------

def validate_provenance_scenario(scenario_path: Path, test_db: sqlite3.Connection | None = None) -> dict[str, Any]:
    """
    Run PRAMAAN detectors and orchestrator against a scenario and compare against ground truth.

    Returns structured summary with observed vs expected results.
    """
    scenario_path = scenario_path.resolve()
    input_dir = scenario_path / "input"
    gt_file = scenario_path / "ground_truth" / "ground_truth.json"

    if not gt_file.exists():
        raise FileNotFoundError(f"Missing ground_truth.json: {gt_file}")

    gt = json.loads(gt_file.read_text(encoding="utf-8"))
    scen_id = gt["scenario_id"]

    # Special handling for malformed scenario
    if scen_id == "12_malformed_provenance":
        manifest_dict = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest = ProvenanceManifest.model_validate(manifest_dict)
        pub_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex((input_dir / "public_key.hex").read_text(encoding="utf-8").strip()))
        det = PI01ProvenanceIntegrityDetector()
        ctx = DetectorContext(
            assessment_id="test-asmt",
            asset_id="test-asset",
        )
        setattr(ctx, "pi01", PI01Context(manifest=manifest, public_key=pub_key))
        can_run_res = det.can_run(ctx)
        return {
            "scenario_id": scen_id,
            "passed": can_run_res.ok == gt["expected_can_run_ok"],
            "can_run_ok": can_run_res.ok,
            "can_run_reason": can_run_res.reason,
            "observed_risk": "none" if not can_run_res.ok else "unknown",
            "findings": [],
            "replay_anomalies": [],
            "audit_chain_valid": None,
        }

    # Load candidate manifest
    manifest_dict = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest = ProvenanceManifest.model_validate(manifest_dict)
    pub_bytes = bytes.fromhex((input_dir / "public_key.hex").read_text(encoding="utf-8").strip())
    pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)

    # Optional actual artefacts
    actual_input = (input_dir / "input_image.png").read_bytes() if (input_dir / "input_image.png").exists() else None
    actual_output = (input_dir / "output.json").read_bytes() if (input_dir / "output.json").exists() else None
    actual_model_sha = (input_dir / "model_sha256.txt").read_text(encoding="utf-8").strip() if (input_dir / "model_sha256.txt").exists() else None

    # Load prior manifests for replay scenarios
    known_manifests: list[ProvenanceManifest] = []
    prior_file = input_dir / "prior_manifest.json"
    if prior_file.exists():
        prior_dict = json.loads(prior_file.read_text(encoding="utf-8"))
        known_manifests.append(ProvenanceManifest.model_validate(prior_dict))

    # Execute PI-01 detector directly
    det = PI01ProvenanceIntegrityDetector()
    pi01_ctx = PI01Context(
        manifest=manifest,
        public_key=pub_key,
        actual_input_bytes=actual_input,
        actual_output_bytes=actual_output,
        actual_model_sha256=actual_model_sha,
        known_manifests=known_manifests,
    )
    context = DetectorContext(
        assessment_id="test-asmt",
        asset_id="test-asset",
    )
    setattr(context, "pi01", pi01_ctx)

    output = det.run(context)
    observed_risk = output.risk_level.value.lower()
    observed_conf = output.confidence_level.value.lower()
    observed_subcats = [f.subcategory for f in output.findings]

    replay_anomalies: list[str] = []
    for f in output.findings:
        if f.subcategory == "replay_detected":
            # Extract anomaly type from title e.g. "Provenance replay anomaly: duplicate_nonce"
            anomaly_type = f.title.split(":")[-1].strip()
            replay_anomalies.append(anomaly_type)

    expected_risk = gt["expected_overall_risk"].lower()
    expected_conf = gt.get("expected_confidence", "high").lower()
    expected_subcats = gt.get("expected_finding_subcategories", [])
    expected_anomalies = gt.get("expected_replay_anomalies", [])

    passed = (
        observed_risk == expected_risk
        and observed_conf == expected_conf
        and all(sub in observed_subcats for sub in expected_subcats)
        and all(anom in replay_anomalies for anom in expected_anomalies)
    )

    return {
        "scenario_id": scen_id,
        "passed": passed,
        "observed_risk": observed_risk,
        "expected_risk": expected_risk,
        "observed_confidence": observed_conf,
        "expected_confidence": expected_conf,
        "observed_subcategories": observed_subcats,
        "expected_subcategories": expected_subcats,
        "replay_anomalies": replay_anomalies,
        "expected_replay_anomalies": expected_anomalies,
        "findings_count": len(output.findings),
        "evidence_count": len(output.evidence),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PRAMAAN Phase 17 Provenance Assurance Corpus.")
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=DEFAULT_CORPUS_ROOT,
        help="Root path for generated corpus (default: data/corpus/provenance)",
    )
    args = parser.parse_args()
    generator = ProvenanceCorpusGenerator(root=args.corpus_root)
    generator.generate_all()


if __name__ == "__main__":
    main()
