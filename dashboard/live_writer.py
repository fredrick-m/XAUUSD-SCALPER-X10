"""
LiveWriter - writes backtest state to a JSON file for the dashboard to consume.
Usage:
    writer = LiveWriter()
    writer.update(balance=123.45, trades=[...], metrics={...})
    writer.close()
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Optional

FEED_PATH = Path(__file__).parent.parent / "backtests" / "live_feed.json"


class LiveWriter:
    def __init__(self, path: Path = FEED_PATH):
        self.path = path
        self.start_time = time.time()
        self._write({
            "status": "STARTING",
            "timestamp": time.time(),
            "balance": 50.0,
            "initial_balance": 50.0,
            "trades": [],
            "equity_curve": [50.0],
            "metrics": {},
            "strategy": "",
            "pipeline_stage": "IDLE",
            "regime": "UNKNOWN",
            "regime_stats": {},
            "wf_windows": [],
            "monte_carlo": {},
        })

    def _write(self, data: dict):
        self.path.write_text(json.dumps(data, default=str), encoding="utf-8")

    def update(self,
               balance: float = 50.0,
               trades: Optional[List[Dict]] = None,
               equity_curve: Optional[List[float]] = None,
               metrics: Optional[Dict] = None,
               strategy: str = "",
               pipeline_stage: str = "IDLE",
               regime: str = "UNKNOWN",
               regime_stats: Optional[Dict] = None,
               wf_windows: Optional[List[Dict]] = None,
               monte_carlo: Optional[Dict] = None,
               decision_tree: Optional[List[Dict]] = None,
               status: str = "RUNNING"):
        data = {
            "status": status,
            "timestamp": time.time(),
            "elapsed": round(time.time() - self.start_time, 1),
            "balance": round(balance, 2),
            "initial_balance": 50.0,
            "trades": (trades or [])[-20:],  # last 20
            "equity_curve": equity_curve or [50.0],
            "metrics": metrics or {},
            "strategy": strategy,
            "pipeline_stage": pipeline_stage,
            "regime": regime,
            "regime_stats": regime_stats or {},
            "wf_windows": wf_windows or [],
            "monte_carlo": monte_carlo or {},
            "decision_tree": decision_tree or [],
        }
        self._write(data)

    def close(self, final_metrics: Optional[Dict] = None):
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            data = {}
        data["status"] = "COMPLETE"
        data["timestamp"] = time.time()
        data["elapsed"] = round(time.time() - self.start_time, 1)
        if final_metrics:
            data["metrics"] = final_metrics
        self._write(data)
