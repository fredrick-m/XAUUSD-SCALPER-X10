"""Anthropic API client with automatic token usage tracking.

Dual mode:
  - If ANTHROPIC_API_KEY is set → direct API call (original behavior)
  - If no key → queue request in llm_queue table, poll for Claude Code to process it
"""
import os
import time
from typing import Optional

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


def has_api_key() -> bool:
    """Check if an Anthropic API key is configured."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


class APIClient:
    """Wrapper around the Anthropic SDK that tracks token usage per call.

    When no API key is available, requests are queued in the llm_queue table
    and the call blocks until Claude Code processes the request.
    """

    def __init__(self, db, agent_id: str):
        self.db = db
        self.agent_id = agent_id
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def call(self, prompt: str, model_key: str = "sonnet", system: str = "",
             max_tokens: int = 4096, task_type: str = "general", temperature: float = 0.7) -> str:
        """Call Claude and record token usage. Returns the text response."""
        if has_api_key():
            return self._call_api(prompt, model_key, system, max_tokens, task_type, temperature)
        return self._call_via_queue(prompt, model_key, system, max_tokens, task_type, temperature)

    # ── Direct API path ───────────────────────────────────────────────────────

    def _call_api(self, prompt: str, model_key: str, system: str,
                  max_tokens: int, task_type: str, temperature: float) -> str:
        """Direct Anthropic API call."""
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

    # ── Queue path (no API key) ───────────────────────────────────────────────

    def _call_via_queue(self, prompt: str, model_key: str, system: str,
                        max_tokens: int, task_type: str, temperature: float) -> str:
        """Queue the request and poll until Claude Code processes it."""
        model_id = MODELS.get(model_key, model_key)

        cursor = self.db.execute(
            "INSERT INTO llm_queue (agent_id, prompt, system_prompt, model, task_type, max_tokens, temperature) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.agent_id, prompt, system, model_id, task_type, max_tokens, temperature),
        )
        request_id = cursor.lastrowid

        from core.logger import get_logger
        logger = get_logger(self.agent_id)
        logger.info(f"LLM request #{request_id} queued ({task_type}) — waiting for Claude Code...")

        # Poll for response (10 min timeout)
        deadline = time.time() + 600
        while time.time() < deadline:
            row = self.db.fetchone(
                "SELECT response FROM llm_queue WHERE id = ? AND status = 'completed'",
                (request_id,),
            )
            if row and row["response"]:
                return row["response"]
            time.sleep(2)

        raise TimeoutError(f"LLM request #{request_id} timed out — no Claude Code session processing the queue")
