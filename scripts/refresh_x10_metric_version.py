"""One-time migration for a new backtest metric version.

Old active results are archived, all derived deployment evidence is invalidated,
and non-retired strategies are re-queued. A trigger stamps future active
backtests with the current metric version. The migration is idempotent.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.config import BACKTEST_METRIC_VERSION, DB_PATH
from core.db import Database


DERIVED_KEYS = {
    "monte_carlo",
    "sensitivity",
    "sensitivity_tested",
    "statistical_evidence",
    "chronological_stability",
    "portfolio",
    "portfolio_selected",
    "portfolio_score",
    "portfolio_rejection_reason",
    "redundant",
    "redundant_of",
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


def _ensure_tables(db: Database) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS metric_migrations ("
        "metric_version TEXT PRIMARY KEY, applied_at TEXT NOT NULL, "
        "archived_results INTEGER NOT NULL DEFAULT 0, "
        "requeued_strategies INTEGER NOT NULL DEFAULT 0)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS backtest_results_archive AS "
        "SELECT b.*, CAST(NULL AS TEXT) AS archived_metric_version, "
        "CAST(NULL AS TEXT) AS archived_at "
        "FROM backtest_results b WHERE 0"
    )


def _install_version_trigger(db: Database) -> None:
    payload = json.dumps({"metric_version": BACKTEST_METRIC_VERSION})
    db.execute("DROP TRIGGER IF EXISTS stamp_backtest_metric_version")
    escaped = payload.replace("'", "''")
    db.execute(
        "CREATE TRIGGER stamp_backtest_metric_version "
        "AFTER INSERT ON backtest_results "
        "WHEN NEW.config IS NULL "
        "BEGIN "
        f"UPDATE backtest_results SET config='{escaped}' WHERE id=NEW.id; "
        "END"
    )


def refresh(db: Database) -> dict:
    """Archive stale active results and re-queue strategies for this version."""
    _ensure_tables(db)

    existing = db.fetchone(
        "SELECT metric_version, applied_at, archived_results, requeued_strategies "
        "FROM metric_migrations WHERE metric_version=?",
        (BACKTEST_METRIC_VERSION,),
    )
    if existing:
        _install_version_trigger(db)
        return {
            "metric_version": BACKTEST_METRIC_VERSION,
            "already_applied": True,
            "applied_at": existing["applied_at"],
            "archived_results": existing["archived_results"],
            "requeued": existing["requeued_strategies"],
        }

    now = datetime.now(timezone.utc).isoformat()
    count_row = db.fetchone("SELECT COUNT(*) AS n FROM backtest_results")
    archived_count = int(count_row["n"] or 0) if count_row else 0

    if archived_count:
        db.execute(
            "INSERT INTO backtest_results_archive "
            "SELECT b.*, ?, ? FROM backtest_results b",
            (BACKTEST_METRIC_VERSION, now),
        )
        db.execute("DELETE FROM backtest_results")

    rows = db.fetchall(
        "SELECT id, status, best_config FROM strategies "
        "WHERE status IN ('candidate','validated','portfolio_reserve','rejected','retired')"
    )

    requeued = 0
    retired = 0
    for row in rows:
        if row["status"] == "retired":
            retired += 1
            continue

        config = _parse_config(row["best_config"])
        for key in DERIVED_KEYS:
            config.pop(key, None)
        config["metric_version"] = BACKTEST_METRIC_VERSION
        config["metric_refresh_pending"] = True

        db.execute(
            "UPDATE strategies SET "
            "status='candidate', walk_forward_passed=0, "
            "best_win_rate=NULL, best_profit_factor=NULL, "
            "best_max_drawdown=NULL, best_x10_count=NULL, "
            "best_final_balance=NULL, best_config=? "
            "WHERE id=?",
            (json.dumps(config), row["id"]),
        )
        requeued += 1

    _install_version_trigger(db)
    db.execute(
        "INSERT INTO metric_migrations "
        "(metric_version, applied_at, archived_results, requeued_strategies) "
        "VALUES (?, ?, ?, ?)",
        (BACKTEST_METRIC_VERSION, now, archived_count, requeued),
    )

    return {
        "metric_version": BACKTEST_METRIC_VERSION,
        "already_applied": False,
        "applied_at": now,
        "archived_results": archived_count,
        "requeued": requeued,
        "retired_untouched": retired,
    }


def main() -> None:
    db = Database(DB_PATH)
    try:
        result = refresh(db)
        print(json.dumps(result, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
