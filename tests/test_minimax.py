import json

import httpx
import pytest

from llm_regression_lab.errors import ExecutionFailure
from llm_regression_lab.minimax import MiniMaxProvider, config_for_minimax

CASE = {"input": "Capital of Peru?", "contexts": [], "reference": "SECRET_REFERENCE", "assertions": []}


async def test_minimax_request_and_usage():
    def handle(request):
        payload = json.loads(request.content)
        assert "SECRET_REFERENCE" not in request.content.decode()
        assert payload["max_completion_tokens"] == 256
        assert payload["thinking"] == {"type": "disabled"}
        return httpx.Response(
            200,
            json={
                "model": "MiniMax-M3",
                "choices": [{"message": {"content": "Lima"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 2},
            },
        )

    provider = MiniMaxProvider(config_for_minimax(), api_key="test", transport=httpx.MockTransport(handle))
    assert await provider.generate(CASE, "minimax:MiniMax-M3") == "Lima"
    assert provider.input_tokens == 20 and provider.output_tokens == 2
    assert str(provider.cost) == "0.0000084"


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "PROVIDER_AUTH"),
        (429, "PROVIDER_RATE_LIMIT"),
        (500, "INVALID_ENGINE_OUTPUT"),
        (200, "INVALID_ENGINE_OUTPUT"),
    ],
)
async def test_minimax_failures(status, code):
    provider = MiniMaxProvider(
        config_for_minimax(),
        api_key="test",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={})),
    )
    with pytest.raises(ExecutionFailure) as error:
        await provider.generate(CASE, "minimax:MiniMax-M3")
    assert error.value.code == code


async def test_minimax_budget_prevents_network():
    config = config_for_minimax()
    config["max_cost_usd"] = "0.000000"

    def unexpected(request):
        pytest.fail("Budget must be checked before network I/O")

    provider = MiniMaxProvider(config, api_key="test", transport=httpx.MockTransport(unexpected))
    with pytest.raises(ExecutionFailure) as error:
        await provider.generate(CASE, config["target"])
    assert error.value.code == "BUDGET_EXCEEDED"
