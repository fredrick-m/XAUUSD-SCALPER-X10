"""Fail closed when a strategy file changed after its recorded backtest.

A Git checkout or runtime overwrite can make SQLite metrics refer to different
source code than the executable strategy file. At service start this guard
removes such results and clears/rebuilds the affected strategy summaries so
they are re-tested from their current source.

The mtime rule is intentionally conservative. A deployment that merely touches
a tracked strategy can cause a recalculation; keeping unverifiable evidence is
worse than spending CPU to reproduce it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.config import DB_PATH
from core.db import Database

MTIME_TOLERANCE_SECONDS = 2.0


def _run_timestamp(value) -> float | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _rebuild_summary(db: Database, strategy_id: str) -> None:
    row = db.fetchone(
        "SELECT win_rate,profit_factor,max_drawdown,x10_count,final_balance "
        "FROM backtest_results WHERE strategy_id=? "
        "ORDER BY profit_factor DESC, id DESC LIMIT 1",
        (strategy_id,),
    )
    if row:
        db.execute(
            "UPDATE strategies SET best_win_rate=?,best_profit_factor=?,"
            "best_max_drawdown=?,best_x10_count=?,best_final_balance=?,"
            "best_config=NULL,walk_forward_passed=0,status='candidate' "
            "WHERE id=? AND COALESCE(family,'')!='id_reservation'",
            (
                row["win_rate"], row["profit_factor"], row["max_drawdown"],
                row["x10_count"], row["final_balance"], strategy_id,
            ),
        )
    else:
        db.execute(
            "UPDATE strategies SET best_win_rate=NULL,best_profit_factor=NULL,"
            "best_max_drawdown=NULL,best_x10_count=NULL,best_final_balance=NULL,"
            "best_config=NULL,walk_forward_passed=0,status='candidate' "
            "WHERE id=? AND COALESCE(family,'')!='id_reservation'",
            (strategy_id,),
        )


def main() -> int:
    db = Database(DB_PATH)
    stale_result_ids: list[int] = []
    affected: set[str] = set()
    try:
        db.init_schema()
        rows = db.fetchall(
            "SELECT b.id,b.strategy_id,b.run_at,s.file_path,s.family "
            "FROM backtest_results b JOIN strategies s ON s.id=b.strategy_id"
        )
        for row in rows:
            if row["family"] == "id_reservation":
                continue
            path = Path(row["file_path"]) if row["file_path"] else None
            run_ts = _run_timestamp(row["run_at"])
            stale = path is None or not path.exists() or run_ts is None
            if not stale:
                try:
                    stale = path.stat().st_mtime > run_ts + MTIME_TOLERANCE_SECONDS
                except OSError:
                    stale = True
            if stale:
                stale_result_ids.append(int(row["id"]))
                affected.add(str(row["strategy_id"]))

        for result_id in stale_result_ids:
            db.execute("DELETE FROM backtest_results WHERE id=?", (result_id,))
        for strategy_id in affected:
            _rebuild_summary(db, strategy_id)

        # Remove an obsolete early trigger name if it exists. The richer
        # metric-version guard is installed independently.
        db.execute("DROP TRIGGER IF EXISTS stamp_backtest_metric_version")

        print(
            json.dumps(
                {
                    "stale_results_removed": len(stale_result_ids),
                    "strategies_reset": len(affected),
                },
                sort_keys=True,
            )
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
