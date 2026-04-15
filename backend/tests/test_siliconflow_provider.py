import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.memory.providers.siliconflow import SiliconFlowProvider


def _mock_response(status_code: int, payload: dict | None = None, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload or {}
    resp.text = text
    return resp


@pytest.mark.anyio
async def test_siliconflow_embed_sends_correct_payload():
    resp = _mock_response(200, {"data": [{"embedding": [0.3] * 1024}]})

    with patch("app.memory.providers.siliconflow.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.post = AsyncMock(return_value=resp)
        MockClient.return_value.__aenter__.return_value = client_instance

        provider = SiliconFlowProvider(
            api_key="sk-test",
            base_url="https://api.siliconflow.cn/v1",
            model="Qwen/Qwen3-Embedding-8B",
            dimensions=1024,
        )
        result = await provider.embed("hello")

    assert result == [0.3] * 1024
    call = client_instance.post.await_args
    assert call.args[0] == "https://api.siliconflow.cn/v1/embeddings"
    assert call.kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert call.kwargs["json"]["model"] == "Qwen/Qwen3-Embedding-8B"
    assert call.kwargs["json"]["input"] == "hello"
    assert call.kwargs["json"]["dimensions"] == 1024


@pytest.mark.anyio
async def test_siliconflow_truncates_oversized_vector_client_side():
    # Server returned 4096 dim ignoring our dimensions param
    resp = _mock_response(200, {"data": [{"embedding": [0.5] * 4096}]})

    with patch("app.memory.providers.siliconflow.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.post = AsyncMock(return_value=resp)
        MockClient.return_value.__aenter__.return_value = client_instance

        provider = SiliconFlowProvider(api_key="k", model="m", dimensions=1024)
        result = await provider.embed("hello")

    assert len(result) == 1024
    assert result[0] == 0.5


@pytest.mark.anyio
async def test_siliconflow_empty_text_returns_none_without_network():
    provider = SiliconFlowProvider(api_key="k", model="m", dimensions=1024)

    with patch("app.memory.providers.siliconflow.httpx.AsyncClient") as MockClient:
        result = await provider.embed("")

    assert result is None
    MockClient.assert_not_called()


@pytest.mark.anyio
async def test_siliconflow_retries_on_5xx_then_gives_up():
    resp_fail = _mock_response(500, text="transient error")

    with patch("app.memory.providers.siliconflow.httpx.AsyncClient") as MockClient, \
         patch("app.memory.providers.siliconflow.asyncio.sleep", new=AsyncMock()):
        client_instance = AsyncMock()
        client_instance.post = AsyncMock(return_value=resp_fail)
        MockClient.return_value.__aenter__.return_value = client_instance

        provider = SiliconFlowProvider(api_key="k", model="m", dimensions=1024)
        result = await provider.embed("hello")

    assert result is None
    # 1 initial + 2 retries = 3 calls
    assert client_instance.post.await_count == 3


@pytest.mark.anyio
async def test_siliconflow_retry_succeeds_on_second_attempt():
    resp_fail = _mock_response(503)
    resp_ok = _mock_response(200, {"data": [{"embedding": [0.7] * 1024}]})

    with patch("app.memory.providers.siliconflow.httpx.AsyncClient") as MockClient, \
         patch("app.memory.providers.siliconflow.asyncio.sleep", new=AsyncMock()):
        client_instance = AsyncMock()
        client_instance.post = AsyncMock(side_effect=[resp_fail, resp_ok])
        MockClient.return_value.__aenter__.return_value = client_instance

        provider = SiliconFlowProvider(api_key="k", model="m", dimensions=1024)
        result = await provider.embed("hello")

    assert result == [0.7] * 1024
    assert client_instance.post.await_count == 2


@pytest.mark.anyio
async def test_siliconflow_batch_embeds_all_texts():
    resp = _mock_response(200, {"data": [
        {"embedding": [0.1] * 1024, "index": 0},
        {"embedding": [0.2] * 1024, "index": 1},
    ]})

    with patch("app.memory.providers.siliconflow.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.post = AsyncMock(return_value=resp)
        MockClient.return_value.__aenter__.return_value = client_instance

        provider = SiliconFlowProvider(api_key="k", model="m", dimensions=1024)
        results = await provider.embed_batch(["a", "b"])

    assert len(results) == 2
    assert results[0][0] == 0.1
    assert results[1][0] == 0.2
