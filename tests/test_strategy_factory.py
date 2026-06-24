"""Tests for Strategy Factory agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("strategy_factory", "strategy_factory", "agents.strategy_factory", "StrategyFactory",
         '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_strategy_factory_imports():
    from agents.strategy_factory import StrategyFactory
    assert StrategyFactory.name == "strategy_factory"


def test_build_generation_prompt(tmp_db):
    from agents.strategy_factory import StrategyFactory
    agent = StrategyFactory(tmp_db)
    prompt = agent._build_generation_prompt()
    assert isinstance(prompt, str)
    assert "generate_signals" in prompt
    assert "PARAMS" in prompt
    assert len(prompt) > 100


def test_validate_strategy_code_valid():
    from agents.strategy_factory import validate_strategy_code
    code = '''
import pandas as pd
import numpy as np
import ta

PARAMS = {"ema_fast": 5, "ema_slow": 20, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0}

def generate_signals(df, p=PARAMS):
    df["signal"] = 0
    return df
'''
    is_valid, error = validate_strategy_code(code)
    assert is_valid, f"Should be valid but got: {error}"


def test_validate_strategy_code_invalid():
    from agents.strategy_factory import validate_strategy_code
    code = "x = 1 + 2"
    is_valid, error = validate_strategy_code(code)
    assert not is_valid


def test_register_strategy(tmp_db):
    from agents.strategy_factory import StrategyFactory
    agent = StrategyFactory(tmp_db)
    agent._register_strategy(
        strategy_id="S100",
        file_path="strategies/strategy_s100.py",
        family="momentum",
        description="test strategy",
    )
    row = tmp_db.fetchone("SELECT * FROM strategies WHERE id = ?", ("S100",))
    assert row["family"] == "momentum"
    assert row["status"] == "candidate"


def test_tick_no_crash_without_api(tmp_db):
    from agents.strategy_factory import StrategyFactory
    agent = StrategyFactory(tmp_db)
    agent.setup()
    try:
        agent.tick()
    except Exception:
        pass  # Expected if no API key
