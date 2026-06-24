"""Tests for Evolution Agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("evolution_agent", "evolution_agent", "agents.evolution_agent", "EvolutionAgent",
         '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def _seed_strategies(db, count=5):
    """Insert dummy strategies with backtest results for testing."""
    for i in range(1, count + 1):
        sid = f"S{i:04d}"
        db.execute(
            "INSERT INTO strategies (id, file_path, family, status, generation, "
            "best_win_rate, best_profit_factor, best_max_drawdown, best_x10_count, best_final_balance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, f"strategies/strategy_{sid.lower()}.py", "momentum_burst", "candidate", 1,
             0.60 + i * 0.02, 1.5 + i * 0.3, 0.25 - i * 0.02, i, 100.0 + i * 50),
        )
        db.execute(
            "INSERT INTO backtest_results "
            "(strategy_id, risk_pct, total_trades, win_rate, profit_factor, "
            "max_drawdown, x10_count, final_balance, return_pct, blown_account) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, 0.05, 300, 0.60 + i * 0.02, 1.5 + i * 0.3,
             0.25 - i * 0.02, i, 100.0 + i * 50, (100.0 + i * 50 - 50) / 50 * 100, 0),
        )


def test_evolution_agent_imports():
    from agents.evolution_agent import EvolutionAgent
    assert EvolutionAgent.name == "evolution_agent"


def test_select_top_strategies(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    _seed_strategies(tmp_db, count=5)
    agent = EvolutionAgent(tmp_db)
    top = agent._select_top_strategies(limit=3)
    assert len(top) == 3
    # Should be sorted by composite score descending
    assert top[0]["id"] == "S0005"  # highest metrics


def test_composite_score_used(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    from engine.optimizer import composite_score
    _seed_strategies(tmp_db, count=3)
    agent = EvolutionAgent(tmp_db)
    top = agent._select_top_strategies(limit=3)
    # Verify each row has a 'score' key
    for row in top:
        assert "score" in row
        assert isinstance(row["score"], float)


def test_mutate_params():
    from agents.evolution_agent import EvolutionAgent
    params = {"ema_fast": 5.0, "ema_slow": 20.0, "sl_atr": 1.5, "tp_atr": 3.0}
    mutated = EvolutionAgent._mutate_params(params, mutation_rate=1.0, mutation_range=0.2)
    # All params should be mutated (rate=1.0) but keys preserved
    assert set(mutated.keys()) == set(params.keys())
    # At least one param should differ (extremely unlikely all stay the same at rate 1.0)
    assert mutated != params


def test_mutate_params_preserves_positive():
    from agents.evolution_agent import EvolutionAgent
    params = {"sl_atr": 0.1}
    # Even with heavy mutation, values should stay positive
    for _ in range(20):
        mutated = EvolutionAgent._mutate_params(params, mutation_rate=1.0, mutation_range=0.5)
        assert mutated["sl_atr"] > 0


def test_crossover_params():
    from agents.evolution_agent import EvolutionAgent
    parent_a = {"ema_fast": 3.0, "ema_slow": 8.0, "sl_atr": 1.5, "tp_atr": 2.5}
    parent_b = {"ema_fast": 5.0, "ema_slow": 20.0, "sl_atr": 2.0, "tp_atr": 4.0}
    child = EvolutionAgent._crossover_params(parent_a, parent_b)
    # Child should have all keys from parent_a
    assert set(child.keys()) == set(parent_a.keys())
    # Each value should come from one of the parents
    for key in child:
        assert child[key] in (parent_a[key], parent_b[key])


def test_next_evolution_id(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    agent = EvolutionAgent(tmp_db)
    eid = agent._next_evolution_id()
    assert eid == "E0001"
    # Simulate one existing
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status, generation) VALUES (?, ?, ?, ?, ?)",
        ("E0001", "strategies/strategy_e0001.py", "evolved", "candidate", 2),
    )
    eid2 = agent._next_evolution_id()
    assert eid2 == "E0002"


def test_retire_poor_strategies(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    # Insert a strategy with 3 failed backtest runs
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status, generation) VALUES (?, ?, ?, ?, ?)",
        ("POOR1", "strategies/strategy_poor1.py", "test", "candidate", 3),
    )
    for _ in range(3):
        tmp_db.execute(
            "INSERT INTO backtest_results "
            "(strategy_id, risk_pct, total_trades, win_rate, profit_factor, "
            "max_drawdown, x10_count, final_balance, return_pct, blown_account) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("POOR1", 0.05, 50, 0.30, 0.5, 0.80, 0, 10.0, -80.0, 0),
        )
    agent = EvolutionAgent(tmp_db)
    retired = agent._retire_poor_strategies(min_runs=3, max_score=0.3)
    assert "POOR1" in retired


def test_tick_no_crash_empty_db(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    agent = EvolutionAgent(tmp_db)
    agent.setup()
    agent.tick()  # Should not crash with no strategies
