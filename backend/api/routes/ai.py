"""
PRAMAAN AI Copilot API Routes.

Provides endpoints for:
- Checking AI configuration status and models (GET /api/v1/ai/status, GET /api/v1/ai/models)
- Testing provider connectivity (POST /api/v1/ai/test)
- Interactive Copilot chat against bounded assessment evidence (POST /api/v1/assessments/{id}/ai/chat)
- Instant explanation of a specific finding (POST /api/v1/assessments/{id}/findings/{fid}/ai/explain)
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from backend.ai.models import (
    AIChatRequest,
    AIChatResponse,
    AIModelsResponse,
    AIStatusResponse,
    FindingExplainRequest,
)
from backend.ai.service import ai_service
from backend.api.deps import DbDep
from backend.api.errors import AssessmentNotFound

logger = logging.getLogger("pramaan.api.ai")

router = APIRouter(prefix="/api/v1", tags=["ai"])


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str


@router.get(
    "/ai/status",
    response_model=AIStatusResponse,
    summary="Get current Cloud AI configuration and status",
)
def get_ai_status() -> AIStatusResponse:
    """
    Retrieve Cloud AI Copilot configuration status.
    API keys are never exposed in the response.
    """
    return ai_service.get_status()


@router.get(
    "/ai/models",
    response_model=AIModelsResponse,
    summary="List available/recommended AI models",
)
async def get_ai_models() -> AIModelsResponse:
    """
    List recommended models for the active AI provider.
    """
    return await ai_service.list_models()


@router.post(
    "/ai/test",
    response_model=ConnectionTestResponse,
    summary="Test connectivity to the configured AI provider",
)
async def test_ai_connection() -> ConnectionTestResponse:
    """
    Test whether the configured AI provider is reachable and authenticates successfully.
    """
    ok, msg = await ai_service.test_connection()
    return ConnectionTestResponse(ok=ok, message=msg)


@router.post(
    "/assessments/{assessment_id}/ai/chat",
    response_model=AIChatResponse,
    summary="Interact with PRAMAAN Analyst Copilot",
)
async def chat_with_copilot(
    assessment_id: str,
    body: AIChatRequest,
    conn: DbDep,
) -> AIChatResponse:
    """
    Submit an analyst inquiry to Copilot regarding assessment findings or evidence.
    Strictly READ-ONLY: Never alters findings, risk scores, or audit logs.
    """
    try:
        return await ai_service.chat(conn, assessment_id, body)
    except AssessmentNotFound:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_scope", "message": str(exc)},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "not configured" in msg.lower() or "disabled" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "ai_not_configured", "message": msg},
            )
        elif "timed out" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={"error": "provider_timeout", "message": msg},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "provider_error", "message": msg},
            )


@router.post(
    "/assessments/{assessment_id}/findings/{finding_id}/ai/explain",
    response_model=AIChatResponse,
    summary="Request a detailed explanation for a specific finding",
)
async def explain_finding_with_copilot(
    assessment_id: str,
    finding_id: str,
    conn: DbDep,
    body: FindingExplainRequest | None = None,
) -> AIChatResponse:
    """
    Convenience endpoint for single-click finding explanation from finding cards.
    """
    user_query = body.user_query if body else None
    try:
        return await ai_service.explain_finding(conn, assessment_id, finding_id, user_query)
    except AssessmentNotFound:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_finding", "message": str(exc)},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "not configured" in msg.lower() or "disabled" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "ai_not_configured", "message": msg},
            )
        elif "timed out" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={"error": "provider_timeout", "message": msg},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": "provider_error", "message": msg},
            )
