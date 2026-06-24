"""Tests for agents.base_agent."""
import time
import threading
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    yield db
    db.close()


def _make_agent_class():
    from agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        name = "test_agent"

        def __init__(self, db):
            super().__init__(agent_id="test1", db=db)
            self.tick_count = 0
            self.setup_called = False
            self.cleanup_called = False

        def setup(self):
            self.setup_called = True

        def tick(self):
            self.tick_count += 1
            if self.tick_count >= 3:
                self.request_shutdown()

        def tick_interval(self) -> float:
            return 0.01

        def cleanup(self):
            self.cleanup_called = True

    return TestAgent


def test_agent_lifecycle(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "tests", "TestAgent"),
    )
    AgentClass = _make_agent_class()
    agent = AgentClass(tmp_db)
    t = threading.Thread(target=agent.run)
    t.start()
    t.join(timeout=5)
    assert agent.setup_called
    assert agent.cleanup_called
    assert agent.tick_count >= 3


def test_agent_emits_event(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "tests", "TestAgent"),
    )
    AgentClass = _make_agent_class()
    agent = AgentClass(tmp_db)
    agent.emit_event("info", "hello from test")
    row = tmp_db.fetchone("SELECT event_message FROM events WHERE agent_id = ?", ("test1",))
    assert row["event_message"] == "hello from test"


def test_agent_posts_task(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "tests", "TestAgent"),
    )
    AgentClass = _make_agent_class()
    agent = AgentClass(tmp_db)
    agent.post_task("backtest_runner", "backtest", {"strategy_id": "S001"})
    row = tmp_db.fetchone("SELECT * FROM task_queue WHERE agent_target = ?", ("backtest_runner",))
    assert row["task_type"] == "backtest"


def test_agent_heartbeat_updates(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "tests", "TestAgent"),
    )
    AgentClass = _make_agent_class()
    agent = AgentClass(tmp_db)
    agent.update_heartbeat()
    row = tmp_db.fetchone("SELECT last_heartbeat FROM agent_registry WHERE id = ?", ("test1",))
    assert row["last_heartbeat"] is not None
