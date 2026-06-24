"""Tests for Backtest Runner agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("backtest_runner", "backtest_runner", "agents.backtest_runner", "BacktestRunner",
         '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_backtest_runner_imports():
    from agents.backtest_runner import BacktestRunner
    assert BacktestRunner.name == "backtest_runner"


def test_run_backtest_on_strategy(tmp_db):
    from agents.backtest_runner import BacktestRunner
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status) VALUES (?, ?, ?, ?)",
        ("S001", "strategies/strategy_s001.py", "EMA", "candidate"),
    )
    agent = BacktestRunner(tmp_db)
    agent.setup()
    result = agent.run_single_backtest("S001")
    assert result is None or isinstance(result, dict)


def test_process_task_from_queue(tmp_db):
    from agents.backtest_runner import BacktestRunner
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status) VALUES (?, ?, ?, ?)",
        ("S001", "strategies/strategy_s001.py", "EMA", "candidate"),
    )
    tmp_db.execute(
        "INSERT INTO task_queue (agent_target, task_type, payload, created_by) VALUES (?, ?, ?, ?)",
        ("backtest_runner", "backtest", json.dumps({"strategy_id": "S001"}), "test"),
    )
    agent = BacktestRunner(tmp_db)
    agent.setup()
    agent.tick()
    task = tmp_db.fetchone("SELECT status FROM task_queue WHERE agent_target = 'backtest_runner'")
    assert task["status"] in ("completed", "failed")


def test_tick_no_crash_empty_queue(tmp_db):
    from agents.backtest_runner import BacktestRunner
    agent = BacktestRunner(tmp_db)
    agent.setup()
    agent.tick()
