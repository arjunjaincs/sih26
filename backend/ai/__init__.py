"""
PRAMAAN AI Assistance Subsystem.

Provides optional, read-only Cloud AI Copilot analysis using OpenRouter (and future
extensible local providers) while keeping the deterministic assurance engine 100% offline.
"""

from backend.ai.context_builder import AIContextBuilder
from backend.ai.fake_provider import MockAIProvider
from backend.ai.models import (
    AIChatRequest,
    AIChatResponse,
    AICopilotScope,
    AIModelsResponse,
    AIProviderStatus,
    AISourceReference,
    AIStatusResponse,
    ChatMessage,
    FindingExplainRequest,
)
from backend.ai.openrouter import OpenRouterProvider
from backend.ai.policy import COPILOT_SYSTEM_POLICY, PRIVACY_DISCLOSURE, RECOMMENDED_MODELS
from backend.ai.provider import AIProvider
from backend.ai.service import AIService, ai_service

__all__ = [
    "AIContextBuilder",
    "AIProvider",
    "OpenRouterProvider",
    "MockAIProvider",
    "AIService",
    "ai_service",
    "ChatMessage",
    "AIChatRequest",
    "AIChatResponse",
    "AICopilotScope",
    "AIProviderStatus",
    "AISourceReference",
    "AIStatusResponse",
    "AIModelsResponse",
    "FindingExplainRequest",
    "COPILOT_SYSTEM_POLICY",
    "PRIVACY_DISCLOSURE",
    "RECOMMENDED_MODELS",
]
