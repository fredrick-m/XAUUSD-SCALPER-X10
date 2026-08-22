"""Materialize param-optimizer winners into executable strategy source.

The parameter optimizer can record an improved parameter dict in SQLite while
the strategy file still contains older PARAMS. That makes later evolution or
execution refer to different code than the measured result.

For each latest optimizer-produced result, this guard writes those executable
parameters into the strategy's PARAMS assignment when they differ. It then
removes that strategy's existing backtest evidence and resets it to candidate,
forcing the primary BacktestRunner to reproduce the performance under the full
Validation V2 pipeline. No optimized result is trusted merely because it was
materialized.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from core.config import DB_PATH
from core.db import Database

_METADATA_KEYS = {"metric_version"}


def _json(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _params_assignment(tree: ast.AST) -> ast.Assign | ast.AnnAssign | None:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "PARAMS" for t in node.targets):
                return node
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "PARAMS":
                return node
    return None


def _source_params(source: str) -> dict | None:
    try:
        tree = ast.parse(source)
        node = _params_assignment(tree)
        if node is None:
            return None
        value = node.value
        parsed = ast.literal_eval(value)
        return dict(parsed) if isinstance(parsed, dict) else None
    except Exception:
        return None


def _rewrite_params(path: Path, params: dict) -> bool:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = _params_assignment(tree)
    if node is None or not getattr(node, "lineno", None) or not getattr(node, "end_lineno", None):
        return False

    current = _source_params(source)
    if current == params:
        return False

    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = node.end_lineno
    replacement = "PARAMS = " + repr(params) + "\n"
    candidate = "".join(lines[:start]) + replacement + "".join(lines[end:])
    compile(candidate, str(path), "exec")

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(candidate, encoding="utf-8")
    tmp.replace(path)
    return True


def _reset_strategy(db: Database, strategy_id: str) -> None:
    db.execute("DELETE FROM backtest_results WHERE strategy_id=?", (strategy_id,))
    db.execute(
        "UPDATE strategies SET best_win_rate=NULL,best_profit_factor=NULL,"
        "best_max_drawdown=NULL,best_x10_count=NULL,best_final_balance=NULL,"
        "best_config=NULL,walk_forward_passed=0,status='candidate' "
        "WHERE id=? AND COALESCE(family,'')!='id_reservation'",
        (strategy_id,),
    )


def main() -> int:
    db = Database(DB_PATH)
    materialized: list[str] = []
    try:
        db.init_schema()
        rows = db.fetchall(
            "SELECT b.id,b.strategy_id,b.config,b.regime_results,s.file_path "
            "FROM backtest_results b JOIN strategies s ON s.id=b.strategy_id "
            "ORDER BY b.id DESC"
        )
        seen: set[str] = set()
        for row in rows:
            sid = str(row["strategy_id"])
            if sid in seen:
                continue
            regime = _json(row["regime_results"])
            if regime.get("source") != "param_optimizer":
                continue
            seen.add(sid)

            config = _json(row["config"])
            params = {k: v for k, v in config.items() if k not in _METADATA_KEYS}
            if not params:
                continue
            path = Path(row["file_path"]) if row["file_path"] else None
            if path is None or not path.exists():
                _reset_strategy(db, sid)
                continue
            try:
                changed = _rewrite_params(path, params)
            except Exception as exc:
                raise RuntimeError(f"failed to materialize {sid}: {exc}") from exc
            if changed:
                _reset_strategy(db, sid)
                materialized.append(sid)

        print(json.dumps({"materialized": materialized, "count": len(materialized)}, sort_keys=True))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
