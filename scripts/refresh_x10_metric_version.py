"""Invalidate stale pre-V2 strategy evidence without deleting history.

Run once after deploying a new BACKTEST_METRIC_VERSION. The script is
idempotent: strategies already stamped with the current metric version are
left untouched.

Historical backtest_results rows remain in SQLite for audit/debugging. What is
cleared is only the *derived deployment evidence* that must not survive a
change in metric semantics.
"""
from __future__ import annotations

import json
from typing import Any

from core.config import BACKTEST_METRIC_VERSION
from core.db import Database


DERIVED_KEYS = {
    "monte_carlo",
    "sensitivity",
    "statistical_evidence",
    "chronological_stability",
    "portfolio",
    "portfolio_selected",
    "portfolio_score",
    "regime_perf",
    "probation",
    "validation_v2",
}


def _parse_config(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _is_current(config: dict) -> bool:
    return config.get("metric_version") == BACKTEST_METRIC_VERSION


def refresh(db: Database) -> dict:
    """Invalidate stale metrics and queue strategies for V2 revalidation.

    Rules:
    - candidate strategies with no derived evidence stay candidates;
    - validated / portfolio_reserve strategies become candidates;
    - rejected/retired strategies remain rejected/retired unless their stored
      best metrics were derived from an older engine and therefore need a new
      fair evaluation; rejected strategies are re-queued, retired are not;
    - live deployment is disabled immediately by walk_forward_passed=0;
    - old backtest rows are retained untouched.
    """
    rows = db.fetchall(
        "SELECT id, status, best_config FROM strategies "
        "WHERE status IN ('candidate','validated','portfolio_reserve','rejected','retired')"
    )

    changed = 0
    skipped = 0
    retired = 0

    for row in rows:
        config = _parse_config(row["best_config"])
        if _is_current(config):
            skipped += 1
            continue

        if row["status"] == "retired":
            retired += 1
            continue

        for key in DERIVED_KEYS:
            config.pop(key, None)
        config["metric_version"] = BACKTEST_METRIC_VERSION
        config["metric_refresh_pending"] = True

        # Reset aggregate best_* values. They are not comparable across the
        # old and new x10_count semantics and must be repopulated by V2.
        db.execute(
            "UPDATE strategies SET "
            "status='candidate', walk_forward_passed=0, "
            "best_win_rate=NULL, best_profit_factor=NULL, "
            "best_max_drawdown=NULL, best_x10_count=NULL, "
            "best_final_balance=NULL, best_config=? "
            "WHERE id=?",
            (json.dumps(config), row["id"]),
        )
        changed += 1

    return {
        "metric_version": BACKTEST_METRIC_VERSION,
        "requeued": changed,
        "already_current": skipped,
        "retired_untouched": retired,
    }


def main() -> None:
    db = Database()
    result = refresh(db)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
