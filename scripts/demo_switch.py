"""Explicit master switch for NEW MT5 demo entries.

``enable`` requires an explicit risk profile and runs the full preflight first.
If any prerequisite fails, the switch remains OFF. ``disable`` is immediate
and never force-closes existing demo positions; it only prevents new entries.

Usage:
    python scripts/demo_switch.py status
    python scripts/demo_switch.py enable --profile conservative
    python scripts/demo_switch.py enable --profile growth
    python scripts/demo_switch.py enable --profile x10_research
    python scripts/demo_switch.py disable
"""
from __future__ import annotations

import argparse
import json
import sys

from agents.risk_manager import RISK_PROFILES
from core.config import DB_PATH
from core.db import Database
from scripts.demo_preflight import print_results, run_preflight


def _read_config(db: Database) -> dict:
    row = db.fetchone("SELECT config FROM agent_registry WHERE id='risk_manager'")
    if not row:
        return {}
    raw = row["config"]
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write_config(db: Database, config: dict) -> None:
    db.execute(
        "UPDATE agent_registry SET config=? WHERE id='risk_manager'",
        (json.dumps(config),),
    )


def _registered(db: Database) -> bool:
    return db.fetchone("SELECT id FROM agent_registry WHERE id='risk_manager'") is not None


def status(db: Database) -> int:
    if not _registered(db):
        print("DEMO EXECUTION: OFF — risk_manager is not registered")
        return 2
    cfg = _read_config(db)
    enabled = cfg.get("demo_execution_enabled") is True
    profile = cfg.get("risk_profile", "x10_research")
    profile_cfg = RISK_PROFILES.get(profile, RISK_PROFILES["x10_research"])
    print(f"DEMO EXECUTION: {'ON' if enabled else 'OFF'}")
    print(
        f"RISK PROFILE: {profile} | base/trade={profile_cfg['risk_per_trade']:.2%} "
        f"dailyDD={profile_cfg['max_daily_dd']:.0%} weeklyDD={profile_cfg['max_weekly_dd']:.0%}"
    )
    return 0 if enabled else 2


def disable(db: Database) -> int:
    if not _registered(db):
        print("DEMO EXECUTION already effectively OFF — risk_manager not registered")
        return 0
    cfg = _read_config(db)
    cfg["demo_execution_enabled"] = False
    _write_config(db, cfg)
    db.execute(
        "INSERT INTO events (agent_id,event_type,event_message,metadata) VALUES (?,?,?,?)",
        (
            "demo_switch", "warning", "Demo execution master switch DISABLED",
            json.dumps({"demo_execution_enabled": False}),
        ),
    )
    print("DEMO EXECUTION: OFF")
    print("New entries are blocked. Existing demo positions are not force-closed.")
    return 0


def enable(db: Database, profile: str) -> int:
    if not _registered(db):
        print("BLOCKED: risk_manager is not registered. Start/register the system first.")
        return 2
    if profile not in RISK_PROFILES:
        print(f"BLOCKED: unknown risk profile {profile}")
        return 2

    # Force OFF and persist the explicitly chosen profile before checking, so
    # preflight reports the exact risk budget the user is about to enable.
    cfg = _read_config(db)
    cfg["demo_execution_enabled"] = False
    cfg["risk_profile"] = profile
    _write_config(db, cfg)

    profile_cfg = RISK_PROFILES[profile]
    print(
        f"Requested profile: {profile} | base risk/trade={profile_cfg['risk_per_trade']:.2%} | "
        f"daily DD lock={profile_cfg['max_daily_dd']:.0%} | "
        f"weekly DD lock={profile_cfg['max_weekly_dd']:.0%}"
    )

    ready, results = run_preflight(db)
    print_results(ready, results)
    if not ready:
        print("DEMO EXECUTION remains OFF. No order was sent.")
        return 2

    cfg = _read_config(db)
    cfg["risk_profile"] = profile
    cfg["demo_execution_enabled"] = True
    _write_config(db, cfg)

    from agents.risk_manager import get_risk_readiness
    risk_ready, reason = get_risk_readiness(db)
    if not risk_ready:
        cfg = _read_config(db)
        cfg["demo_execution_enabled"] = False
        _write_config(db, cfg)
        print(f"BLOCKED after switch verification: {reason}. Switch returned to OFF.")
        return 2

    db.execute(
        "INSERT INTO events (agent_id,event_type,event_message,metadata) VALUES (?,?,?,?)",
        (
            "demo_switch", "milestone", "Demo execution master switch ENABLED after preflight",
            json.dumps({
                "demo_execution_enabled": True,
                "risk_profile": profile,
                "risk_per_trade": profile_cfg["risk_per_trade"],
                "preflight": "passed",
            }),
        ),
    )
    print("DEMO EXECUTION: ON")
    print(f"ACTIVE PROFILE: {profile} ({profile_cfg['risk_per_trade']:.2%} base risk/trade)")
    print("Only NEW orders that pass every runtime gate can now be sent to the MT5 demo account.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MT5 demo execution master switch")
    parser.add_argument("action", choices=("status", "enable", "disable"))
    parser.add_argument(
        "--profile",
        choices=tuple(RISK_PROFILES),
        help="Required with enable; explicit risk profile to activate.",
    )
    args = parser.parse_args()

    if args.action == "enable" and not args.profile:
        parser.error("enable requires --profile conservative|growth|x10_research")

    db = Database(DB_PATH)
    try:
        db.init_schema()
        if args.action == "enable":
            return enable(db, args.profile)
        if args.action == "disable":
            return disable(db)
        return status(db)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
