"""
/api/pipeline — pipeline state endpoints.
"""
from datetime import datetime, timezone
from fastapi import APIRouter
from app.models.schemas import PipelineStateResponse, StageState, StageFinding
from app.data.fixtures import build_stages
from app.state import active_scenarios

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/state", response_model=PipelineStateResponse)
def get_pipeline_state() -> PipelineStateResponse:
    """Return the current state of all 5 pipeline stages."""
    raw_stages = build_stages(list(active_scenarios))
    stages = []
    for s in raw_stages:
        findings = [StageFinding(**f) for f in s["findings"]]
        stages.append(
            StageState(
                stage_id=s["stage_id"],
                stage_name=s["stage_name"],
                risk=s["risk"],
                confidence=s["confidence"],
                coverage_pct=s["coverage_pct"],
                findings=findings,
                audit_hash=s["audit_hash"],
            )
        )
    return PipelineStateResponse(
        pipeline_id="PRAMAAN-PIPE-001",
        captured_at=datetime.now(timezone.utc),
        stages=stages,
        active_scenarios=list(active_scenarios),
    )
