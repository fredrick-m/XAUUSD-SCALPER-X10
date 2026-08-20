import json
from datetime import datetime, timezone

from agents.signal_gatekeeper import SignalGatekeeper
from core.db import Database


def _gate(db):
    g = SignalGatekeeper.__new__(SignalGatekeeper)
    g.db = db
    g.agent_id = "signal_gatekeeper"
    g.logger = __import__("logging").getLogger("test.demo_safety")
    return g


def _insert_agent(db, agent_id, config):
    db.execute(
        "INSERT INTO agent_registry "
        "(id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        (agent_id, agent_id, f"agents.{agent_id}", "TestAgent", json.dumps(config)),
    )


def test_unverified_calendar_blocks_new_entry(tmp_path):
    db = Database(tmp_path / "gate.sqlite")
    try:
        db.init_schema()
        _insert_agent(
            db,
            "news_calendar",
            {
                "calendar_verified": False,
                "calendar_source": "static_fallback",
                "last_fetch": datetime.now(timezone.utc).isoformat(),
                "blackout_windows": [],
            },
        )
        allowed, reason = _gate(db)._check_news_blackout({})
        assert allowed is False
        assert reason == "news_calendar_unverified (static_fallback)"
    finally:
        db.close()


def test_fresh_verified_calendar_without_blackout_allows_news_gate(tmp_path):
    db = Database(tmp_path / "gate.sqlite")
    try:
        db.init_schema()
        _insert_agent(
            db,
            "news_calendar",
            {
                "calendar_verified": True,
                "calendar_source": "forex_factory",
                "last_fetch": datetime.now(timezone.utc).isoformat(),
                "blackout_windows": [],
            },
        )
        allowed, reason = _gate(db)._check_news_blackout({})
        assert allowed is True
        assert reason == "ok"
    finally:
        db.close()


def test_minimum_lot_is_blocked_when_it_exceeds_effective_risk_budget(tmp_path):
    db = Database(tmp_path / "gate.sqlite")
    try:
        db.init_schema()
        _insert_agent(
            db,
            "risk_manager",
            {
                "demo_execution_enabled": True,
                "risk_profile": "conservative",
                "risk_state": {
                    "equity_ready": True,
                    "circuit_breaker_active": False,
                    "current_scaling": 1.0,
                },
            },
        )
        # $500 equity at 1% risk => $5 budget. 0.01 lot with a $6 stop has
        # $6 risk at PIP_VALUE=100, so the broker minimum is too large.
        allowed, reason = _gate(db)._check_per_trade_risk(
            {"equity": 500.0, "lot": 0.01, "sl_distance": 6.0}
        )
        assert allowed is False
        assert reason.startswith("per_trade_risk_exceeded")
    finally:
        db.close()


def test_order_within_effective_risk_budget_passes(tmp_path):
    db = Database(tmp_path / "gate.sqlite")
    try:
        db.init_schema()
        _insert_agent(
            db,
            "risk_manager",
            {
                "demo_execution_enabled": True,
                "risk_profile": "growth",
                "risk_state": {
                    "equity_ready": True,
                    "circuit_breaker_active": False,
                    "current_scaling": 0.5,
                },
            },
        )
        # Growth 2% * 0.5 stress = 1% effective => $5 on $500.
        # 0.01 lot * $4 stop * 100 = $4 risk.
        allowed, reason = _gate(db)._check_per_trade_risk(
            {"equity": 500.0, "lot": 0.01, "sl_distance": 4.0}
        )
        assert allowed is True
        assert reason == "ok"
    finally:
        db.close()
