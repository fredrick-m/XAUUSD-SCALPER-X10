"""Install a fail-closed SQLite guard for backtest metric versioning.

The current backtest writer can create rows with a NULL/empty config. The demo
preflight correctly treats those rows as stale. This deployment guard removes
already-unversioned results so they must be recomputed, then installs a SQLite
trigger that stamps newly inserted results with BACKTEST_METRIC_VERSION.

It does not mark old evidence as current: stale rows are deleted, not upgraded.
"""
from __future__ import annotations

import json
import sqlite3

from core.config import BACKTEST_METRIC_VERSION, DB_PATH

TRIGGER_NAME = "backtest_results_metric_version_guard"


def install_guard(db_path=DB_PATH) -> tuple[int, str]:
    conn = sqlite3.connect(str(db_path))
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='backtest_results'"
        ).fetchone()
        if not table:
            return 0, BACKTEST_METRIC_VERSION

        rows = conn.execute("SELECT id, config FROM backtest_results").fetchall()
        stale_ids: list[int] = []
        for row_id, raw in rows:
            try:
                cfg = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, TypeError):
                cfg = {}
            if not isinstance(cfg, dict) or cfg.get("metric_version") != BACKTEST_METRIC_VERSION:
                stale_ids.append(int(row_id))

        if stale_ids:
            conn.executemany(
                "DELETE FROM backtest_results WHERE id=?",
                [(row_id,) for row_id in stale_ids],
            )

        conn.execute(f"DROP TRIGGER IF EXISTS {TRIGGER_NAME}")
        version_json = json.dumps({"metric_version": BACKTEST_METRIC_VERSION})
        version_sql = version_json.replace("'", "''")
        conn.execute(
            f"""
            CREATE TRIGGER {TRIGGER_NAME}
            AFTER INSERT ON backtest_results
            WHEN NEW.config IS NULL
                 OR json_valid(NEW.config) = 0
                 OR json_extract(NEW.config, '$.metric_version') IS NULL
            BEGIN
                UPDATE backtest_results
                SET config = CASE
                    WHEN NEW.config IS NOT NULL AND json_valid(NEW.config)
                    THEN json_set(NEW.config, '$.metric_version', '{BACKTEST_METRIC_VERSION}')
                    ELSE '{version_sql}'
                END
                WHERE id = NEW.id;
            END
            """
        )
        conn.commit()
        return len(stale_ids), BACKTEST_METRIC_VERSION
    finally:
        conn.close()


def main() -> int:
    removed, version = install_guard()
    print(f"metric guard installed: version={version}; stale_results_removed={removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
