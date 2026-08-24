"""Publish a fail-closed deployment manifest for the Windows MT5 execution node.

The Linux VPS remains the source of truth. This publisher exports only
Portfolio V5-selected strategies and NEVER enables order execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.config import BASE_DIR, DB_PATH
from core.db import Database
from agents.risk_manager import DEFAULT_RISK_PROFILE, RISK_PROFILES
from scripts.demo_preflight import run_preflight

BRIDGE_DIR = BASE_DIR / "bridge"
OUTBOX = BRIDGE_DIR / "outbox"
STRATEGY_DIR = OUTBOX / "strategies"
MANIFEST = OUTBOX / "deployment.json"


def _risk_config(db: Database) -> dict:
    row = db.fetchone("SELECT config FROM agent_registry WHERE id='risk_manager'")
    if not row or not row["config"]:
        return {}
    raw = row["config"]
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, 0o640)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def selected_strategies(db: Database) -> list[dict]:
    rows = db.fetchall(
        "SELECT id, file_path, family, status, walk_forward_passed, best_config, "
        "best_profit_factor, best_win_rate, best_max_drawdown "
        "FROM strategies WHERE status='validated' AND walk_forward_passed=1"
    )
    selected = []
    for row in rows:
        try:
            cfg = json.loads(row["best_config"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if not cfg.get("portfolio_selected"):
            continue
        if cfg.get("metric_version") != "x10_10d_v2":
            continue
        if not cfg.get("validation_v2", {}).get("passed"):
            continue
        if not cfg.get("statistical_evidence", {}).get("passed"):
            continue
        if not cfg.get("chronological_stability", {}).get("passed"):
            continue
        if cfg.get("sensitivity", {}).get("is_fragile", True):
            continue
        if float(cfg.get("monte_carlo", {}).get("p_ruin_10d", 1.0)) > 0.10:
            continue

        source = Path(row["file_path"])
        if not source.is_file():
            continue
        target = STRATEGY_DIR / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        selected.append({
            "id": row["id"],
            "family": row["family"],
            "file": f"strategies/{target.name}",
            "sha256": _sha256(target),
            "profit_factor": row["best_profit_factor"],
            "win_rate": row["best_win_rate"],
            "max_drawdown": row["best_max_drawdown"],
            "portfolio_score": cfg.get("portfolio_score"),
            "metric_version": cfg.get("metric_version"),
        })
    return sorted(selected, key=lambda x: float(x.get("portfolio_score") or 0), reverse=True)


def main() -> int:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(DB_PATH)
    try:
        strategies = selected_strategies(db)
        cfg = _risk_config(db)
        profile_name = str(cfg.get("risk_profile") or DEFAULT_RISK_PROFILE)
        profile = dict(RISK_PROFILES.get(profile_name, RISK_PROFILES[DEFAULT_RISK_PROFILE]))
        switch_requested = cfg.get("demo_execution_enabled") is True

        preflight_ready = False
        blockers: list[str] = []
        if switch_requested:
            ready, results = run_preflight(db)
            preflight_ready = bool(ready)
            blockers = [f"{name}:{detail}" for name, ok, detail in results if not ok]

        execution_enabled = bool(switch_requested and preflight_ready and strategies)
        entry_allowed = execution_enabled
    finally:
        db.close()

    payload = {
        "schema": "xauusd-mt5-bridge-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "linux-vps",
        "execution_enabled": execution_enabled,
        "entry_allowed": entry_allowed,
        "demo_switch_requested": switch_requested,
        "preflight_ready": preflight_ready,
        "preflight_blockers": blockers[:8],
        "account_mode_required": "demo",
        "symbol": "XAUUSD",
        "metric_version": "x10_10d_v2",
        "risk_policy": {"profile": profile_name, **profile},
        "strategies": strategies,
    }
    _atomic_json(MANIFEST, payload)
    print(
        f"published={MANIFEST} selected={len(strategies)} "
        f"switch_requested={switch_requested} preflight_ready={preflight_ready} "
        f"execution_enabled={execution_enabled}"
    )
    for blocker in blockers[:5]:
        print(f"BLOCK {blocker}")
    for s in strategies:
        print(f"{s['id']} sha256={s['sha256']} score={s['portfolio_score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
