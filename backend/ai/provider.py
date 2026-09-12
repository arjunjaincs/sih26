"""
PRAMAAN AI Provider Abstraction.

Defines the clean abstract base class that all AI providers (OpenRouter now,
local Ollama in future) must implement. The rest of PRAMAAN depends strictly
on this contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.ai.models import ChatMessage


class AIProvider(ABC):
    """
    Abstract contract for an AI assistance provider.
    
    Guarantees that replacing or extending the backend provider (e.g. adding Ollama)
    requires zero modifications to the Copilot UI, context builder, assessment engine,
    or API contracts.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Execute a chat completion with the specified message list.
        
        Args:
            messages: List of ChatMessage objects (system, user, assistant).
            model: Optional model override; uses provider default if None.
            timeout: Optional per-request timeout in seconds.
            
        Returns:
            The raw text response from the model.
            
        Raises:
            RuntimeError: If provider communication fails, times out, or returns an error.
        """
        ...

    @abstractmethod
    async def health_check(self) -> tuple[bool, str]:
        """
        Test provider availability and credential validity.
        
        Returns:
            tuple of (is_healthy: bool, status_message: str)
        """
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """
        Return the list of available or recommended models for this provider.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier string for this provider (e.g. 'openrouter', 'ollama')."""
        ...

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """True if the provider has the necessary credentials / endpoints to operate."""
        ...
