"""
/api/demo — attack scenario trigger and reset endpoints.
"""
from fastapi import APIRouter, HTTPException
from app.models.schemas import AttackScenario, TriggerResponse, ResetResponse
from app.data.fixtures import SCENARIO_PATCHES
from app.state import active_scenarios

router = APIRouter(prefix="/demo", tags=["demo"])

# Map each scenario to the human-readable stage names it affects
_STAGE_NAMES = {
    "stage_1": "Training Data",
    "stage_2": "Model",
    "stage_3": "Inference",
    "stage_4": "Evidence & Risk Engine",
    "stage_5": "Assurance Report",
}


@router.post("/trigger/{scenario}", response_model=TriggerResponse)
def trigger_scenario(scenario: AttackScenario) -> TriggerResponse:
    """Activate an attack scenario, mutating the pipeline state."""
    active_scenarios.add(scenario)
    patches = SCENARIO_PATCHES.get(scenario, [])
    affected = [_STAGE_NAMES.get(p["stage_id"], p["stage_id"]) for p in patches]
    return TriggerResponse(
        status="triggered",
        scenario=scenario,
        message=f"Attack scenario '{scenario.value}' is now active. Pipeline state updated.",
        affected_stages=affected,
    )


@router.post("/reset", response_model=ResetResponse)
def reset_pipeline() -> ResetResponse:
    """Clear all active attack scenarios and return the pipeline to baseline."""
    active_scenarios.clear()
    return ResetResponse(
        status="reset",
        message="All active attack scenarios cleared. Pipeline returned to baseline clean state.",
    )
