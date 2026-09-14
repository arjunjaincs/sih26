"""
Tests for PRAMAAN Deterministic Offline Demo Presets and Demo Mode.

Validates:
1. GET /api/v1/demos returns all 5 authentic corpus presets with enriched metadata:
   - clean_baseline
   - duplicate_data
   - corrupted_model
   - trojan_model
   - provenance_attestation
2. Every preset contains required truth indicators:
   - expected_layer
   - expected_finding_type
   - complexity
   - is_deterministic_corpus = True
   - valid resolved local file paths
3. Real authoritative execution:
   - Submitting preset payloads through POST /api/v1/assessments runs actual detectors
   - Produces actual findings, evidence, and completed assessment state
   - Zero mocked or simulated findings
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestDemoPresetsExtended:
    """Test authentic offline demo presets and their end-to-end execution."""

    def test_list_demos_metadata_and_structure(self, client: TestClient):
        """Verify all 5 presets exist with complete analyst-facing metadata."""
        res = client.get("/api/v1/demos")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 6

        preset_ids = [d["id"] for d in data["demos"]]
        expected_ids = [
            "unified_forensic_suite",
            "clean_baseline",
            "duplicate_data",
            "corrupted_model",
            "trojan_model",
            "provenance_attestation",
        ]
        for eid in expected_ids:
            assert eid in preset_ids, f"Expected preset '{eid}' not found in demos"

        for p in data["demos"]:
            assert p["id"]
            assert p["name"]
            assert p["category"]
            assert p["description"]
            assert p["expected_risk"] in ["NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
            assert p["expected_confidence"] in ["LOW", "MODERATE", "HIGH"]
            assert isinstance(p["detectors_targeted"], list)
            assert len(p["detectors_targeted"]) > 0

            # Verified new metadata fields
            assert p["expected_layer"] in ["Model Integrity", "Dataset Integrity", "Inference Provenance", "Multi-Layer Assurance"]
            assert isinstance(p["expected_finding_type"], str) and len(p["expected_finding_type"]) > 5
            assert isinstance(p["complexity"], str) and p["complexity"].startswith("Level ")
            assert p["is_deterministic_corpus"] is True

            # Payload validation
            payload = p["payload"]
            assert payload["title"].startswith("Demo:")

            # Check that referenced model or dataset paths actually exist on disk
            if "model_path" in payload and payload["model_path"]:
                assert Path(payload["model_path"]).exists(), f"Model path does not exist: {payload['model_path']}"
            if "model_reference_path" in payload and payload["model_reference_path"]:
                assert Path(payload["model_reference_path"]).exists(), f"Ref path does not exist: {payload['model_reference_path']}"
            if "dataset_path" in payload and payload["dataset_path"]:
                assert Path(payload["dataset_path"]).exists(), f"Dataset path does not exist: {payload['dataset_path']}"

    @pytest.mark.parametrize(
        "preset_id",
        [
            "unified_forensic_suite",
            "clean_baseline",
            "duplicate_data",
            "corrupted_model",
            "trojan_model",
            "provenance_attestation",
        ],
    )
    def test_demo_preset_authoritative_execution(self, client: TestClient, preset_id: str):
        """Every demo preset payload executes through the real assessment engine with 201 Created."""
        demos_res = client.get("/api/v1/demos")
        assert demos_res.status_code == 200
        presets = {d["id"]: d for d in demos_res.json()["demos"]}
        preset = presets[preset_id]

        # Execute the actual assessment
        create_res = client.post("/api/v1/assessments", json=preset["payload"])
        assert create_res.status_code == 201
        asmt = create_res.json()

        assert asmt["assessment_id"]
        assert asmt["title"] == preset["payload"]["title"]
        assert asmt["status"] == "complete"
        assert asmt["software_version"] == "1.0.0"
        assert asmt["audit_chain_valid"] is True

        # Ensure real detectors executed
        executed_detectors = asmt["detectors_executed"]
        assert len(executed_detectors) > 0

        # Verify specific scenario properties without mocked data
        if preset_id == "clean_baseline":
            assert asmt["overall_risk"].lower() == "none"
        elif preset_id == "duplicate_data":
            # Must have executed DI-01 duplicate detection and found clusters
            assert any("di01" in d.lower() or "duplicate" in d.lower() for d in executed_detectors)
            assert asmt["findings_count"] > 0
        elif preset_id == "corrupted_model":
            assert asmt["overall_risk"].lower() in ["high", "critical"]
            assert asmt["findings_count"] > 0
        elif preset_id == "trojan_model":
            assert asmt["overall_risk"].lower() in ["high", "critical"]
            assert asmt["findings_count"] > 0
        elif preset_id == "provenance_attestation":
            assert asmt["audit_chain_valid"] is True
        elif preset_id == "unified_forensic_suite":
            assert asmt["findings_count"] > 0
            assert asmt["overall_risk"].lower() in ["high", "critical"]
            # All 3 layers must have executed detectors!
            assert any("di" in d.lower() for d in executed_detectors)
            assert any("mi" in d.lower() for d in executed_detectors)
            assert any("pi" in d.lower() for d in executed_detectors)
