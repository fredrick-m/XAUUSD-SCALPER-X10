"""Tests for the Orchestrator daemon."""
import threading
import time
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    yield db
    db.close()


def test_orchestrator_imports():
    from agents.orchestrator import Orchestrator
    assert Orchestrator is not None


def test_register_core_agents(tmp_db):
    from agents.orchestrator import Orchestrator
    orch = Orchestrator(tmp_db)
    orch.register_core_agents()
    agents = tmp_db.fetchall("SELECT name FROM agent_registry")
    names = {row["name"] for row in agents}
    assert "token_manager" in names
    assert "model_router" in names
    assert "data_agent" in names


def test_check_internet():
    from agents.orchestrator import check_internet
    result = check_internet()
    assert isinstance(result, bool)


def test_orchestrator_start_and_stop(tmp_db):
    from agents.orchestrator import Orchestrator
    orch = Orchestrator(tmp_db)
    orch.register_core_agents()
    t = threading.Thread(target=orch.run)
    t.start()
    time.sleep(2)
    orch.shutdown()
    t.join(timeout=10)
    assert not t.is_alive()
