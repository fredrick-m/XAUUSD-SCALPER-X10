import json

from agents.signal_gatekeeper import SignalGatekeeper
from core.config import BACKTEST_METRIC_VERSION
from core.db import Database


def _good_config():
    return {
        "metric_version": BACKTEST_METRIC_VERSION,
        "metric_refresh_pending": False,
        "validation_v2": {
            "passed": True,
            "holdout_available": True,
            "walk_forward": {"passed": True},
            "holdout": {"passed": True},
        },
        "monte_carlo": {
            "model": "fixed_fraction_edge_model_v2",
            "p_ruin_10d": 0.05,
        },
        "sensitivity_tested": True,
        "sensitivity": {"is_fragile": False},
        "statistical_evidence": {"passed": True},
        "chronological_stability": {
            "passed": True,
            "locked_holdout_excluded": True,
        },
        "portfolio_selected": True,
    }


def _gate(db):
    g = SignalGatekeeper.__new__(SignalGatekeeper)
    g.db = db
    g.agent_id = "signal_gatekeeper"
    g.logger = __import__("logging").getLogger("test.signal_gatekeeper")
    return g


def _insert_strategy(db, config):
    db.execute(
        "INSERT INTO strategies "
        "(id, file_path, status, walk_forward_passed, best_config) "
        "VALUES (?, ?, 'validated', 1, ?)",
        ("S1", "strategies/s1.py", json.dumps(config)),
    )


def test_deployment_evidence_allows_complete_portfolio_v5_proof(tmp_path):
    db = Database(tmp_path / "gate.sqlite")
    try:
        db.init_schema()
        _insert_strategy(db, _good_config())
        allowed, reason = _gate(db)._check_deployment_evidence({"strategy_id": "S1"})
        assert allowed is True
        assert reason == "ok"
    finally:
        db.close()


def test_deployment_evidence_blocks_stale_portfolio_selection(tmp_path):
    db = Database(tmp_path / "gate.sqlite")
    try:
        db.init_schema()
        cfg = _good_config()
        cfg["portfolio_selected"] = False
        _insert_strategy(db, cfg)
        allowed, reason = _gate(db)._check_deployment_evidence({"strategy_id": "S1"})
        assert allowed is False
        assert reason == "portfolio_not_selected"
    finally:
        db.close()


def test_deployment_evidence_blocks_missing_monte_carlo(tmp_path):
    db = Database(tmp_path / "gate.sqlite")
    try:
        db.init_schema()
        cfg = _good_config()
        cfg.pop("monte_carlo")
        _insert_strategy(db, cfg)
        allowed, reason = _gate(db)._check_deployment_evidence({"strategy_id": "S1"})
        assert allowed is False
        assert reason == "monte_carlo_v2_missing"
    finally:
        db.close()


def test_deployment_evidence_blocks_stability_that_reuses_holdout(tmp_path):
    db = Database(tmp_path / "gate.sqlite")
    try:
        db.init_schema()
        cfg = _good_config()
        cfg["chronological_stability"]["locked_holdout_excluded"] = False
        _insert_strategy(db, cfg)
        allowed, reason = _gate(db)._check_deployment_evidence({"strategy_id": "S1"})
        assert allowed is False
        assert reason == "stability_reused_locked_holdout"
    finally:
        db.close()
