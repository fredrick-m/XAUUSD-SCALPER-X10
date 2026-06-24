"""Tests for core.logger module."""
import logging
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    yield db
    db.close()


def test_get_logger_returns_logger():
    from core.logger import get_logger
    log = get_logger("test_agent")
    assert isinstance(log, logging.Logger)
    assert log.name == "agent.test_agent"


def test_log_event_writes_to_db(tmp_db):
    from core.logger import log_event
    log_event(tmp_db, "agent1", "info", "hello world", {"key": "val"})
    row = tmp_db.fetchone("SELECT * FROM events WHERE agent_id = ?", ("agent1",))
    assert row["event_message"] == "hello world"
    assert row["event_type"] == "info"


def test_log_event_without_metadata(tmp_db):
    from core.logger import log_event
    log_event(tmp_db, "agent1", "warning", "something happened")
    row = tmp_db.fetchone("SELECT * FROM events WHERE agent_id = ?", ("agent1",))
    assert row["event_message"] == "something happened"
    assert row["metadata"] is None
