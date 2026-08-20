"""Safe entry point for the XAUUSD multi-agent system.

Startup always forces NEW demo execution OFF. Research, backtesting, Monte
Carlo, sensitivity and portfolio selection may continue, while paper_trade is
blocked by Risk Engine until ``python scripts/demo_switch.py enable`` passes the
full preflight.

Usage:
    python run_system.py
"""
from __future__ import annotations

import json
import signal

from agents.orchestrator import Orchestrator
from core.config import DB_PATH
from core.db import Database


def _force_demo_off(db: Database) -> None:
    row = db.fetchone("SELECT config FROM agent_registry WHERE id='risk_manager'")
    if not row:
        return
    config = {}
    if row["config"]:
        try:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else dict(row["config"])
        except (json.JSONDecodeError, TypeError, ValueError):
            config = {}
    config["demo_execution_enabled"] = False
    db.execute(
        "UPDATE agent_registry SET config=? WHERE id='risk_manager'",
        (json.dumps(config),),
    )
    db.execute(
        "INSERT INTO events (agent_id,event_type,event_message,metadata) VALUES (?,?,?,?)",
        (
            "orchestrator",
            "info",
            "Startup safety: demo execution forced OFF",
            json.dumps({"demo_execution_enabled": False}),
        ),
    )


def main() -> None:
    db = Database(DB_PATH)
    db.init_schema()

    orchestrator = Orchestrator(db)
    orchestrator.register_core_agents()
    _force_demo_off(db)

    def shutdown_handler(_signum, _frame):
        orchestrator.shutdown()

    signal.signal(signal.SIGINT, shutdown_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown_handler)

    print("=" * 68)
    print("XAUUSD-SCALPER-X10")
    print("Research system starting. DEMO EXECUTION = OFF")
    print("Enable only with: python scripts/demo_switch.py enable")
    print("=" * 68)

    try:
        orchestrator.run()
    finally:
        # New entries remain disabled after any orderly shutdown as well.
        try:
            _force_demo_off(db)
        finally:
            db.close()


if __name__ == "__main__":
    main()
