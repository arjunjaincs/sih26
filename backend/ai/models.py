"""
PRAMAAN AI Copilot Data Models.

Defines schemas for chat requests, responses, provider status, and grounded source references.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class AICopilotScope(str, Enum):
    ASSESSMENT = "assessment"
    FINDING = "finding"
    PROVENANCE = "provenance"
    AUDIT = "audit"


class AIProviderStatus(str, Enum):
    CONNECTED = "connected"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class ChatMessage(BaseModel):
    role: str = Field(..., description="'system', 'user', or 'assistant'")
    content: str = Field(..., description="Text content of the message")


class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="User question or prompt for Copilot")
    scope: AICopilotScope = Field(default=AICopilotScope.ASSESSMENT, description="Analysis scope context")
    finding_id: Optional[str] = Field(default=None, description="Specific finding ID if scope is 'finding'")


class AISourceReference(BaseModel):
    type: str = Field(..., description="Source type: 'finding', 'evidence', 'limitation', or 'detector'")
    id: str = Field(..., description="Unique source identifier")
    label: Optional[str] = Field(default=None, description="Human-readable citation label")


class AIChatResponse(BaseModel):
    answer: str = Field(..., description="Copilot generated response")
    provider: str = Field(..., description="Active AI provider name")
    model: str = Field(..., description="Model identifier used")
    scope: str = Field(..., description="Scope of the response")
    grounded: bool = Field(default=True, description="Whether the answer is grounded in actual evidence")
    sources: list[AISourceReference] = Field(default_factory=list, description="Authoritative sources cited")


class AIStatusResponse(BaseModel):
    configured: bool = Field(..., description="Whether cloud AI is configured with credentials")
    provider: str = Field(..., description="Active AI provider identifier")
    model: str = Field(..., description="Configured model identifier")
    status: str = Field(..., description="Connection status: connected, not_configured, unavailable, disabled")
    has_api_key: bool = Field(..., description="Whether an API key is set (masked, key itself is never returned)")
    privacy_disclosure: str = Field(..., description="Disclosure explaining the cloud AI boundary and data minimization")
    available_models: list[str] = Field(default_factory=list, description="List of recommended or available models")


class AIModelsResponse(BaseModel):
    models: list[str] = Field(default_factory=list, description="Supported / recommended models")
    current_model: str = Field(..., description="Currently active model")


class FindingExplainRequest(BaseModel):
    user_query: Optional[str] = Field(default=None, max_length=1000, description="Optional custom analyst inquiry regarding the finding")
