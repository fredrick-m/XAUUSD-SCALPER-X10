"""Tests for core.api_client — token-tracking Anthropic wrapper."""
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    yield db
    db.close()


def test_record_usage_writes_to_db(tmp_db):
    from core.api_client import record_usage
    record_usage(
        db=tmp_db,
        agent_id="test_agent",
        model="claude-haiku-4-5-20251001",
        tokens_in=500,
        tokens_out=200,
        task_type="test_call",
        cached_tokens=100,
    )
    row = tmp_db.fetchone("SELECT * FROM token_usage WHERE agent_id = ?", ("test_agent",))
    assert row["tokens_in"] == 500
    assert row["tokens_out"] == 200
    assert row["cost_usd"] > 0


def test_cost_calculation(tmp_db):
    from core.api_client import record_usage
    # Haiku: $0.80/1M in, $4.00/1M out
    record_usage(
        db=tmp_db,
        agent_id="test",
        model="claude-haiku-4-5-20251001",
        tokens_in=1_000_000,
        tokens_out=1_000_000,
        task_type="test",
    )
    row = tmp_db.fetchone("SELECT cost_usd FROM token_usage WHERE agent_id = ?", ("test",))
    assert abs(row["cost_usd"] - 4.80) < 0.01


def test_api_client_init():
    from core.api_client import APIClient
    client = APIClient(db=None, agent_id="test")
    assert client.agent_id == "test"
