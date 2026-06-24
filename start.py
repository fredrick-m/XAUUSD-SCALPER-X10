"""
XAUUSD-SCALPER-X10 Autonomous Multi-Agent System
=================================================
Entry point: python start.py
"""
import signal
import sys

from core.config import DB_PATH
from core.db import Database
from agents.orchestrator import Orchestrator


def main():
    print("=" * 60)
    print("  XAUUSD-SCALPER-X10")
    print("  Autonomous Multi-Agent Backtesting System")
    print("=" * 60)
    print()

    print("[1/3] Initializing database...")
    db = Database(DB_PATH)
    db.init_schema()
    print(f"  DB: {DB_PATH}")

    print("[2/3] Registering core agents...")
    orch = Orchestrator(db)
    orch.register_core_agents()

    def handle_sigint(sig, frame):
        print("\n\nShutdown requested (Ctrl+C)...")
        orch.shutdown()

    signal.signal(signal.SIGINT, handle_sigint)

    print("[3/3] Starting orchestrator...")
    print()
    orch.run()

    db.close()
    print("System terminated.")


if __name__ == "__main__":
    main()
