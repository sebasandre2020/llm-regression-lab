"""Bounded MiniMax diagnostic adapter; never sends references or assertions."""

import os
from decimal import Decimal

import httpx

from .artifacts import canonical_bytes, digest_bytes
from .errors import ExecutionFailure

SYSTEM = "Answer the user's question concisely using the supplied context when relevant."
PRICING = {"model": "MiniMax-M3", "date": "2026-09-30", "input_per_million": "0.30", "output_per_million": "1.20"}


def config_for_minimax():
    from .local_profile import config_for

    config = config_for()
    config.update(
        target="minimax:MiniMax-M3",
        model_revision="MiniMax-M3",
        prompt_digest=digest_bytes(SYSTEM.encode()),
        engine_image_digest=digest_bytes(b"minimax-http-adapter-v1"),
        pricing_snapshot_digest=digest_bytes(canonical_bytes(PRICING)),
        execution_profile="local-minimax-v1",
        repetitions=1,
        concurrency=1,
        max_output_tokens=256,
        max_total_tokens=10000,
        max_cost_usd="0.020000",
    )
    return config


class MiniMaxProvider:
    def __init__(self, config, *, api_key=None, transport=None):
        self.config = config
        self._key = api_key if api_key is not None else os.environ.get("MINIMAX_API_KEY", "")
        self.transport = transport
        self.input_tokens = 0
        self.output_tokens = 0
        self.reserved_tokens = 0
        self.reserved_cost = Decimal(0)
        self.observed_revision = None

    @property
    def cost(self):
        return (Decimal(self.input_tokens) * Decimal("0.30") + Decimal(self.output_tokens) * Decimal("1.20")) / 1000000

    async def generate(self, case, target):
        if not self._key:
            raise ExecutionFailure("PROVIDER_AUTH")
        content = case["input"]
        if case["contexts"]:
            content += "\n\nContext:\n" + "\n".join(case["contexts"])
        # Conservative byte-based estimate plus message overhead, reserved before network I/O.
        input_bound = len((SYSTEM + content).encode("utf-8")) + 256
        output_bound = self.config["max_output_tokens"]
        cost_bound = (Decimal(input_bound) * Decimal("0.30") + Decimal(output_bound) * Decimal("1.20")) / 1000000
        if (
            input_bound > 32000
            or output_bound > 4096
            or self.reserved_tokens + input_bound + output_bound > self.config["max_total_tokens"]
            or self.reserved_cost + cost_bound > Decimal(self.config["max_cost_usd"])
        ):
            raise ExecutionFailure("BUDGET_EXCEEDED")
        self.reserved_tokens += input_bound + output_bound
        self.reserved_cost += cost_bound
        try:
            async with httpx.AsyncClient(timeout=60, transport=self.transport, follow_redirects=False) as client:
                response = await client.post(
                    "https://api.minimax.io/v1/chat/completions",
                    headers={"Authorization": "Bearer " + self._key},
                    json={
                        "model": "MiniMax-M3",
                        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
                        "temperature": 0.1,
                        "max_completion_tokens": output_bound,
                        "thinking": {"type": "disabled"},
                        "reasoning_split": True,
                    },
                )
        except httpx.TimeoutException:
            raise ExecutionFailure("PROVIDER_TIMEOUT") from None
        except httpx.HTTPError:
            raise ExecutionFailure("INVALID_ENGINE_OUTPUT") from None
        if response.status_code in (401, 403):
            raise ExecutionFailure("PROVIDER_AUTH")
        if response.status_code == 429:
            raise ExecutionFailure("PROVIDER_RATE_LIMIT")
        if response.is_error:
            raise ExecutionFailure("INVALID_ENGINE_OUTPUT")
        try:
            data = response.json()
            choice = data["choices"][0]
            answer = choice["message"]["content"]
            usage = data["usage"]
            incoming, outgoing = usage["prompt_tokens"], usage["completion_tokens"]
            revision = data["model"]
            if (
                not isinstance(answer, str)
                or not answer.strip()
                or choice["finish_reason"] != "stop"
                or type(incoming) is not int
                or type(outgoing) is not int
                or min(incoming, outgoing) < 0
                or max(incoming, outgoing) > 1000000
                or not isinstance(revision, str)
                or not revision
                or len(revision) > 128
            ):
                raise ValueError()
            if self.observed_revision is not None and self.observed_revision != revision:
                raise ValueError()
        except (ValueError, KeyError, IndexError, TypeError):
            raise ExecutionFailure("INVALID_ENGINE_OUTPUT") from None
        self.observed_revision = revision
        self.input_tokens += incoming
        self.output_tokens += outgoing
        if self.input_tokens + self.output_tokens > self.config["max_total_tokens"] or self.cost > Decimal(
            self.config["max_cost_usd"]
        ):
            raise ExecutionFailure("BUDGET_EXCEEDED")
        return answer.strip()
