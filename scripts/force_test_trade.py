"""Legacy compatibility command for the former forced-test-order utility.

Direct ``mt5.order_send`` calls from this script are intentionally disabled.
All demo orders must pass the normal paper_trade -> SignalGatekeeper -> Risk
Engine pipeline, including Portfolio V5 evidence, verified news calendar,
per-trade/portfolio risk limits and the explicit demo master switch.

Use instead:
    python scripts/demo_preflight.py
    python scripts/demo_switch.py enable

Then allow the normal paper_trade agent to place only genuine strategy signals.
"""
import sys

from core.config import DB_PATH
from core.db import Database
from scripts.demo_preflight import print_results, run_preflight


def main() -> int:
    db = Database(DB_PATH)
    try:
        db.init_schema()
        ready, results = run_preflight(db)
    finally:
        db.close()

    print_results(ready, results)
    print()
    print("FORCED TEST ORDERS ARE DISABLED.")
    print("No order was sent.")
    if ready:
        print("To enable guarded demo execution, run: python scripts/demo_switch.py enable")
        return 0
    print("Resolve the BLOCK items before enabling the normal demo pipeline.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
