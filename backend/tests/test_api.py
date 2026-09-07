"""
PRAMAAN pytest suite — covers all API endpoints.
Run with: pytest tests/test_api.py -v
"""
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
import app.state as state


@pytest.fixture(autouse=True)
def reset_state():
    """Ensure a clean pipeline state before and after every test."""
    state.active_scenarios.clear()
    yield
    state.active_scenarios.clear()


@pytest.mark.asyncio
async def test_pipeline_state_baseline():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/pipeline/state")
    assert r.status_code == 200
    body = r.json()
    assert body["pipeline_id"] == "PRAMAAN-PIPE-001"
    assert len(body["stages"]) == 5
    assert body["active_scenarios"] == []
    for stage in body["stages"]:
        assert stage["risk"] in ("clean", "low")  # baseline is clean/low only


@pytest.mark.asyncio
async def test_trigger_backdoor_injection():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/demo/trigger/backdoor_injection")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "triggered"
    assert body["scenario"] == "backdoor_injection"
    assert len(body["affected_stages"]) > 0


@pytest.mark.asyncio
async def test_pipeline_state_after_backdoor():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/demo/trigger/backdoor_injection")
        r = await client.get("/api/pipeline/state")
    assert r.status_code == 200
    body = r.json()
    assert "backdoor_injection" in body["active_scenarios"]
    risks = [s["risk"] for s in body["stages"]]
    assert "critical" in risks


@pytest.mark.asyncio
async def test_trigger_all_scenarios():
    scenarios = [
        "label_manipulation", "duplicate_flooding", "backdoor_injection",
        "model_substitution", "inference_tampering", "replay_attack", "distribution_shift"
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for scenario in scenarios:
            r = await client.post(f"/api/demo/trigger/{scenario}")
            assert r.status_code == 200, f"Failed to trigger {scenario}: {r.text}"


@pytest.mark.asyncio
async def test_demo_reset():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/demo/trigger/backdoor_injection")
        r = await client.post("/api/demo/reset")
    assert r.status_code == 200
    assert r.json()["status"] == "reset"
    # Confirm state is cleared
    assert len(state.active_scenarios) == 0


@pytest.mark.asyncio
async def test_reset_restores_clean_pipeline():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/demo/trigger/model_substitution")
        await client.post("/api/demo/reset")
        r = await client.get("/api/pipeline/state")
    body = r.json()
    assert body["active_scenarios"] == []
    for stage in body["stages"]:
        assert stage["risk"] in ("clean", "low")


@pytest.mark.asyncio
async def test_report_generate_baseline():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/report/generate")
    assert r.status_code == 200
    body = r.json()
    assert body["report_id"].startswith("PRAMAAN-")
    assert body["pipeline_summary"]["overall_risk"] in ("clean", "low")
    assert body["audit_chain_verified"] is True
    assert body["attack_scenarios_detected"] == []
    assert len(body["analyst_recommendation"]) > 100
    assert len(body["stages"]) == 5


@pytest.mark.asyncio
async def test_report_generate_after_backdoor():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/demo/trigger/backdoor_injection")
        r = await client.get("/api/report/generate")
    assert r.status_code == 200
    body = r.json()
    assert body["pipeline_summary"]["overall_risk"] == "critical"
    assert body["audit_chain_verified"] is False
    assert "backdoor_injection" in body["attack_scenarios_detected"]
    assert "CRITICAL" in body["analyst_recommendation"]


@pytest.mark.asyncio
async def test_report_recommendation_varies_by_risk():
    """Verify the recommendation text changes meaningfully across risk levels."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r_clean = await client.get("/api/report/generate")
        await client.post("/api/demo/trigger/distribution_shift")
        r_medium = await client.get("/api/report/generate")
        await client.post("/api/demo/trigger/backdoor_injection")
        r_critical = await client.get("/api/report/generate")

    assert r_clean.json()["analyst_recommendation"] != r_medium.json()["analyst_recommendation"]
    assert r_medium.json()["analyst_recommendation"] != r_critical.json()["analyst_recommendation"]


@pytest.mark.asyncio
async def test_invalid_scenario_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/demo/trigger/not_a_real_scenario")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_no_root_hello_world():
    """Ensure the default FastAPI boilerplate root endpoint is not present."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/")
    assert r.status_code == 404
