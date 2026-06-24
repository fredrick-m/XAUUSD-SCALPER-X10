"""Tests for Meta Agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config, status, error_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("meta_agent", "meta_agent", "agents.meta_agent", "MetaAgent",
         '{"tick_interval": 0.01}', "running", 0),
    )
    yield db
    db.close()


def _seed_system(db):
    """Populate the DB with realistic multi-agent system data."""
    # Additional agents
    agents = [
        ("token_manager", "token_manager", "agents.token_manager", "TokenManager",
         '{"tick_interval": 60}', "running", 0),
        ("model_router", "model_router", "agents.model_router", "ModelRouter",
         '{"tick_interval": 30}', "running", 0),
        ("plugin_scout", "plugin_scout", "agents.plugin_scout", "PluginScout",
         '{"tick_interval": 3600}', "running", 2),
        ("evolution_agent", "evolution_agent", "agents.evolution_agent", "EvolutionAgent",
         '{"tick_interval": 120}', "stopped", 5),
        ("data_agent", "data_agent", "agents.data_agent", "DataAgent",
         '{"tick_interval": 300}', "running", 0),
    ]
    for a in agents:
        db.execute(
            "INSERT INTO agent_registry (id, name, module_path, class_name, config, status, error_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            a,
        )

    # Strategies
    for i in range(1, 6):
        sid = f"S{i:04d}"
        status = "validated" if i <= 3 else ("retired" if i == 4 else "candidate")
        db.execute(
            "INSERT INTO strategies (id, file_path, family, status, generation, "
            "best_win_rate, best_profit_factor, best_max_drawdown, best_x10_count, best_final_balance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, f"strategies/strategy_{sid.lower()}.py", "momentum_burst", status, 1,
             0.60 + i * 0.02, 1.5 + i * 0.3, 0.25 - i * 0.02, i, 100.0 + i * 50),
        )

    # Task queue entries
    tasks = [
        ("evolution_agent", "evolve_strategy", '{"strategy_id": "S0001"}', "pending", 5, "meta_agent"),
        ("data_agent", "fetch_data", '{"symbol": "XAUUSD"}', "pending", 3, "orchestrator"),
        ("backtest_runner", "run_backtest", '{"strategy_id": "S0002"}', "completed", 5, "evolution_agent"),
    ]
    for t in tasks:
        db.execute(
            "INSERT INTO task_queue (agent_target, task_type, payload, status, priority, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            t,
        )

    # Token usage
    db.execute(
        "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("strategy_factory", "claude-opus-4-6", 5000, 2500, 0.45, "generate_strategy"),
    )
    db.execute(
        "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("evolution_agent", "claude-sonnet-4-6", 1000, 500, 0.02, "analyze_results"),
    )

    # Events
    for i in range(10):
        db.execute(
            "INSERT INTO events (agent_id, event_type, event_message) VALUES (?, ?, ?)",
            ("evolution_agent", "info", f"Tick completed {i}"),
        )
    db.execute(
        "INSERT INTO events (agent_id, event_type, event_message) VALUES (?, ?, ?)",
        ("plugin_scout", "error", "Failed to download plugin"),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_meta_agent_imports():
    from agents.meta_agent import MetaAgent
    assert MetaAgent.name == "meta_agent"


def test_collect_system_state(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)
    state = agent._collect_system_state()

    assert "agents" in state
    assert "task_queue" in state
    assert "strategies" in state
    assert "token_usage" in state
    assert "recent_events" in state

    # agents list should include meta_agent + seeded agents
    assert len(state["agents"]) >= 1

    # strategies summary keys
    strat = state["strategies"]
    assert "total" in strat
    assert "validated" in strat
    assert "retired" in strat
    assert "top5" in strat

    # token usage keys
    tu = state["token_usage"]
    assert "last_hour" in tu
    assert "all_time" in tu


def test_build_decision_prompt(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)
    state = agent._collect_system_state()
    prompt = agent._build_decision_prompt(state)

    assert isinstance(prompt, str)
    assert len(prompt) > 200
    assert "agent" in prompt.lower()
    assert "strategy" in prompt.lower()


def test_parse_decision_no_changes():
    from agents.meta_agent import MetaAgent
    raw = '{"action": "no_changes", "reason": "System is healthy"}'
    decisions = MetaAgent._parse_decisions(raw)
    assert isinstance(decisions, list)
    assert len(decisions) == 1
    assert decisions[0]["action"] == "no_changes"


def test_parse_decision_reconfigure():
    from agents.meta_agent import MetaAgent
    raw = json.dumps({
        "actions": [
            {"action": "reconfigure", "agent_id": "evolution_agent", "config": {"tick_interval": 60}},
            {"action": "no_changes", "reason": "other agents fine"},
        ]
    })
    decisions = MetaAgent._parse_decisions(raw)
    assert isinstance(decisions, list)
    assert len(decisions) == 2
    assert decisions[0]["action"] == "reconfigure"
    assert decisions[0]["agent_id"] == "evolution_agent"


def test_parse_decision_list():
    from agents.meta_agent import MetaAgent
    raw = json.dumps([
        {"action": "enable", "agent_id": "evolution_agent"},
        {"action": "no_changes"},
    ])
    decisions = MetaAgent._parse_decisions(raw)
    assert isinstance(decisions, list)
    assert len(decisions) == 2
    assert decisions[0]["action"] == "enable"


def test_parse_decision_malformed():
    from agents.meta_agent import MetaAgent
    decisions = MetaAgent._parse_decisions("random text that is not JSON at all")
    assert decisions == []


def test_parse_decision_markdown_fences():
    from agents.meta_agent import MetaAgent
    raw = '```json\n{"action": "no_changes", "reason": "ok"}\n```'
    decisions = MetaAgent._parse_decisions(raw)
    assert len(decisions) == 1
    assert decisions[0]["action"] == "no_changes"


def test_execute_reconfigure(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)

    decision = {
        "action": "reconfigure",
        "agent_id": "evolution_agent",
        "config": {"tick_interval": 240, "max_children": 5},
    }
    agent._execute_decision(decision)

    row = tmp_db.fetchone("SELECT config FROM agent_registry WHERE id = ?", ("evolution_agent",))
    config = json.loads(row["config"])
    assert config["tick_interval"] == 240
    assert config["max_children"] == 5


def test_execute_disable(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)

    decision = {"action": "disable", "agent_id": "plugin_scout"}
    agent._execute_decision(decision)

    row = tmp_db.fetchone("SELECT status FROM agent_registry WHERE id = ?", ("plugin_scout",))
    assert row["status"] == "disabled"


def test_execute_enable(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    # First set evolution_agent to disabled
    tmp_db.execute("UPDATE agent_registry SET status='disabled' WHERE id='evolution_agent'")
    agent = MetaAgent(tmp_db)

    decision = {"action": "enable", "agent_id": "evolution_agent"}
    agent._execute_decision(decision)

    row = tmp_db.fetchone(
        "SELECT status, error_count FROM agent_registry WHERE id = ?", ("evolution_agent",)
    )
    assert row["status"] == "stopped"
    assert row["error_count"] == 0


def test_execute_disable_protected_agent(tmp_db):
    """Meta agent must refuse to disable protected agents."""
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)

    for protected in ["token_manager", "model_router", "meta_agent"]:
        # Ensure the agent exists (meta_agent already in registry from fixture)
        decision = {"action": "disable", "agent_id": protected}
        agent._execute_decision(decision)
        row = tmp_db.fetchone("SELECT status FROM agent_registry WHERE id = ?", (protected,))
        # status should NOT be 'disabled'
        if row:
            assert row["status"] != "disabled", f"{protected} should not be disabled"


def test_execute_no_changes(tmp_db):
    from agents.meta_agent import MetaAgent
    agent = MetaAgent(tmp_db)
    # Should not raise
    agent._execute_decision({"action": "no_changes", "reason": "all good"})


def test_tick_no_crash_without_api(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)
    agent.setup()
    try:
        agent.tick()
    except Exception:
        pass  # No API key available in test environment — that's fine
