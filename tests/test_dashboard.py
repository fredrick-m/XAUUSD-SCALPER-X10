"""
Tests for the Flask + htmx dashboard (dashboard/app.py).
Uses a temp SQLite database and monkeypatches _get_db.
"""
import json
import pytest
import tempfile
from pathlib import Path

from core.db import Database
from core.logger import log_event


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary Database with schema initialised."""
    db_file = tmp_path / "test_agent.sqlite"
    db = Database(db_file)
    db.init_schema()
    yield db
    db.close()


@pytest.fixture
def client(tmp_db, monkeypatch):
    """Flask test client with _get_db monkeypatched to tmp_db."""
    import dashboard.app as app_module
    monkeypatch.setattr(app_module, "_get_db", lambda: tmp_db)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


# ── Page route tests ──────────────────────────────────────────────────────────

def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"XAUUSD" in resp.data


def test_strategies_page(client):
    resp = client.get("/strategies")
    assert resp.status_code == 200


def test_tokens_page(client):
    resp = client.get("/tokens")
    assert resp.status_code == 200


def test_events_page(client):
    resp = client.get("/events")
    assert resp.status_code == 200


# ── API route tests ───────────────────────────────────────────────────────────

def test_api_agents(tmp_db, client):
    tmp_db.execute(
        """INSERT INTO agent_registry
           (id, name, module_path, class_name, status)
           VALUES (?, ?, ?, ?, ?)""",
        ("agent-1", "test_agent", "agents.test", "TestAgent", "running"),
    )
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["name"] == "test_agent"
    assert data[0]["status"] == "running"


def test_api_strategies(tmp_db, client):
    tmp_db.execute(
        """INSERT INTO strategies
           (id, file_path, family, status, generation, best_profit_factor)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("strat-1", "strategies/test.py", "scalper", "validated", 1, 3.5),
    )
    resp = client.get("/api/strategies")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["id"] == "strat-1"


def test_api_token_usage(tmp_db, client):
    tmp_db.execute(
        """INSERT INTO token_usage
           (agent_id, model, tokens_in, tokens_out, cost_usd, task_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("agent-1", "claude-sonnet-4-6", 1000, 500, 0.025, "backtest"),
    )
    resp = client.get("/api/tokens")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "total_cost" in data
    assert data["total_cost"] > 0
    assert "by_agent" in data
    assert "by_model" in data


def test_api_events(tmp_db, client):
    log_event(tmp_db, "agent-1", "INFO", "Test event message", {"key": "value"})
    resp = client.get("/api/events")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "event_message" in data[0]
    assert data[0]["event_message"] == "Test event message"


def test_api_system_summary(tmp_db, client):
    # Insert an agent so we have something to count
    tmp_db.execute(
        """INSERT INTO agent_registry
           (id, name, module_path, class_name, status)
           VALUES (?, ?, ?, ?, ?)""",
        ("agent-2", "runner_agent", "agents.runner", "Runner", "running"),
    )
    resp = client.get("/api/summary")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "agents_running" in data
    assert "total_strategies" in data
    assert "total_cost_usd" in data
