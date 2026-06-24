"""Tests for core.db module."""
import threading
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database for testing."""
    from core.db import Database
    db_path = tmp_path / "test.sqlite"
    db = Database(db_path)
    db.init_schema()
    yield db
    db.close()


def test_database_creates_file(tmp_path):
    from core.db import Database
    db_path = tmp_path / "test.sqlite"
    db = Database(db_path)
    db.init_schema()
    assert db_path.exists()
    db.close()


def test_schema_creates_all_tables(tmp_db):
    tables = tmp_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row[0] for row in tables}
    expected = {
        "agent_registry", "task_queue", "strategies",
        "backtest_results", "token_usage", "events",
        "data_registry", "plugins",
    }
    assert expected.issubset(table_names)


def test_insert_and_query_agent(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("test1", "test_agent", "agents.test", "TestAgent"),
    )
    row = tmp_db.execute("SELECT name FROM agent_registry WHERE id = ?", ("test1",)).fetchone()
    assert row[0] == "test_agent"


def test_insert_event(tmp_db):
    tmp_db.execute(
        "INSERT INTO events (agent_id, event_type, event_message) VALUES (?, ?, ?)",
        ("agent1", "info", "test event"),
    )
    row = tmp_db.execute("SELECT event_message FROM events WHERE agent_id = ?", ("agent1",)).fetchone()
    assert row[0] == "test event"


def test_insert_token_usage(tmp_db):
    tmp_db.execute(
        "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("agent1", "claude-haiku-4-5-20251001", 100, 200, 0.001, "test"),
    )
    row = tmp_db.execute("SELECT cost_usd FROM token_usage WHERE agent_id = ?", ("agent1",)).fetchone()
    assert row[0] == 0.001


def test_concurrent_writes(tmp_db):
    """Verify WAL mode allows concurrent writes without errors."""
    errors = []

    def writer(agent_id):
        try:
            for i in range(20):
                tmp_db.execute(
                    "INSERT INTO events (agent_id, event_type, event_message) VALUES (?, ?, ?)",
                    (agent_id, "info", f"msg {i}"),
                )
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(f"agent_{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    count = tmp_db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 80


def test_upsert_agent_heartbeat(tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name) VALUES (?, ?, ?, ?)",
        ("a1", "agent1", "agents.a1", "A1"),
    )
    tmp_db.update_heartbeat("a1")
    row = tmp_db.execute("SELECT last_heartbeat FROM agent_registry WHERE id = ?", ("a1",)).fetchone()
    assert row[0] is not None
