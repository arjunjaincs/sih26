"""
Tests for GET /api/v1/capabilities method detail payload.
Verifies that all registered detectors expose complete, authoritative method specifications.
"""

from fastapi.testclient import TestClient


def test_capabilities_returns_all_detectors_with_method_details(client: TestClient):
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    data = response.json()

    assert "detectors" in data
    assert "supported_dataset_formats" in data
    assert "supported_model_formats" in data
    assert "pramaan_version" in data

    detectors = data["detectors"]
    assert len(detectors) == 11

    # Map by code
    by_code = {d["code"]: d for d in detectors}
    expected_codes = [
        "DI-01", "DI-02", "DI-03", "DI-04", "DI-05",
        "MI-01", "MI-02", "MI-03", "MI-04", "MI-05",
        "PI-01"
    ]
    for code in expected_codes:
        assert code in by_code, f"Missing detector code {code}"
        det = by_code[code]

        # Verify all 14 required fields are present and valid
        assert det["detector_id"]
        assert det["name"]
        assert det["pillar"] in ["Dataset Integrity", "Model Integrity", "Inference Provenance"]
        assert det["description"]
        assert len(det["applicable_asset_types"]) > 0
        assert isinstance(det["available"], bool)
        assert det["access_requirements"]
        assert isinstance(det["dependencies"], list) and len(det["dependencies"]) > 0
        assert isinstance(det["supported_formats"], list) and len(det["supported_formats"]) > 0
        assert det["what_it_analyzes"]
        assert isinstance(det["evidence_produced"], list) and len(det["evidence_produced"]) > 0
        assert det["confidence_semantics"]
        assert isinstance(det["limitations"], list) and len(det["limitations"]) > 0
        assert det["reference_method"]


def test_di02_method_detail_truthful(client: TestClient):
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    detectors = response.json()["detectors"]
    di02 = next((d for d in detectors if d["code"] == "DI-02"), None)
    assert di02 is not None

    assert di02["detector_id"] == "data.integrity.di02_label_integrity"
    assert "Label Integrity" in di02["name"]
    assert di02["pillar"] == "Dataset Integrity"
    assert any("COCO" in fmt or "labels.json" in fmt for fmt in di02["supported_formats"])
    assert "centroid" in di02["what_it_analyzes"]
    assert any("Conflicting duplicate" in ev for ev in di02["evidence_produced"])
    assert "Decoupling" in di02["reference_method"]


def test_mi05_method_detail_truthful(client: TestClient):
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    detectors = response.json()["detectors"]
    mi05 = next((d for d in detectors if d["code"] == "MI-05"), None)
    assert mi05 is not None

    assert mi05["detector_id"] == "model.integrity.mi05_trigger_anomaly"
    assert "Trigger" in mi05["name"]
    assert mi05["pillar"] == "Model Integrity"
    assert "CR < 0.15" in mi05["confidence_semantics"] or "Target Mode Convergence" in mi05["what_it_analyzes"]
    assert any("Neural Cleanse" in mi05["reference_method"] for _ in [1])
    assert any("localized spatial patch" in lim for lim in mi05["limitations"])
