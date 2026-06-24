"""Tests for core.config module."""
import os
from pathlib import Path


def test_base_dir_exists():
    from core.config import BASE_DIR
    assert isinstance(BASE_DIR, Path)
    assert BASE_DIR.exists()


def test_db_path_is_under_base():
    from core.config import BASE_DIR, DB_PATH
    assert str(DB_PATH).startswith(str(BASE_DIR))
    assert DB_PATH.name == "agent_db.sqlite"


def test_data_dir_exists():
    from core.config import DATA_DIR
    assert isinstance(DATA_DIR, Path)


def test_strategies_dir_exists():
    from core.config import STRATEGIES_DIR
    assert isinstance(STRATEGIES_DIR, Path)


def test_core_agents_list():
    from core.config import CORE_AGENTS
    assert isinstance(CORE_AGENTS, list)
    assert len(CORE_AGENTS) >= 5
    names = [a["name"] for a in CORE_AGENTS]
    assert "token_manager" in names
    assert "model_router" in names
    assert "data_agent" in names
    assert "backtest_runner" in names
    assert "strategy_factory" in names


def test_model_constants():
    from core.config import MODELS
    assert "haiku" in MODELS
    assert "sonnet" in MODELS
    assert "opus" in MODELS
