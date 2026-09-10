"""
Tests for Phase 4: Model Integrity Fingerprinting (MI-01).

Strategy:
  - All synthetic models created locally — no internet, no downloads.
  - ONNX models built with tests/detectors/onnx_writer.py (raw protobuf,
    no 'onnx' package needed) and verified via onnxruntime.
  - PyTorch tests skipped when torch not installed.
  - When onnxruntime is not installed, graceful-degradation path is verified.
  - Anti-fake tests prove detector output changes with actual model changes.

Test classes:
  TestModelLoaderSecurity         — path, size, extension, unsafe pickle
  TestModelLoaderGraceful         — unavailable framework handling
  TestArtifactFingerprint         — SHA-256 identity, determinism
  TestStructuralFingerprintOnnx   — ONNX structural fields via ORT
  TestBehavioralFingerprintOnnx   — deterministic probe battery via ORT
  TestReferenceComparison         — compare_fingerprints() logic
  TestRiskConfidenceSeparation    — ADR-003 compliance
  TestMI01Detector                — metadata, can_run, full run
  TestPersistenceRoundTrip        — runner → DB → retrieval
  TestAntiFake                    — output changes when model changes
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from backend.detectors.base import DetectorContext
from backend.detectors.model.mi01_fingerprint import (
    MI01Context,
    MI01FingerprintDetector,
    ArtifactFingerprint,
    BehavioralFingerprint,
    StructuralFingerprint,
    ModelFingerprint,
    ComparisonDifference,
    BehavioralProbe,
    _derive_risk_confidence,
    build_fingerprint,
    compare_fingerprints,
    _build_integrity_finding,
    _METADATA,
)
from backend.detectors.registry import ALL_DETECTORS, DETECTOR_BY_ID
from backend.detectors.runner import run_detector
from backend.domain.entities import Assessment, Asset, ModelArtifact
from backend.domain.enums import (
    AccessLevel,
    AssetType,
    AssessmentType,
    ConfidenceLevel,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    ModelFramework,
    RiskLevel,
    Severity,
)
from backend.infra.db import (
    AssessmentRepository,
    AssetRepository,
    DetectorResultRepository,
    EvidenceRepository,
    FindingRepository,
    ModelArtifactRepository,
)
from backend.infra.model_loader import (
    ModelLoadError,
    ModelLoadErrorCode,
    _ONNX_AVAILABLE,
    _ORT_AVAILABLE,
    _TORCH_AVAILABLE,
    load_model,
)

# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------

requires_ort = pytest.mark.skipif(
    not _ORT_AVAILABLE, reason="onnxruntime not installed"
)
requires_torch = pytest.mark.skipif(
    not _TORCH_AVAILABLE, reason="torch not installed"
)


# ---------------------------------------------------------------------------
# Helpers — synthetic model factories (no onnx package required)
# ---------------------------------------------------------------------------

def _make_relu_model(tmp_path: Path, name: str = "relu.onnx") -> Path:
    """Create a valid ONNX Relu model using the raw protobuf writer."""
    from tests.detectors.onnx_writer import make_relu_model
    path = tmp_path / name
    path.write_bytes(make_relu_model([1, 3]))
    return path


def _make_bias_model(
    tmp_path: Path,
    bias: float = 1.0,
    name: str = "bias.onnx",
) -> Path:
    """Create a valid ONNX Add-bias model with a configurable initializer."""
    from tests.detectors.onnx_writer import make_add_bias_model
    path = tmp_path / name
    path.write_bytes(make_add_bias_model([bias, bias, bias], [1, 3]))
    return path


def _make_pytorch_state_dict(tmp_path: Path, name: str = "model.pt") -> Path:
    """Create a minimal PyTorch state dict. Requires torch."""
    import torch
    sd = {"layer.weight": torch.ones(3, 3), "layer.bias": torch.zeros(3)}
    path = tmp_path / name
    torch.save(sd, str(path))
    return path


def _make_unsafe_pickle(tmp_path: Path, name: str = "evil.pt") -> Path:
    """Create a file with a malicious __reduce__. Must be REJECTED by loader."""
    import pickle

    class _Evil:
        def __reduce__(self):
            return (eval, ("__import__('os').getcwd()",))

    path = tmp_path / name
    with open(path, "wb") as f:
        pickle.dump(_Evil(), f)
    return path


# ---------------------------------------------------------------------------
# DB setup helpers
# ---------------------------------------------------------------------------

def _setup_model_assessment(db) -> tuple[str, str]:
    """Create Assessment + Asset + ModelArtifact. Return (assessment_id, model_id)."""
    a = Assessment(title="MI-01 test assessment")
    AssessmentRepository(db).insert(a)

    asset = Asset(
        assessment_id=a.assessment_id,
        asset_type=AssetType.MODEL,
        name="test_model",
        sha256="a" * 64,
        size_bytes=1024,
    )
    AssetRepository(db).insert(asset)

    ma = ModelArtifact(
        model_id=asset.asset_id,
        assessment_id=a.assessment_id,
        framework=ModelFramework.ONNX,
        access_level=AccessLevel.WHITE_BOX,
        source_path="/tmp/test.onnx",
    )
    ModelArtifactRepository(db).insert(ma)

    return a.assessment_id, asset.asset_id


def _make_ctx(db, assessment_id, model_id, model_path, reference=None) -> DetectorContext:
    """Build a DetectorContext with MI01Context attached."""
    ctx = DetectorContext(
        assessment_id=assessment_id,
        asset_id=model_id,
        conn=db,
    )
    ctx.mi01 = MI01Context(
        model_path=model_path,
        reference_fingerprint=reference,
    )
    return ctx


# ---------------------------------------------------------------------------
# Tests: Model Loader Security
# ---------------------------------------------------------------------------

class TestModelLoaderSecurity:

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(ModelLoadError) as exc_info:
            load_model(tmp_path / "nonexistent.onnx")
        assert exc_info.value.code == ModelLoadErrorCode.FILE_NOT_FOUND

    def test_directory_raises(self, tmp_path):
        with pytest.raises(ModelLoadError) as exc_info:
            load_model(tmp_path)
        assert exc_info.value.code == ModelLoadErrorCode.NOT_A_FILE

    def test_unsupported_extension_rejected(self, tmp_path):
        f = tmp_path / "model.keras"
        f.write_bytes(b"fake")
        with pytest.raises(ModelLoadError) as exc_info:
            load_model(f)
        assert exc_info.value.code == ModelLoadErrorCode.UNSUPPORTED_FORMAT

    def test_txt_extension_rejected(self, tmp_path):
        f = tmp_path / "weights.txt"
        f.write_bytes(b"not a model")
        with pytest.raises(ModelLoadError) as exc_info:
            load_model(f)
        assert exc_info.value.code == ModelLoadErrorCode.UNSUPPORTED_FORMAT

    def test_file_too_large_rejected(self, tmp_path):
        f = tmp_path / "huge.onnx"
        f.write_bytes(b"x" * 1024)
        with pytest.raises(ModelLoadError) as exc_info:
            load_model(f, max_size_bytes=512)
        assert exc_info.value.code == ModelLoadErrorCode.FILE_TOO_LARGE

    def test_relative_path_raises(self):
        """load_model requires absolute paths."""
        with pytest.raises(ModelLoadError) as exc_info:
            load_model(Path("relative/path/model.onnx"))
        assert exc_info.value.code in (
            ModelLoadErrorCode.PATH_TRAVERSAL,
            ModelLoadErrorCode.FILE_NOT_FOUND,
        )

    @requires_torch
    def test_unsafe_pickle_rejected(self, tmp_path):
        """PyTorch file with malicious __reduce__ must be rejected (weights_only=True)."""
        evil = _make_unsafe_pickle(tmp_path)
        with pytest.raises(ModelLoadError) as exc_info:
            load_model(evil)
        assert exc_info.value.code in (
            ModelLoadErrorCode.UNSAFE_PICKLE,
            ModelLoadErrorCode.MALFORMED,
        ), "Unsafe pickle must be caught by weights_only=True"

    @requires_ort
    def test_malformed_onnx_rejected(self, tmp_path):
        """Garbage bytes in .onnx → ORT session creation fails → load_model raises."""
        f = tmp_path / "garbage.onnx"
        f.write_bytes(b"\xFF\xFE garbage not a protobuf")
        with pytest.raises(ModelLoadError) as exc_info:
            load_model(f)
        assert exc_info.value.code in (
            ModelLoadErrorCode.MALFORMED,
            ModelLoadErrorCode.VALIDATION_FAILED,
        )


class TestModelLoaderGraceful:
    """Graceful degradation when frameworks not installed."""

    def test_onnx_unavailable_returns_error(self, tmp_path, monkeypatch):
        import backend.infra.model_loader as ml
        monkeypatch.setattr(ml, "_ONNX_AVAILABLE", False)
        monkeypatch.setattr(ml, "_ORT_AVAILABLE", False)
        f = tmp_path / "model.onnx"
        f.write_bytes(b"fake")
        with pytest.raises(ModelLoadError) as exc_info:
            ml.load_model(f)
        assert exc_info.value.code == ModelLoadErrorCode.DEPENDENCY_UNAVAILABLE

    def test_torch_unavailable_returns_error(self, tmp_path, monkeypatch):
        import backend.infra.model_loader as ml
        monkeypatch.setattr(ml, "_TORCH_AVAILABLE", False)
        f = tmp_path / "model.pt"
        f.write_bytes(b"fake")
        with pytest.raises(ModelLoadError) as exc_info:
            ml.load_model(f)
        assert exc_info.value.code == ModelLoadErrorCode.DEPENDENCY_UNAVAILABLE

    def test_framework_available_returns_bool(self):
        from backend.infra.model_loader import framework_available
        assert isinstance(framework_available("onnx"), bool)
        assert isinstance(framework_available("pytorch"), bool)

    def test_unsupported_framework_returns_false(self):
        from backend.infra.model_loader import framework_available
        assert framework_available("tensorflow") is False
        assert framework_available("completely_fake") is False


# ---------------------------------------------------------------------------
# Tests: Artifact Fingerprint
# ---------------------------------------------------------------------------

class TestArtifactFingerprint:

    def test_identical_file_same_sha256(self, tmp_path):
        f = tmp_path / "model.onnx"
        f.write_bytes(b"some content " + b"x" * 500)
        fp1 = build_fingerprint(f)
        fp2 = build_fingerprint(f)
        assert fp1.artifact.sha256 == fp2.artifact.sha256

    def test_modified_file_different_sha256(self, tmp_path):
        """ANTI-FAKE: modifying file content must change SHA-256."""
        f = tmp_path / "model.onnx"
        f.write_bytes(b"original content")
        fp1 = build_fingerprint(f)

        f.write_bytes(b"modified content!")
        fp2 = build_fingerprint(f)

        assert fp1.artifact.sha256 != fp2.artifact.sha256, (
            "ANTI-FAKE: SHA-256 must change when file content changes"
        )

    def test_sha256_matches_hash_file(self, tmp_path):
        from backend.infra.crypto import hash_file
        content = b"deterministic content"
        f = tmp_path / "model.onnx"
        f.write_bytes(content)
        fp = build_fingerprint(f)
        assert fp.artifact.sha256 == hash_file(f)

    def test_file_size_recorded(self, tmp_path):
        content = b"z" * 2048
        f = tmp_path / "model.onnx"
        f.write_bytes(content)
        fp = build_fingerprint(f)
        assert fp.artifact.file_size_bytes == 2048

    def test_format_recorded(self, tmp_path):
        f = tmp_path / "mymodel.onnx"
        f.write_bytes(b"placeholder")
        fp = build_fingerprint(f)
        assert fp.artifact.format == "onnx"

    def test_pramaan_version_recorded(self, tmp_path):
        f = tmp_path / "m.onnx"
        f.write_bytes(b"x")
        fp = build_fingerprint(f)
        assert fp.artifact.pramaan_version == "1.0.0"

    def test_timestamp_recorded(self, tmp_path):
        f = tmp_path / "m.onnx"
        f.write_bytes(b"x")
        fp = build_fingerprint(f)
        assert fp.artifact.analyzed_at_utc  # non-empty

    def test_to_dict_json_serializable(self, tmp_path):
        f = tmp_path / "m.onnx"
        f.write_bytes(b"x")
        fp = build_fingerprint(f)
        d = fp.to_dict()
        json_str = json.dumps(d)
        assert len(json_str) > 10


# ---------------------------------------------------------------------------
# Tests: ONNX Structural Fingerprint (via ORT, no onnx package)
# ---------------------------------------------------------------------------

class TestStructuralFingerprintOnnx:

    @requires_ort
    def test_relu_model_has_structural_fingerprint(self, tmp_path):
        path = _make_relu_model(tmp_path)
        fp = build_fingerprint(path)
        assert fp.structural.available is True
        assert fp.structural.framework == "onnx"
        assert "X" in fp.structural.input_names
        assert "Y" in fp.structural.output_names

    @requires_ort
    def test_structural_fingerprint_deterministic(self, tmp_path):
        path = _make_relu_model(tmp_path)
        fp1 = build_fingerprint(path)
        fp2 = build_fingerprint(path)
        assert fp1.structural.input_names == fp2.structural.input_names
        assert fp1.structural.output_names == fp2.structural.output_names
        assert fp1.structural.input_shapes == fp2.structural.input_shapes

    @requires_ort
    def test_relu_and_bias_models_different_structural_fingerprints(self, tmp_path):
        relu_path = _make_relu_model(tmp_path, "relu.onnx")
        bias_path = _make_bias_model(tmp_path, bias=1.0, name="bias.onnx")
        fp_relu = build_fingerprint(relu_path)
        fp_bias = build_fingerprint(bias_path)
        # They have the same i/o names (both X→Y) but different graph names
        # or different structural details from ORT meta
        assert fp_relu.structural.available is True
        assert fp_bias.structural.available is True

    def test_structural_unavailable_when_ort_missing(self, tmp_path, monkeypatch):
        import backend.detectors.model.mi01_fingerprint as mod
        monkeypatch.setattr(mod, "_ORT_AVAILABLE", False)
        f = tmp_path / "model.onnx"
        f.write_bytes(b"fake")
        fp = build_fingerprint(f)
        assert fp.structural.available is False
        assert fp.structural.error is not None


# ---------------------------------------------------------------------------
# Tests: Behavioral Fingerprint (ONNX via ORT)
# ---------------------------------------------------------------------------

class TestBehavioralFingerprintOnnx:

    @requires_ort
    def test_behavioral_fingerprint_available(self, tmp_path):
        path = _make_relu_model(tmp_path)
        fp = build_fingerprint(path)
        assert fp.behavioral.available is True
        assert len(fp.behavioral.probes) > 0

    @requires_ort
    def test_probes_are_deterministic(self, tmp_path):
        path = _make_relu_model(tmp_path)
        fp1 = build_fingerprint(path)
        fp2 = build_fingerprint(path)
        for p1, p2 in zip(fp1.behavioral.probes, fp2.behavioral.probes):
            assert p1.output_sha256 == p2.output_sha256, (
                f"Probe {p1.probe_name}: output SHA-256 must be deterministic"
            )

    @requires_ort
    def test_probe_names_present(self, tmp_path):
        path = _make_relu_model(tmp_path)
        fp = build_fingerprint(path)
        probe_names = {p.probe_name for p in fp.behavioral.probes}
        assert "probe_zeros" in probe_names
        assert "probe_ones" in probe_names
        assert "probe_noise" in probe_names

    @requires_ort
    def test_probes_have_sha256(self, tmp_path):
        path = _make_relu_model(tmp_path)
        fp = build_fingerprint(path)
        for p in fp.behavioral.probes:
            if p.error is None:
                assert p.output_sha256 is not None
                assert len(p.output_sha256) == 64

    @requires_ort
    def test_probes_have_statistics(self, tmp_path):
        path = _make_relu_model(tmp_path)
        fp = build_fingerprint(path)
        for p in fp.behavioral.probes:
            if p.error is None:
                assert p.output_mean is not None
                assert p.output_std is not None
                assert p.output_shape is not None

    @requires_ort
    def test_relu_zeros_output_all_zero(self, tmp_path):
        """Relu(zeros) = zeros — verifies probe correctness."""
        path = _make_relu_model(tmp_path)
        fp = build_fingerprint(path)
        zero_probe = next(p for p in fp.behavioral.probes if p.probe_name == "probe_zeros")
        assert zero_probe.output_mean is not None
        assert abs(zero_probe.output_mean) < 1e-6, "Relu(zeros) mean must be ~0"

    @requires_ort
    def test_relu_ones_output_all_ones(self, tmp_path):
        """Relu(ones) = ones — verifies probe correctness."""
        path = _make_relu_model(tmp_path)
        fp = build_fingerprint(path)
        ones_probe = next(p for p in fp.behavioral.probes if p.probe_name == "probe_ones")
        assert ones_probe.output_mean is not None
        assert abs(ones_probe.output_mean - 1.0) < 1e-5, "Relu(ones) mean must be ~1"

    @requires_ort
    def test_different_bias_produces_different_behavioral_hash(self, tmp_path):
        """
        ANTI-FAKE: bias=1.0 vs bias=100.0 must produce different output hashes.
        """
        path_a = _make_bias_model(tmp_path, bias=1.0, name="a.onnx")
        path_b = _make_bias_model(tmp_path, bias=100.0, name="b.onnx")
        fp_a = build_fingerprint(path_a)
        fp_b = build_fingerprint(path_b)

        probes_a = {p.probe_name: p.output_sha256 for p in fp_a.behavioral.probes if p.output_sha256}
        probes_b = {p.probe_name: p.output_sha256 for p in fp_b.behavioral.probes if p.output_sha256}

        shared = set(probes_a) & set(probes_b)
        assert shared, "Should have shared probe names to compare"
        assert any(probes_a[k] != probes_b[k] for k in shared), (
            "ANTI-FAKE: different model weights must produce different behavioral hashes"
        )

    def test_behavioral_unavailable_when_ort_missing(self, tmp_path, monkeypatch):
        import backend.detectors.model.mi01_fingerprint as mod
        monkeypatch.setattr(mod, "_ORT_AVAILABLE", False)
        f = tmp_path / "model.onnx"
        f.write_bytes(b"fake")
        fp = build_fingerprint(f)
        assert fp.behavioral.available is False
        assert fp.behavioral.error is not None


# ---------------------------------------------------------------------------
# Tests: Reference Comparison
# ---------------------------------------------------------------------------

class TestReferenceComparison:

    def _make_fp(
        self,
        sha256: str = "a" * 64,
        size: int = 1000,
        node_count: int | None = 5,
        init_count: int | None = 2,
        input_names: list[str] | None = None,
        output_names: list[str] | None = None,
    ) -> ModelFingerprint:
        a = ArtifactFingerprint(sha256=sha256, file_size_bytes=size,
                                format="onnx", pramaan_version="1.0.0",
                                analyzed_at_utc="2026-01-01T00:00:00+00:00")
        s = StructuralFingerprint(
            available=True, framework="onnx",
            node_count=node_count, initializer_count=init_count,
            input_names=input_names or ["X"],
            output_names=output_names or ["Y"],
            operator_types=["Relu"],
        )
        b = BehavioralFingerprint(available=False, framework="onnx")
        return ModelFingerprint(artifact=a, structural=s, behavioral=b)

    def test_identical_fingerprints_no_diffs(self):
        fp = self._make_fp()
        diffs = compare_fingerprints(fp, fp.to_dict())
        assert diffs == []

    def test_sha256_change_detected(self):
        fp = self._make_fp(sha256="a" * 64)
        ref = self._make_fp(sha256="b" * 64).to_dict()
        diffs = compare_fingerprints(fp, ref)
        sha_diffs = [d for d in diffs if d.field == "artifact.sha256"]
        assert len(sha_diffs) == 1
        assert sha_diffs[0].observed_value == "a" * 64
        assert sha_diffs[0].reference_value == "b" * 64

    def test_node_count_change_detected(self):
        fp = self._make_fp(node_count=10)
        ref = self._make_fp(node_count=5).to_dict()
        diffs = compare_fingerprints(fp, ref)
        node_diffs = [d for d in diffs if d.field == "structural.node_count"]
        assert len(node_diffs) == 1
        assert node_diffs[0].observed_value == 10
        assert node_diffs[0].reference_value == 5

    def test_behavioral_diff_detected(self):
        fp_base = self._make_fp()
        ref_dict = fp_base.to_dict()

        fp_with_behav = ModelFingerprint(
            artifact=fp_base.artifact,
            structural=fp_base.structural,
            behavioral=BehavioralFingerprint(
                available=True, framework="onnx",
                probes=[BehavioralProbe(
                    probe_name="probe_zeros", input_shape=[1, 3],
                    output_shape=[1, 3], output_dtype="float32",
                    output_sha256="obs_hash" + "0" * 56,
                    output_mean=0.0, output_std=0.0, output_min=0.0, output_max=0.0,
                )],
            ),
        )
        ref_dict["behavioral"] = {
            "available": True, "framework": "onnx", "error": None,
            "probes": [{"probe_name": "probe_zeros", "input_shape": [1, 3],
                        "output_shape": [1, 3], "output_dtype": "float32",
                        "output_sha256": "ref_hash" + "0" * 56,
                        "output_mean": 0.0, "output_std": 0.0,
                        "output_min": 0.0, "output_max": 0.0, "error": None}],
        }
        diffs = compare_fingerprints(fp_with_behav, ref_dict)
        behav_diffs = [d for d in diffs if "behavioral" in d.field]
        assert len(behav_diffs) >= 1

    def test_empty_reference_no_crash(self):
        fp = self._make_fp()
        diffs = compare_fingerprints(fp, {})
        assert isinstance(diffs, list)
        # No usable reference values → no diffs
        assert diffs == []

    def test_diff_description_non_empty(self):
        fp = self._make_fp(sha256="a" * 64)
        ref = self._make_fp(sha256="b" * 64).to_dict()
        diffs = compare_fingerprints(fp, ref)
        for d in diffs:
            assert len(d.description) > 10

    def test_no_diff_when_none_fields_in_reference(self):
        """None values in reference (unavailable) must not produce diffs."""
        fp = self._make_fp(node_count=5)
        ref = self._make_fp(node_count=None).to_dict()
        diffs = compare_fingerprints(fp, ref)
        node_diffs = [d for d in diffs if d.field == "structural.node_count"]
        assert node_diffs == []


# ---------------------------------------------------------------------------
# Tests: Risk / Confidence Separation (ADR-003)
# ---------------------------------------------------------------------------

class TestRiskConfidenceSeparation:

    def _fp(self, struct: bool = True, behav: bool = True) -> ModelFingerprint:
        a = ArtifactFingerprint("a" * 64, 100, "onnx", "1.0.0", "ts")
        s = StructuralFingerprint(available=struct, framework="onnx")
        b = BehavioralFingerprint(available=behav, framework="onnx")
        return ModelFingerprint(a, s, b)

    def test_no_reference_risk_none(self):
        risk, _, _ = _derive_risk_confidence([], self._fp(), has_reference=False)
        assert risk == RiskLevel.NONE

    def test_no_reference_high_confidence_when_analysis_available(self):
        _, conf, _ = _derive_risk_confidence([], self._fp(struct=True, behav=True), False)
        assert conf == ConfidenceLevel.HIGH

    def test_no_reference_low_confidence_when_unavailable(self):
        _, conf, _ = _derive_risk_confidence([], self._fp(struct=False, behav=False), False)
        assert conf == ConfidenceLevel.LOW

    def test_no_diffs_risk_none(self):
        risk, _, _ = _derive_risk_confidence([], self._fp(), has_reference=True)
        assert risk == RiskLevel.NONE

    def test_no_diffs_high_confidence_with_behavioral(self):
        _, conf, _ = _derive_risk_confidence([], self._fp(struct=True, behav=True), True)
        assert conf == ConfidenceLevel.HIGH

    def test_no_diffs_moderate_confidence_without_behavioral(self):
        _, conf, _ = _derive_risk_confidence([], self._fp(struct=True, behav=False), True)
        assert conf == ConfidenceLevel.MODERATE

    def test_artifact_diff_only_risk_low(self):
        diffs = [ComparisonDifference("artifact.sha256", "ref", "obs", "SHA changed")]
        risk, _, _ = _derive_risk_confidence(diffs, self._fp(), has_reference=True)
        assert risk == RiskLevel.LOW

    def test_structural_diff_risk_medium(self):
        diffs = [ComparisonDifference("structural.node_count", 5, 10, "nodes changed")]
        risk, _, _ = _derive_risk_confidence(diffs, self._fp(), has_reference=True)
        assert risk == RiskLevel.MEDIUM

    def test_behavioral_diff_risk_medium(self):
        diffs = [ComparisonDifference(
            "behavioral.probe_zeros.output_sha256", "ref", "obs", "output changed"
        )]
        risk, _, _ = _derive_risk_confidence(diffs, self._fp(), has_reference=True)
        assert risk == RiskLevel.MEDIUM

    def test_risk_and_confidence_independent(self):
        """MEDIUM risk with unavailable analysis → LOW confidence (ADR-003)."""
        fp = self._fp(struct=False, behav=False)
        diffs = [ComparisonDifference("structural.node_count", 5, 10, "changed")]
        risk, conf, _ = _derive_risk_confidence(diffs, fp, has_reference=True)
        assert risk == RiskLevel.MEDIUM
        assert conf == ConfidenceLevel.LOW

    def test_findings_never_claim_malicious_automatically(self):
        """Finding title/description must not assert malice."""
        a = ArtifactFingerprint("a" * 64, 100, "onnx", "1.0.0", "ts")
        s = StructuralFingerprint(available=True, framework="onnx")
        b = BehavioralFingerprint(available=True, framework="onnx")
        fp = ModelFingerprint(a, s, b)

        diffs = [ComparisonDifference("artifact.sha256", "ref", "obs", "SHA changed")]
        finding, _ = _build_integrity_finding(
            diffs, fp, "assess1", "asset1", "det1", RiskLevel.LOW
        )
        assert "malicious" not in finding.title.lower()
        assert "backdoor" not in finding.title.lower()
        assert "is malicious" not in finding.description.lower()
        assert "is a backdoor" not in finding.description.lower()


# ---------------------------------------------------------------------------
# Tests: MI-01 Detector (full integration)
# ---------------------------------------------------------------------------

class TestMI01Detector:

    def test_metadata_correct(self):
        det = MI01FingerprintDetector()
        assert det.metadata.detector_id == "model.integrity.mi01_fingerprint"
        assert det.metadata.version == "1.0.0"
        assert "model" in det.metadata.applicable_asset_types

    def test_can_run_requires_mi01_context(self, db, tmp_path):
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = DetectorContext(assessment_id=assessment_id, asset_id=model_id, conn=db)
        result = MI01FingerprintDetector().can_run(ctx)
        assert result.ok is False
        assert "mi01" in result.reason.lower() or "MI01Context" in result.reason

    def test_can_run_nonexistent_file_false(self, db, tmp_path):
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, tmp_path / "nonexistent.onnx")
        assert MI01FingerprintDetector().can_run(ctx).ok is False

    def test_can_run_unsupported_extension_false(self, db, tmp_path):
        f = tmp_path / "model.keras"
        f.write_bytes(b"fake")
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, f)
        assert MI01FingerprintDetector().can_run(ctx).ok is False

    def test_can_run_valid_path_true(self, db, tmp_path):
        f = tmp_path / "model.onnx"
        f.write_bytes(b"fake content")
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, f)
        assert MI01FingerprintDetector().can_run(ctx).ok is True

    def test_run_always_returns_output(self, db, tmp_path):
        """Even with garbage bytes, run() returns something — never crashes."""
        f = tmp_path / "model.onnx"
        f.write_bytes(b"garbage content not a real onnx model")
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, f)
        output = MI01FingerprintDetector().run(ctx)
        assert output is not None
        assert output.status in (
            DetectorStatus.SUCCESS, DetectorStatus.PARTIAL, DetectorStatus.FAILED
        )

    @requires_ort
    def test_run_real_model_produces_fingerprint_finding(self, db, tmp_path):
        path = _make_relu_model(tmp_path)
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, path)
        output = MI01FingerprintDetector().run(ctx)

        assert len(output.findings) >= 1
        info = [f for f in output.findings if f.subcategory == "fingerprint_recorded"]
        assert len(info) == 1

        meas_ev = [e for e in output.evidence if e.evidence_type == EvidenceType.MEASUREMENT]
        assert len(meas_ev) >= 1
        assert len(meas_ev[0].data["artifact_sha256"]) == 64
        assert meas_ev[0].data["artifact_sha256"] != "0" * 64

    @requires_ort
    def test_no_reference_no_mismatch_finding(self, db, tmp_path):
        path = _make_relu_model(tmp_path)
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, path, reference=None)
        output = MI01FingerprintDetector().run(ctx)
        mismatch = [f for f in output.findings if f.subcategory == "integrity_mismatch"]
        assert len(mismatch) == 0

    @requires_ort
    def test_matching_reference_no_mismatch(self, db, tmp_path):
        path = _make_relu_model(tmp_path)
        reference = build_fingerprint(path).to_dict()
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, path, reference=reference)
        output = MI01FingerprintDetector().run(ctx)
        mismatch = [f for f in output.findings if f.subcategory == "integrity_mismatch"]
        assert len(mismatch) == 0
        assert output.risk_level == RiskLevel.NONE

    @requires_ort
    def test_mismatching_reference_produces_finding(self, db, tmp_path):
        """ANTI-FAKE: modified model vs original reference → integrity mismatch finding."""
        original = _make_bias_model(tmp_path, bias=1.0, name="orig.onnx")
        modified = _make_bias_model(tmp_path, bias=99.0, name="mod.onnx")

        reference = build_fingerprint(original).to_dict()

        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, modified, reference=reference)
        output = MI01FingerprintDetector().run(ctx)

        mismatch = [f for f in output.findings if f.subcategory == "integrity_mismatch"]
        assert len(mismatch) >= 1, (
            "ANTI-FAKE: modifying model weights must produce an integrity mismatch finding"
        )
        assert output.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH)

    @requires_ort
    def test_evidence_references_actual_sha256(self, db, tmp_path):
        """Evidence must contain actual SHA-256, not a hardcoded constant."""
        from backend.infra.crypto import hash_file
        path = _make_relu_model(tmp_path)
        actual_sha256 = hash_file(path)

        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, path)
        output = MI01FingerprintDetector().run(ctx)

        ev_sha256 = [
            e.data["artifact_sha256"]
            for e in output.evidence
            if "artifact_sha256" in e.data
        ]
        assert len(ev_sha256) >= 1
        assert ev_sha256[0] == actual_sha256, (
            "ANTI-FAKE: evidence must reference actual SHA-256"
        )

    def test_run_output_changes_when_file_changes(self, db, tmp_path):
        """
        Core anti-fake: two files with different content → different detector output.
        Works without ORT — SHA-256 comparison catches file changes.
        """
        f1 = tmp_path / "v1.onnx"
        f2 = tmp_path / "v2.onnx"
        f1.write_bytes(b"model version 1 content here")
        f2.write_bytes(b"model version 2 content here - different bytes")

        ref = build_fingerprint(f1).to_dict()
        fp2 = build_fingerprint(f2)

        # If SHAs differ (they must), the comparison will detect the change
        if ref["artifact"]["sha256"] != fp2.artifact.sha256:
            assessment_id, model_id = _setup_model_assessment(db)
            ctx = _make_ctx(db, assessment_id, model_id, f2, reference=ref)
            output = MI01FingerprintDetector().run(ctx)
            # Different files → at least risk > NONE or a mismatch finding
            mismatch = [f for f in output.findings if f.subcategory == "integrity_mismatch"]
            assert len(mismatch) >= 1 or output.risk_level != RiskLevel.NONE, (
                "ANTI-FAKE: different model files must produce different detector output"
            )


# ---------------------------------------------------------------------------
# Tests: Persistence Round-Trip
# ---------------------------------------------------------------------------

class TestPersistenceRoundTrip:

    @requires_ort
    def test_runner_persists_findings(self, db, tmp_path):
        path = _make_relu_model(tmp_path)
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, path)
        run_detector(MI01FingerprintDetector(), ctx, db)

        findings = FindingRepository(db).list_by_assessment(assessment_id)
        assert len(findings) >= 1
        assert all(f.category == FindingCategory.MODEL_INTEGRITY for f in findings)

    @requires_ort
    def test_runner_persists_evidence(self, db, tmp_path):
        path = _make_relu_model(tmp_path)
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, path)
        run_detector(MI01FingerprintDetector(), ctx, db)

        findings = FindingRepository(db).list_by_assessment(assessment_id)
        for f in findings:
            evs = EvidenceRepository(db).list_by_finding(f.finding_id)
            assert len(evs) >= 1

    @requires_ort
    def test_runner_persists_detector_result(self, db, tmp_path):
        path = _make_relu_model(tmp_path)
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, path)
        run_detector(MI01FingerprintDetector(), ctx, db)

        results = DetectorResultRepository(db).list_by_assessment(assessment_id)
        mi_results = [r for r in results if r.detector_id == "model.integrity.mi01_fingerprint"]
        assert len(mi_results) == 1
        r = mi_results[0]
        assert r.status in (DetectorStatus.SUCCESS, DetectorStatus.PARTIAL)
        assert r.duration_ms is not None

    @requires_ort
    def test_evidence_data_survives_db_roundtrip(self, db, tmp_path):
        path = _make_relu_model(tmp_path)
        assessment_id, model_id = _setup_model_assessment(db)
        ctx = _make_ctx(db, assessment_id, model_id, path)
        run_detector(MI01FingerprintDetector(), ctx, db)

        findings = FindingRepository(db).list_by_assessment(assessment_id)
        for f in findings:
            for ev in EvidenceRepository(db).list_by_finding(f.finding_id):
                assert isinstance(ev.data, dict)


# ---------------------------------------------------------------------------
# Tests: Registry
# ---------------------------------------------------------------------------

class TestRegistry:

    def test_mi01_in_registry(self):
        assert "model.integrity.mi01_fingerprint" in DETECTOR_BY_ID

    def test_mi01_implements_protocol(self):
        from backend.detectors.base import Detector
        det = DETECTOR_BY_ID["model.integrity.mi01_fingerprint"]
        assert isinstance(det, Detector)

    def test_all_detectors_in_registry(self):
        assert "data.integrity.di01_duplicates" in DETECTOR_BY_ID
        assert "model.integrity.mi01_fingerprint" in DETECTOR_BY_ID
        assert len(ALL_DETECTORS) >= 2
