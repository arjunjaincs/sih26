"""
Tests for OpenRouterProvider with simulated network conditions (zero external calls).
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from backend.ai.models import ChatMessage
from backend.ai.openrouter import OpenRouterProvider


@pytest.mark.asyncio
async def test_openrouter_missing_api_key():
    provider = OpenRouterProvider(api_key="")
    assert not provider.is_configured
    with pytest.raises(RuntimeError, match="Cloud AI is not configured"):
        await provider.chat([ChatMessage(role="user", content="Hello")])


@pytest.mark.asyncio
async def test_openrouter_headers():
    provider = OpenRouterProvider(
        api_key="test-key-12345",
        base_url="https://openrouter.ai/api/v1",
        default_model="anthropic/claude-3.5-sonnet",
        zdr_privacy=True,
    )
    headers = provider._build_headers()
    assert headers["Authorization"] == "Bearer test-key-12345"
    assert headers["HTTP-Referer"] == "https://pramaan.sih.internal"
    assert headers["X-Title"] == "PRAMAAN AI Assurance Platform"
    assert headers["X-Data-Collection"] == "deny"


@pytest.mark.asyncio
async def test_openrouter_successful_chat():
    provider = OpenRouterProvider(api_key="valid-test-key")

    mock_response = httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": "Finding PI-01-001 shows exact duplicates in the dataset."
                    }
                }
            ]
        },
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await provider.chat([ChatMessage(role="user", content="Explain finding")])
        assert "Finding PI-01-001" in result


@pytest.mark.asyncio
async def test_openrouter_timeout_handling():
    provider = OpenRouterProvider(api_key="valid-test-key", timeout=10.0)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Read timed out")
        with pytest.raises(RuntimeError, match="timed out"):
            await provider.chat([ChatMessage(role="user", content="Hello")])


@pytest.mark.asyncio
async def test_openrouter_http_401_error():
    provider = OpenRouterProvider(api_key="bad-key")

    mock_response = httpx.Response(
        401,
        text='{"error": "Unauthorized"}',
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        with pytest.raises(RuntimeError, match="HTTP 401"):
            await provider.chat([ChatMessage(role="user", content="Hello")])


@pytest.mark.asyncio
async def test_openrouter_malformed_response():
    provider = OpenRouterProvider(api_key="valid-test-key")

    mock_response = httpx.Response(
        200,
        json={"choices": []},
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        with pytest.raises(RuntimeError, match="missing choices array"):
            await provider.chat([ChatMessage(role="user", content="Hello")])


@pytest.mark.asyncio
async def test_openrouter_health_check():
    provider = OpenRouterProvider(api_key="valid-test-key")

    mock_response = httpx.Response(
        200,
        json={"data": []},
        request=httpx.Request("GET", "https://openrouter.ai/api/v1/models"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        ok, msg = await provider.health_check()
        assert ok is True
        assert "Connected" in msg
