"""
Tests for AI data models and schemas.
"""

import pytest
from pydantic import ValidationError

from backend.ai.models import (
    AIChatRequest,
    AIChatResponse,
    AICopilotScope,
    AIProviderStatus,
    AISourceReference,
    AIStatusResponse,
    ChatMessage,
)


def test_chat_message_schema():
    msg = ChatMessage(role="user", content="Explain finding PI-01")
    assert msg.role == "user"
    assert msg.content == "Explain finding PI-01"


def test_ai_chat_request_validation():
    req = AIChatRequest(message="Hello", scope=AICopilotScope.ASSESSMENT)
    assert req.message == "Hello"
    assert req.scope == AICopilotScope.ASSESSMENT
    assert req.finding_id is None

    # Empty message should fail validation
    with pytest.raises(ValidationError):
        AIChatRequest(message="")


def test_ai_source_reference():
    src = AISourceReference(type="finding", id="PI-01-001", label="Exact Duplicate Sample")
    assert src.type == "finding"
    assert src.id == "PI-01-001"
    assert src.label == "Exact Duplicate Sample"


def test_ai_status_response_no_keys_exposed():
    status_resp = AIStatusResponse(
        configured=True,
        provider="openrouter",
        model="anthropic/claude-3.5-sonnet",
        status="connected",
        has_api_key=True,
        privacy_disclosure="Disclosure text",
        available_models=["anthropic/claude-3.5-sonnet"],
    )
    # Ensure api_key field does not exist on schema
    data = status_resp.model_dump()
    assert "api_key" not in data
    assert data["has_api_key"] is True
    assert data["status"] == "connected"
