from __future__ import annotations

import httpx
import pytest

from api_gateway.client import AsyncHTTPClient

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_live_request_does_not_log_content_by_default(monkeypatch, tmp_path) -> None:
    client = AsyncHTTPClient()
    request = httpx.Request("POST", "https://example.test/chat")
    response = httpx.Response(
        200,
        request=request,
        json={
            "choices": [{"message": {"content": "private response"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    )

    async def post(*args, **kwargs):
        return response

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(client, "_is_simulated", lambda provider: False)
    monkeypatch.setattr(client.client, "post", post)

    assert await client.post_request("local/test", "private prompt") == "private response"
    assert not (tmp_path / "logs" / "model_io.log").exists()
    await client.close()


@pytest.mark.asyncio
async def test_provider_error_excludes_response_body(monkeypatch) -> None:
    client = AsyncHTTPClient()
    request = httpx.Request("POST", "https://example.test/chat")
    response = httpx.Response(401, text="secret upstream diagnostic", request=request)

    async def post(*args, **kwargs):
        return response

    monkeypatch.setattr(client, "_is_simulated", lambda provider: False)
    monkeypatch.setattr(client.client, "post", post)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await client.post_request("local/test", "prompt")

    assert "secret upstream diagnostic" not in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_missing_key_in_production_refuses_instead_of_simulating(monkeypatch) -> None:
    """Production must never silently fabricate an answer when a key is blank."""
    client = AsyncHTTPClient()
    monkeypatch.setattr(client, "_is_simulated", lambda provider: True)
    monkeypatch.setattr(
        "api_gateway.client.get_settings",
        lambda: type("S", (), {"ENVIRONMENT": "production"})(),
    )

    sim_called = False

    async def _sim(*args, **kwargs):
        nonlocal sim_called
        sim_called = True
        return "FABRICATED"

    monkeypatch.setattr(client, "_run_simulation", _sim)

    with pytest.raises(RuntimeError):
        await client.post_request("openrouter/model", "prompt")
    assert sim_called is False
    await client.close()


@pytest.mark.asyncio
async def test_missing_key_outside_production_still_simulates(monkeypatch) -> None:
    """Development/test keep the offline simulation fallback."""
    client = AsyncHTTPClient()
    monkeypatch.setattr(client, "_is_simulated", lambda provider: True)
    monkeypatch.setattr(
        "api_gateway.client.get_settings",
        lambda: type("S", (), {"ENVIRONMENT": "development"})(),
    )

    result = await client.post_request("openrouter/model", "prompt")
    assert "simulated" in result.lower()
    await client.close()
