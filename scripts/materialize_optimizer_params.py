"""Clone param-optimizer winners into runtime strategies for full revalidation.

The parameter optimizer can record an improved parameter dict in SQLite while
the original strategy file still contains older PARAMS. Trusting that row as
if it described the executable file breaks provenance.

This guard never edits the original strategy file. Instead, for each latest
optimizer-produced result it creates an untracked runtime child with the
optimized PARAMS, removes optimizer-only evidence from the parent, rebuilds the
parent summary from any remaining primary evidence, and leaves the child as a
candidate for the normal BacktestRunner/Validation V2 pipeline.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from core.config import DB_PATH, STRATEGIES_DIR
from core.db import Database

_METADATA_KEYS = {"metric_version"}
RUNTIME_DIR = STRATEGIES_DIR / "runtime"


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


def _source_with_params(source: str, params: dict, label: str) -> str:
    tree = ast.parse(source)
    node = _params_assignment(tree)
    if node is None or not getattr(node, "lineno", None) or not getattr(node, "end_lineno", None):
        raise ValueError("source has no replaceable PARAMS assignment")
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = node.end_lineno
    replacement = "PARAMS = " + repr(params) + "\n"
    candidate = "".join(lines[:start]) + replacement + "".join(lines[end:])
    compile(candidate, label, "exec")
    return candidate


def _rebuild_parent_summary(db: Database, strategy_id: str) -> None:
    row = db.fetchone(
        "SELECT win_rate,profit_factor,max_drawdown,x10_count,final_balance "
        "FROM backtest_results WHERE strategy_id=? "
        "ORDER BY profit_factor DESC,id DESC LIMIT 1",
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


def _delete_optimizer_results(db: Database, strategy_id: str) -> int:
    rows = db.fetchall(
        "SELECT id,regime_results FROM backtest_results WHERE strategy_id=?",
        (strategy_id,),
    )
    ids = [int(r["id"]) for r in rows if _json(r["regime_results"]).get("source") == "param_optimizer"]
    for result_id in ids:
        db.execute("DELETE FROM backtest_results WHERE id=?", (result_id,))
    return len(ids)


def main() -> int:
    db = Database(DB_PATH)
    created: list[str] = []
    cleaned_parents: set[str] = set()
    try:
        db.init_schema()
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        rows = db.fetchall(
            "SELECT b.id,b.strategy_id,b.config,b.regime_results,"
            "s.file_path,s.family,s.generation "
            "FROM backtest_results b JOIN strategies s ON s.id=b.strategy_id "
            "ORDER BY b.id DESC"
        )
        seen: set[str] = set()
        for row in rows:
            parent_id = str(row["strategy_id"])
            if parent_id in seen:
                continue
            regime = _json(row["regime_results"])
            if regime.get("source") != "param_optimizer":
                continue
            seen.add(parent_id)

            config = _json(row["config"])
            params = {k: v for k, v in config.items() if k not in _METADATA_KEYS}
            source_path = Path(row["file_path"]) if row["file_path"] else None
            if not params or source_path is None or not source_path.exists():
                _delete_optimizer_results(db, parent_id)
                _rebuild_parent_summary(db, parent_id)
                cleaned_parents.add(parent_id)
                continue

            result_id = int(row["id"])
            child_id = f"OPT{result_id:06d}"
            child_path = RUNTIME_DIR / f"strategy_{child_id.lower()}.py"
            exists = db.fetchone("SELECT id FROM strategies WHERE id=?", (child_id,))
            if not exists:
                source = source_path.read_text(encoding="utf-8")
                child_source = _source_with_params(source, params, f"<optimizer:{child_id}>")
                tmp = child_path.with_suffix(".tmp")
                tmp.write_text(child_source, encoding="utf-8")
                tmp.replace(child_path)
                db.execute(
                    "INSERT INTO strategies "
                    "(id,file_path,family,description,generation,parent_strategy,created_by,status) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        child_id,
                        str(child_path),
                        row["family"] or "optimized",
                        f"Optimizer runtime child of {parent_id}; requires full Validation V2",
                        int(row["generation"] or 1) + 1,
                        parent_id,
                        "param_optimizer_materializer",
                        "candidate",
                    ),
                )
                created.append(child_id)

            _delete_optimizer_results(db, parent_id)
            _rebuild_parent_summary(db, parent_id)
            cleaned_parents.add(parent_id)

        print(
            json.dumps(
                {
                    "runtime_children_created": created,
                    "created_count": len(created),
                    "optimizer_parents_cleaned": len(cleaned_parents),
                },
                sort_keys=True,
            )
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
