"""Tests for Model Router agent."""
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("model_router", "model_router", "agents.model_router", "ModelRouter", '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_route_generate_strategy():
    from agents.model_router import ModelRouter
    model = ModelRouter.route_task("generate_strategy")
    assert model == "opus"


def test_route_syntax_check():
    from agents.model_router import ModelRouter
    model = ModelRouter.route_task("syntax_check")
    assert model == "haiku"


def test_route_analyze_results():
    from agents.model_router import ModelRouter
    model = ModelRouter.route_task("analyze_results")
    assert model == "sonnet"


def test_route_unknown_defaults_to_sonnet():
    from agents.model_router import ModelRouter
    model = ModelRouter.route_task("something_unknown")
    assert model == "sonnet"


def test_model_router_tick_no_crash(tmp_db):
    from agents.model_router import ModelRouter
    agent = ModelRouter(tmp_db)
    agent.setup()
    agent.tick()
