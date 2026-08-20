"""XAUUSD-SCALPER-X10 autonomous multi-agent system entry point.

Every process start forces NEW MT5 demo entries OFF. The current metric
migration is applied idempotently before agents start, so stale evidence cannot
silently survive a deployment. Demo execution still requires a fresh preflight
and an explicitly named risk profile.
"""
import json
import signal

from core.config import DB_PATH
from core.db import Database
from agents.orchestrator import Orchestrator
from scripts.refresh_x10_metric_version import refresh as refresh_metric_version


def _read_agent_config(db: Database, agent_id: str) -> dict:
    row = db.fetchone("SELECT config FROM agent_registry WHERE id=?", (agent_id,))
    if not row or not row["config"]:
        return {}
    try:
        return json.loads(row["config"]) if isinstance(row["config"], str) else dict(row["config"])
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _merge_agent_config(db: Database, agent_id: str, **values) -> None:
    config = _read_agent_config(db, agent_id)
    config.update(values)
    db.execute(
        "UPDATE agent_registry SET config=? WHERE id=?",
        (json.dumps(config), agent_id),
    )


def configure_research_pipeline(db: Database) -> None:
    """Set progressive throughput large enough for a 100+ strategy portfolio."""
    _merge_agent_config(
        db,
        "monte_carlo",
        tick_interval=300,
        analysis_per_family=8,
        max_per_tick=8,
        n_simulations=10000,
    )
    _merge_agent_config(
        db,
        "sensitivity_agent",
        tick_interval=300,
        analysis_per_family=8,
        max_per_tick=1,
    )


def force_demo_off(db: Database, reason: str) -> None:
    row = db.fetchone("SELECT config FROM agent_registry WHERE id='risk_manager'")
    if not row:
        return
    config = _read_agent_config(db, "risk_manager")
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

    print("[1/5] Initializing database...")
    db = Database(DB_PATH)
    db.init_schema()
    print(f"  DB: {DB_PATH}")

    print("[2/5] Applying current metric migration...")
    migration = refresh_metric_version(db)
    if migration.get("already_applied"):
        print(f"  Metric version already current: {migration['metric_version']}")
    else:
        print(
            f"  Migrated to {migration['metric_version']}: "
            f"archived={migration.get('archived_results', 0)} "
            f"requeued={migration.get('requeued', 0)}"
        )

    print("[3/5] Registering and tuning core agents...")
    orch = Orchestrator(db)
    orch.register_core_agents()
    configure_research_pipeline(db)

    print("[4/5] Applying startup execution lock...")
    force_demo_off(db, "process startup")
    print("  DEMO EXECUTION: OFF")
    print("  Preflight: python scripts/demo_preflight.py")
    print("  Enable example: python scripts/demo_switch.py enable --profile conservative")

    def handle_shutdown(_sig, _frame):
        print("\nShutdown requested...")
        try:
            force_demo_off(db, "shutdown requested")
        finally:
            orch.shutdown()

    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    print("[5/5] Starting orchestrator...")
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
