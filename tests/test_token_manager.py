"""Tests for Token Manager agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("token_manager", "token_manager", "agents.token_manager", "TokenManager", '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_token_manager_imports():
    from agents.token_manager import TokenManager
    assert TokenManager.name == "token_manager"


def test_aggregate_usage(tmp_db):
    from agents.token_manager import TokenManager
    for i in range(5):
        tmp_db.execute(
            "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) VALUES (?, ?, ?, ?, ?, ?)",
            ("strategy_factory", "claude-opus-4-6", 1000, 500, 0.09, "generate"),
        )
    for i in range(10):
        tmp_db.execute(
            "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) VALUES (?, ?, ?, ?, ?, ?)",
            ("data_agent", "claude-haiku-4-5-20251001", 200, 100, 0.001, "classify"),
        )
    agent = TokenManager(tmp_db)
    summary = agent.compute_summary()
    assert summary["total_cost"] > 0
    assert summary["total_calls"] == 15
    assert "strategy_factory" in summary["by_agent"]
    assert "data_agent" in summary["by_agent"]


def test_token_manager_tick_no_crash(tmp_db):
    from agents.token_manager import TokenManager
    agent = TokenManager(tmp_db)
    agent.setup()
    agent.tick()
