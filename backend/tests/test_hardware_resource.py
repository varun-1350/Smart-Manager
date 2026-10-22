import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from app import app
from agent.model import OllamaClient


@pytest.mark.asyncio
async def test_ollama_client_hardware_payload():
    client = OllamaClient(
        base_url="http://test:11434",
        model="gemma4:e2b",
        num_ctx=2048,
        num_predict=512,
        num_batch=128,
        keep_alive="5m",
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "ok"}
        mock_post.return_value = mock_resp

        res = await client.generate("test prompt")
        assert res == "ok"
        assert mock_post.called

        called_payload = mock_post.call_args[1]["json"]
        assert called_payload["keep_alive"] == "5m"
        assert called_payload["options"]["num_ctx"] == 2048
        assert called_payload["options"]["num_predict"] == 512
        assert called_payload["options"]["num_batch"] == 128


@pytest.mark.asyncio
async def test_model_unload():
    client = OllamaClient(base_url="http://test:11434", model="gemma4:e2b")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        success = await client.unload_model()
        assert success is True
        called_payload = mock_post.call_args[1]["json"]
        assert called_payload["keep_alive"] == 0
        assert called_payload["model"] == "gemma4:e2b"


@pytest.mark.asyncio
async def test_system_resources_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.get("/api/system/resources")
        assert res.status_code == 200
        data = res.json()
        assert "system_ram" in data
        assert data["system_ram"]["total_gb"] > 0
        assert "active_settings" in data
        assert data["active_settings"]["num_ctx"] == 2048
