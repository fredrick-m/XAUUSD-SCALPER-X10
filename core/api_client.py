"""Anthropic API client with automatic token usage tracking."""
import os
from typing import Optional

import anthropic

from core.config import MODELS, MODEL_COSTS


def _compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Compute cost in USD for a given model and token counts."""
    costs = MODEL_COSTS.get(model, {"input": 15.0, "output": 75.0})
    return (tokens_in * costs["input"] + tokens_out * costs["output"]) / 1_000_000


def record_usage(db, agent_id: str, model: str, tokens_in: int, tokens_out: int,
                 task_type: str, cached_tokens: int = 0):
    """Record a single API call's token usage to the database."""
    cost = _compute_cost(model, tokens_in, tokens_out)
    db.execute(
        "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type, cached_tokens) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (agent_id, model, tokens_in, tokens_out, cost, task_type, cached_tokens),
    )


class APIClient:
    """Wrapper around the Anthropic SDK that tracks token usage per call."""

    def __init__(self, db, agent_id: str):
        self.db = db
        self.agent_id = agent_id
        self._client = None

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def call(self, prompt: str, model_key: str = "sonnet", system: str = "",
             max_tokens: int = 4096, task_type: str = "general", temperature: float = 0.7) -> str:
        """Call Claude and record token usage. Returns the text response."""
        model_id = MODELS.get(model_key, model_key)

        messages = [{"role": "user", "content": prompt}]
        kwargs = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)

        usage = response.usage
        tokens_in = usage.input_tokens
        tokens_out = usage.output_tokens
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0

        if self.db is not None:
            record_usage(
                db=self.db, agent_id=self.agent_id, model=model_id,
                tokens_in=tokens_in, tokens_out=tokens_out,
                task_type=task_type, cached_tokens=cached,
            )

        return response.content[0].text
