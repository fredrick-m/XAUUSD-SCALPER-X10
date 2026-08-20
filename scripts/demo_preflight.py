"""Fail-closed readiness check before enabling MT5 demo execution.

This script NEVER sends an order and does NOT enable execution. It checks the
prerequisites that must be true before ``scripts/demo_switch.py enable`` can
turn on new MT5 demo entries.

Usage:
    python scripts/demo_preflight.py

Exit codes:
    0 = READY TO ENABLE
    2 = BLOCKED
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from core.config import BACKTEST_METRIC_VERSION, DB_PATH
from core.db import Database

NEWS_MAX_AGE_MINUTES = 90
MC_MODEL = "fixed_fraction_edge_model_v2"


def _json(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _table_exists(db: Database, name: str) -> bool:
    row = db.fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return row is not None


def _check_metric_migration(db: Database) -> tuple[bool, str]:
    if not _table_exists(db, "metric_migrations"):
        return False, "metric migration not applied"
    row = db.fetchone(
        "SELECT metric_version FROM metric_migrations WHERE metric_version=?",
        (BACKTEST_METRIC_VERSION,),
    )
    if not row:
        return False, f"migration {BACKTEST_METRIC_VERSION} not applied"
    return True, BACKTEST_METRIC_VERSION


def _check_active_results_version(db: Database) -> tuple[bool, str]:
    rows = db.fetchall("SELECT config FROM backtest_results")
    if not rows:
        return False, "no active V2 backtest results"
    stale = 0
    for row in rows:
        cfg = _json(row["config"])
        if cfg.get("metric_version") != BACKTEST_METRIC_VERSION:
            stale += 1
    if stale:
        return False, f"{stale} active backtest result(s) have stale/missing metric version"
    return True, f"{len(rows)} active result(s) on {BACKTEST_METRIC_VERSION}"


def _strategy_proof_reason(cfg: dict) -> str | None:
    if cfg.get("metric_version") != BACKTEST_METRIC_VERSION:
        return "stale_metric_version"
    if cfg.get("metric_refresh_pending", True):
        return "metric_refresh_pending"

    validation = cfg.get("validation_v2")
    if not isinstance(validation, dict) or not validation.get("passed", False):
        return "validation_v2_missing_or_failed"
    if not validation.get("walk_forward", {}).get("passed", False):
        return "walk_forward_v2_failed"
    if not validation.get("holdout_available", False):
        return "locked_holdout_unavailable"
    if not validation.get("holdout", {}).get("passed", False):
        return "locked_holdout_failed"

    mc = cfg.get("monte_carlo")
    if not isinstance(mc, dict) or mc.get("model") != MC_MODEL:
        return "monte_carlo_v2_missing"
    try:
        ruin = float(mc.get("p_ruin_10d", mc.get("p_ruin")))
    except (TypeError, ValueError):
        return "monte_carlo_ruin_missing_or_invalid"
    if ruin > 0.10:
        return "monte_carlo_ruin_too_high"

    sensitivity = cfg.get("sensitivity")
    if not cfg.get("sensitivity_tested", False) or not isinstance(sensitivity, dict):
        return "sensitivity_missing"
    if sensitivity.get("is_fragile", False):
        return "sensitivity_fragile"

    statistical = cfg.get("statistical_evidence")
    if not isinstance(statistical, dict) or not statistical.get("passed", False):
        return "statistical_evidence_missing_or_failed"

    stability = cfg.get("chronological_stability")
    if not isinstance(stability, dict) or not stability.get("passed", False):
        return "chronological_stability_missing_or_failed"
    if not stability.get("locked_holdout_excluded", False):
        return "stability_reused_locked_holdout"

    if cfg.get("portfolio_selected") is not True:
        return "portfolio_not_selected"
    return None


def _check_portfolio(db: Database) -> tuple[bool, str]:
    rows = db.fetchall(
        "SELECT id, best_config FROM strategies "
        "WHERE status='validated' AND walk_forward_passed=1"
    )
    if not rows:
        return False, "no validated+WF strategy"

    ready = []
    blocked = []
    for row in rows:
        reason = _strategy_proof_reason(_json(row["best_config"]))
        if reason is None:
            ready.append(row["id"])
        else:
            blocked.append(f"{row['id']}:{reason}")

    if not ready:
        sample = ", ".join(blocked[:5])
        return False, f"0 Portfolio V5-ready strategies ({sample})"
    return True, f"{len(ready)} Portfolio V5-ready strategy/strategies: {', '.join(ready[:8])}"


def _check_news(db: Database) -> tuple[bool, str]:
    row = db.fetchone("SELECT config FROM agent_registry WHERE id='news_calendar'")
    if not row:
        return False, "news_calendar agent not registered"
    cfg = _json(row["config"])
    if cfg.get("calendar_verified") is not True:
        return False, f"calendar unverified ({cfg.get('calendar_source', 'unknown')})"
    last_fetch = cfg.get("last_fetch")
    if not last_fetch:
        return False, "calendar never fetched"
    try:
        fetched = datetime.fromisoformat(last_fetch)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - fetched).total_seconds() / 60.0
    except Exception:
        return False, "calendar timestamp invalid"
    if age < 0 or age > NEWS_MAX_AGE_MINUTES:
        return False, f"calendar stale ({age:.0f} minutes)"

    try:
        from agents.news_calendar import is_blackout_period
        if is_blackout_period(db):
            return False, "active high-impact USD news blackout"
    except Exception as exc:
        return False, f"calendar blackout check failed: {exc}"
    return True, f"verified calendar fresh ({age:.0f} minutes old)"


def _check_risk(db: Database) -> tuple[bool, str]:
    """Check risk health without requiring the deliberate execution switch ON."""
    try:
        from agents.risk_manager import RISK_PROFILES, DEFAULT_RISK_PROFILE
        row = db.fetchone("SELECT config FROM agent_registry WHERE id='risk_manager'")
        if not row:
            return False, "risk_manager agent not registered"
        cfg = _json(row["config"])
        state = cfg.get("risk_state", {})
        if not state:
            return False, "risk state missing"
        if not state.get("equity_ready", False):
            return False, "MT5 equity not anchored"
        if state.get("equity_anchor_source") != "mt5":
            return False, "equity anchor is not MT5"
        if state.get("circuit_breaker_active", False):
            return False, f"circuit breaker active ({state.get('circuit_breaker_scope', 'unknown')})"
        equity = float(state.get("current_equity") or 0.0)
        if equity <= 0:
            return False, "current risk equity invalid"
        scaling = float(state.get("current_scaling") or 0.0)
        if scaling <= 0:
            return False, "risk scaling is zero"
        profile_name = cfg.get("risk_profile", DEFAULT_RISK_PROFILE)
        profile = RISK_PROFILES.get(profile_name, RISK_PROFILES[DEFAULT_RISK_PROFILE])
        potential_risk = float(profile["risk_per_trade"]) * scaling
        enabled = cfg.get("demo_execution_enabled") is True
        return True, (
            f"Risk Engine healthy; potential risk/trade={potential_risk:.2%}; "
            f"execution switch={'ON' if enabled else 'OFF (safe)'}"
        )
    except Exception as exc:
        return False, f"Risk Engine check failed: {exc}"


def _check_mt5() -> tuple[bool, str]:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return False, "MetaTrader5 Python package not installed"

    if not mt5.initialize():
        return False, f"MT5 initialize failed: {mt5.last_error()}"
    try:
        account = mt5.account_info()
        if account is None:
            return False, f"MT5 account_info unavailable: {mt5.last_error()}"
        if int(getattr(account, "trade_mode", -1)) != 0:
            return False, f"account is NOT demo (trade_mode={getattr(account, 'trade_mode', None)})"
        equity = float(getattr(account, "equity", 0.0) or 0.0)
        balance = float(getattr(account, "balance", 0.0) or 0.0)
        if equity <= 0 or balance <= 0:
            return False, f"invalid demo equity/balance ({equity}/{balance})"
        if hasattr(account, "trade_allowed") and not bool(account.trade_allowed):
            return False, "account trade_allowed is false"
        if hasattr(account, "trade_expert") and not bool(account.trade_expert):
            return False, "account automated trading is disabled"
        if not mt5.symbol_select("XAUUSD", True):
            return False, f"XAUUSD symbol_select failed: {mt5.last_error()}"
        info = mt5.symbol_info("XAUUSD")
        tick = mt5.symbol_info_tick("XAUUSD")
        if info is None or tick is None:
            return False, "XAUUSD symbol/tick unavailable"
        if float(getattr(tick, "ask", 0.0) or 0.0) <= 0 or float(getattr(tick, "bid", 0.0) or 0.0) <= 0:
            return False, "XAUUSD bid/ask invalid"
        return True, (
            f"demo account #{getattr(account, 'login', '?')} equity=${equity:.2f} "
            f"balance=${balance:.2f} XAUUSD={tick.bid:.2f}/{tick.ask:.2f}"
        )
    finally:
        mt5.shutdown()


def run_preflight(db: Database) -> tuple[bool, list[tuple[str, bool, str]]]:
    checks = [
        ("metric_migration", _check_metric_migration),
        ("active_backtests", _check_active_results_version),
        ("portfolio_v5", _check_portfolio),
        ("news_calendar", _check_news),
        ("risk_engine", _check_risk),
    ]
    results = []
    for name, fn in checks:
        try:
            ok, detail = fn(db)
        except Exception as exc:
            ok, detail = False, f"unexpected error: {exc}"
        results.append((name, bool(ok), str(detail)))
    try:
        mt5_ok, mt5_detail = _check_mt5()
    except Exception as exc:
        mt5_ok, mt5_detail = False, f"unexpected error: {exc}"
    results.append(("mt5_demo", bool(mt5_ok), str(mt5_detail)))
    return all(ok for _, ok, _ in results), results


def print_results(ready: bool, results: list[tuple[str, bool, str]]) -> None:
    print("=" * 68)
    print(f"DEMO PREFLIGHT: {'READY TO ENABLE' if ready else 'BLOCKED'}")
    print("=" * 68)
    for name, ok, detail in results:
        print(f"[{'OK' if ok else 'BLOCK'}] {name}: {detail}")
    print("=" * 68)


def main() -> int:
    db = Database(DB_PATH)
    try:
        db.init_schema()
        ready, results = run_preflight(db)
    finally:
        db.close()
    print_results(ready, results)
    if ready:
        print("No order was sent and execution was NOT enabled.")
        return 0
    print("No order was sent. Fix every BLOCK item before enabling demo execution.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
