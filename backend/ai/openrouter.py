"""
PRAMAAN OpenRouter AI Provider.

Implements the AIProvider interface for OpenRouter's OpenAI-compatible API.
Includes robust error handling, timeout management, ZDR privacy controls, and credential safety.
"""

from __future__ import annotations

import logging
from typing import Optional
import httpx

from backend.ai.models import ChatMessage
from backend.ai.policy import RECOMMENDED_MODELS
from backend.ai.provider import AIProvider

logger = logging.getLogger("pramaan.ai.openrouter")


class OpenRouterProvider(AIProvider):
    """
    OpenRouter API provider for Cloud AI assistance.
    
    Adheres strictly to the AIProvider contract. Sanitizes outgoing requests,
    never logs sensitive tokens or prompts, and handles connection failures gracefully.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        default_model: str = "anthropic/claude-3.5-sonnet",
        timeout: float = 30.0,
        zdr_privacy: bool = False,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._base_url = (base_url or "https://openrouter.ai/api/v1").strip().rstrip("/")
        self._default_model = (default_model or "anthropic/claude-3.5-sonnet").strip()
        self._timeout = max(5.0, float(timeout))
        self._zdr_privacy = bool(zdr_privacy)

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def default_model(self) -> str:
        return self._default_model

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://pramaan.sih.internal",
            "X-Title": "PRAMAAN AI Assurance Platform",
            "Content-Type": "application/json",
        }
        if self._zdr_privacy:
            headers["X-Data-Collection"] = "deny"
        return headers

    async def chat(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Send chat messages to OpenRouter chat completions endpoint.
        """
        if not self.is_configured:
            raise RuntimeError("Cloud AI is not configured. An OpenRouter API key is required.")

        active_model = model.strip() if model and model.strip() else self._default_model
        req_timeout = max(5.0, float(timeout)) if timeout is not None else self._timeout

        payload = {
            "model": active_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": 0.2,  # Low temperature for deterministic, factual explanations
            "max_tokens": 1500,
        }

        url = f"{self._base_url}/chat/completions"
        headers = self._build_headers()

        try:
            async with httpx.AsyncClient(timeout=req_timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code == 401:
                    raise RuntimeError("Authentication failed with OpenRouter (HTTP 401). Verify OPENROUTER_API_KEY.")
                elif response.status_code == 429:
                    raise RuntimeError("OpenRouter rate limit or quota exceeded (HTTP 429). Please try again later.")
                elif response.status_code >= 400:
                    # Sanitize error detail to prevent key leaks
                    sanitized_err = response.text[:200]
                    raise RuntimeError(f"OpenRouter error (HTTP {response.status_code}): {sanitized_err}")

                data = response.json()
                choices = data.get("choices", [])
                if not choices or not isinstance(choices, list):
                    raise RuntimeError("Malformed response from OpenRouter: missing choices array.")

                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    raise RuntimeError("Empty response content received from OpenRouter model.")

                return content.strip()

        except httpx.TimeoutException:
            raise RuntimeError(f"OpenRouter request timed out after {req_timeout:.1f}s.")
        except httpx.RequestError as exc:
            raise RuntimeError(f"Failed to connect to OpenRouter endpoint: {exc.__class__.__name__}")

    async def health_check(self) -> tuple[bool, str]:
        """
        Check OpenRouter connectivity and authentication without high latency.
        """
        if not self.is_configured:
            return False, "OpenRouter API key is not configured."

        url = f"{self._base_url}/models"
        headers = self._build_headers()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return True, "Connected to OpenRouter API."
                elif response.status_code in (401, 403):
                    return False, f"OpenRouter authentication failed (HTTP {response.status_code})."
                else:
                    return False, f"OpenRouter returned HTTP {response.status_code}."
        except httpx.TimeoutException:
            return False, "Connection to OpenRouter timed out."
        except httpx.RequestError as exc:
            return False, f"OpenRouter connection error: {exc.__class__.__name__}"
        except Exception as exc:
            return False, f"Health check failed: {type(exc).__name__}"

    async def list_models(self) -> list[str]:
        """
        Return recommended models and currently configured model.
        """
        models = list(RECOMMENDED_MODELS)
        if self._default_model not in models:
            models.insert(0, self._default_model)
        return models
