"""
PRAMAAN Mock AI Provider for testing and offline verification.

Simulates provider responses, error conditions, timeouts, and records outgoing messages
without making any network calls or requiring an API key.
"""

from __future__ import annotations

from typing import Callable, Optional
from backend.ai.models import ChatMessage
from backend.ai.policy import RECOMMENDED_MODELS
from backend.ai.provider import AIProvider


class MockAIProvider(AIProvider):
    """
    Mock AI Provider for automated tests and offline simulation.
    """

    def __init__(
        self,
        configured: bool = True,
        healthy: bool = True,
        health_message: str = "Mock provider online",
        canned_response: Optional[str] = None,
        custom_handler: Optional[Callable[[list[ChatMessage], Optional[str]], str]] = None,
    ) -> None:
        self._configured = configured
        self._healthy = healthy
        self._health_message = health_message
        self._canned_response = canned_response or (
            "Based on the evidence in [finding: PI-01-001], PRAMAAN detected exact duplicate "
            "samples in the dataset. This represents a potential data leakage risk. "
            "Evidence [evidence: EV-001] details the affected asset. Recommended action: "
            "Review duplicate sample paths and prune redundancies before training."
        )
        self._custom_handler = custom_handler
        self.should_timeout: bool = False
        self.should_error: bool = False
        self.error_message: str = "Simulated provider error"
        self.recorded_calls: list[dict] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def is_configured(self) -> bool:
        return self._configured

    def set_configured(self, val: bool) -> None:
        self._configured = val

    def set_healthy(self, val: bool, msg: str = "") -> None:
        self._healthy = val
        if msg:
            self._health_message = msg

    async def chat(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        self.recorded_calls.append({
            "messages": messages,
            "model": model,
            "timeout": timeout,
        })

        if not self._configured:
            raise RuntimeError("Cloud AI is not configured. An API key is required.")

        if self.should_timeout:
            raise RuntimeError(f"OpenRouter request timed out after {timeout or 30.0:.1f}s.")

        if self.should_error:
            raise RuntimeError(self.error_message)

        if self._custom_handler:
            return self._custom_handler(messages, model)

        return self._canned_response

    async def health_check(self) -> tuple[bool, str]:
        if not self._configured:
            return False, "AI provider not configured."
        return self._healthy, self._health_message

    async def list_models(self) -> list[str]:
        return list(RECOMMENDED_MODELS)
