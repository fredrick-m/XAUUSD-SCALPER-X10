"""Tests for UI Director agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("ui_director", "ui_director", "agents.ui_director", "UIDirector", '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_ui_director_imports():
    from agents.ui_director import UIDirector
    assert UIDirector.name == "ui_director"


def test_setup_no_crash(tmp_db):
    from agents.ui_director import UIDirector
    agent = UIDirector(tmp_db)
    agent.setup()  # should not crash; server starts in daemon thread


def test_tick_no_crash(tmp_db):
    from agents.ui_director import UIDirector
    agent = UIDirector(tmp_db)
    agent.setup()
    agent.tick()  # should not crash


def test_compute_dashboard_stats(tmp_db):
    from agents.ui_director import UIDirector
    # Seed one strategy row
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status) VALUES (?, ?, ?, ?)",
        ("strat_001", "strategies/strat_001.py", "scalper", "candidate"),
    )
    agent = UIDirector(tmp_db)
    stats = agent._compute_dashboard_stats()
    assert isinstance(stats, dict)
    assert stats["total_strategies"] >= 1
    assert "agents_total" in stats
    assert "agents_running" in stats
    assert "validated_strategies" in stats
    assert "total_cost_usd" in stats
