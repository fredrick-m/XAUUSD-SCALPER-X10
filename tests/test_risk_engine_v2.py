import logging

from agents.risk_manager import (
    RISK_PROFILES,
    RiskManager,
    get_position_scaling,
    get_risk_readiness,
)
from core.db import Database


def _manager(db):
    mgr = RiskManager.__new__(RiskManager)
    mgr.db = db
    mgr.agent_id = "risk_manager"
    mgr.logger = logging.getLogger("test.risk_manager")
    mgr.emit_event = lambda *args, **kwargs: None
    return mgr


def test_missing_equity_state_fails_closed(tmp_path):
    db = Database(tmp_path / "risk.sqlite")
    try:
        db.init_schema()
        db.execute(
            "INSERT INTO agent_registry "
            "(id, name, module_path, class_name, config) "
            "VALUES ('risk_manager','risk_manager','agents.risk_manager','RiskManager','{}')"
        )

        ready, reason = get_risk_readiness(db)
        assert ready is False
        assert reason == "risk_state_missing"
        assert get_position_scaling(db) == 0.0
    finally:
        db.close()


def test_weekly_breaker_promotes_existing_daily_lock(tmp_path):
    db = Database(tmp_path / "risk.sqlite")
    try:
        db.init_schema()
        mgr = _manager(db)
        profile = RISK_PROFILES["x10_research"]
        state = {
            "circuit_breaker_active": True,
            "circuit_breaker_reason": "daily_dd",
            "circuit_breaker_scope": "daily",
            "daily_drawdown": profile["max_daily_dd"] + 0.01,
            "weekly_drawdown": profile["max_weekly_dd"] + 0.01,
            "current_scaling": 0.0,
        }

        mgr._evaluate_breakers(state, profile)

        assert state["circuit_breaker_active"] is True
        assert state["circuit_breaker_scope"] == "weekly"
        assert state["circuit_breaker_reason"] == "weekly_dd"
    finally:
        db.close()


def test_readiness_lock_blocks_position_scaling(tmp_path):
    db = Database(tmp_path / "risk.sqlite")
    try:
        db.init_schema()
        db.execute(
            "INSERT INTO agent_registry "
            "(id, name, module_path, class_name, config) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "risk_manager",
                "risk_manager",
                "agents.risk_manager",
                "RiskManager",
                '{"risk_profile":"x10_research","risk_state":'
                '{"equity_ready":false,"circuit_breaker_active":true,'
                '"circuit_breaker_scope":"readiness","current_scaling":0.0}}',
            ),
        )

        ready, reason = get_risk_readiness(db)
        assert ready is False
        assert reason == "mt5_equity_unavailable"
        assert get_position_scaling(db) == 0.0
    finally:
        db.close()


def test_ready_state_allows_profile_scaling(tmp_path):
    db = Database(tmp_path / "risk.sqlite")
    try:
        db.init_schema()
        db.execute(
            "INSERT INTO agent_registry "
            "(id, name, module_path, class_name, config) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "risk_manager",
                "risk_manager",
                "agents.risk_manager",
                "RiskManager",
                '{"risk_profile":"x10_research","risk_state":'
                '{"equity_ready":true,"circuit_breaker_active":false,'
                '"current_scaling":0.5}}',
            ),
        )

        ready, reason = get_risk_readiness(db)
        assert ready is True
        assert reason == "ready"
        assert get_position_scaling(db) == 0.5
    finally:
        db.close()
