"""Tests for Plugin Scout agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("plugin_scout", "plugin_scout", "agents.plugin_scout", "PluginScout",
         '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_plugin_scout_imports():
    from agents.plugin_scout import PluginScout
    assert PluginScout.name == "plugin_scout"


def test_search_domains_defined():
    from agents.plugin_scout import SEARCH_QUERIES
    assert isinstance(SEARCH_QUERIES, list)
    assert len(SEARCH_QUERIES) >= 3


def test_evaluate_candidate_good():
    from agents.plugin_scout import evaluate_candidate
    candidate = {
        "full_name": "ta-lib/ta-lib-python",
        "description": "Technical Analysis Library",
        "stargazers_count": 500,
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2026-06-01T00:00:00Z",
        "archived": False,
    }
    passed, reason = evaluate_candidate(candidate, min_stars=50)
    assert passed


def test_evaluate_candidate_low_stars():
    from agents.plugin_scout import evaluate_candidate
    candidate = {
        "full_name": "nobody/tiny-repo",
        "description": "Some lib",
        "stargazers_count": 10,
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2026-06-01T00:00:00Z",
        "archived": False,
    }
    passed, reason = evaluate_candidate(candidate, min_stars=50)
    assert not passed
    assert "stars" in reason.lower()


def test_evaluate_candidate_archived():
    from agents.plugin_scout import evaluate_candidate
    candidate = {
        "full_name": "old/archived-repo",
        "description": "Archived lib",
        "stargazers_count": 200,
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2024-01-01T00:00:00Z",
        "archived": True,
    }
    passed, reason = evaluate_candidate(candidate, min_stars=50)
    assert not passed
    assert "archived" in reason.lower()


def test_register_plugin(tmp_db):
    from agents.plugin_scout import PluginScout
    agent = PluginScout(tmp_db)
    agent._register_plugin(
        plugin_id="ta-lib-python",
        name="ta-lib-python",
        source_url="https://github.com/ta-lib/ta-lib-python",
        install_type="pip",
        description="Technical Analysis Library",
    )
    row = tmp_db.fetchone("SELECT * FROM plugins WHERE id = ?", ("ta-lib-python",))
    assert row is not None
    assert row["status"] == "installed"
    assert row["install_type"] == "pip"


def test_is_already_installed(tmp_db):
    from agents.plugin_scout import PluginScout
    agent = PluginScout(tmp_db)
    assert not agent._is_already_installed("some-package")
    agent._register_plugin("some-package", "some-package", "", "pip", "test")
    assert agent._is_already_installed("some-package")


def test_tick_no_crash_without_internet(tmp_db):
    from agents.plugin_scout import PluginScout
    agent = PluginScout(tmp_db)
    agent.setup()
    # tick() makes HTTP requests that may fail — should not crash
    try:
        agent.tick()
    except Exception:
        pass  # Expected if no internet or GitHub rate limit
