"""XAUUSD-SCALPER-X10 autonomous multi-agent system entry point.

Every process start forces NEW MT5 demo entries OFF. Research agents may run,
but execution requires a fresh successful ``scripts/demo_switch.py enable``.
"""
import json
import signal

from core.config import DB_PATH
from core.db import Database
from agents.orchestrator import Orchestrator


def force_demo_off(db: Database, reason: str) -> None:
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
            "orchestrator", "info", f"Demo execution forced OFF: {reason}",
            json.dumps({"demo_execution_enabled": False, "reason": reason}),
        ),
    )


def main():
    print("=" * 60)
    print("  XAUUSD-SCALPER-X10")
    print("  Autonomous Multi-Agent Research + Guarded Demo System")
    print("=" * 60)
    print()

    print("[1/4] Initializing database...")
    db = Database(DB_PATH)
    db.init_schema()
    print(f"  DB: {DB_PATH}")

    print("[2/4] Registering core agents...")
    orch = Orchestrator(db)
    orch.register_core_agents()

    print("[3/4] Applying startup execution lock...")
    force_demo_off(db, "process startup")
    print("  DEMO EXECUTION: OFF")
    print("  Enable only with: python scripts/demo_switch.py enable")

    def handle_shutdown(_sig, _frame):
        print("\nShutdown requested...")
        # Stop new entries immediately before agent shutdown begins.
        try:
            force_demo_off(db, "shutdown requested")
        finally:
            orch.shutdown()

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    print("[4/4] Starting orchestrator...")
    print()
    try:
        orch.run()
    finally:
        try:
            force_demo_off(db, "process stopped")
        finally:
            db.close()
    print("System terminated. DEMO EXECUTION remains OFF.")


if __name__ == "__main__":
    main()
