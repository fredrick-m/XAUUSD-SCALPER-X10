"""
Strategy ENS_VOTE_013: Ensemble Majority Vote
Family  : ensemble
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Ensemble Majority Vote combining 3 validated strategies
Components: ["c007", "T01736", "T00903"]

Parameters:
  sl_atr: 1.9373
  tp_atr: 2.9485
  method: vote
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import ta

PARAMS = {
    "method": "vote",
    "component_ids": [
        "c007",
        "T01736",
        "T00903"
    ],
    "weights": {
        "c007": 6.7682,
        "T01736": 2.9218,
        "T00903": 2.6287
    },
    "avg_sl_atr": 1.921856,
    "avg_tp_atr": 2.9485,
    "monte_carlo": {
        "median_dd": 0.0722,
        "p95_dd": 0.1283,
        "p_x10": 0.0,
        "p_ruin": 0.0,
        "n_simulations": 10000
    },
    "monte_carlo_tested": 1,
    "mtf_tested": 1,
    "multi_timeframe": {
        "baseline_pf": 0.6335,
        "best_htf": null,
        "best_pf": 0.6335,
        "improvement": 1.0,
        "htf_results": {
            "M5": {
                "pf": 0.7093,
                "wr": 0.4848,
                "trades": 33,
                "improvement": 1.1197
            },
            "M15": {
                "pf": 0.7409,
                "wr": 0.5217,
                "trades": 46,
                "improvement": 1.1695
            },
            "H1": {
                "pf": 0.7878,
                "wr": 0.5385,
                "trades": 52,
                "improvement": 1.2436
            }
        }
    },
    "redundant": 1,
    "redundant_of": "ENS_VOTE_027",
    "redundant_cluster": [
        "T00903",
        "ENS_VOTE_006",
        "ENS_WEIGHTED_006",
        "ENS_VOTE_013",
        "ENS_WEIGHTED_013",
        "ENS_VOTE_019",
        "ENS_WEIGHTED_019",
        "ENS_VOTE_023",
        "ENS_WEIGHTED_023",
        "ENS_VOTE_024",
        "ENS_WEIGHTED_024",
        "ENS_VOTE_025",
        "ENS_WEIGHTED_025",
        "ENS_VOTE_026",
        "ENS_WEIGHTED_026",
        "ENS_VOTE_027",
        "ENS_WEIGHTED_027",
        "ENS_VOTE_028",
        "ENS_WEIGHTED_028",
        "ENS_VOTE_029",
        "ENS_WEIGHTED_029",
        "ENS_VOTE_030",
        "ENS_WEIGHTED_030",
        "ENS_VOTE_031",
        "ENS_WEIGHTED_031",
        "ENS_VOTE_032",
        "ENS_WEIGHTED_032",
        "ENS_VOTE_033",
        "ENS_WEIGHTED_033",
        "ENS_VOTE_034",
        "ENS_WEIGHTED_034",
        "ENS_VOTE_035",
        "ENS_WEIGHTED_035",
        "ENS_VOTE_036",
        "ENS_WEIGHTED_036",
        "ENS_VOTE_037",
        "ENS_WEIGHTED_037",
        "ENS_VOTE_038",
        "ENS_WEIGHTED_038",
        "ENS_VOTE_039",
        "ENS_WEIGHTED_039",
        "ENS_VOTE_040",
        "ENS_WEIGHTED_040",
        "ENS_VOTE_041",
        "ENS_WEIGHTED_041",
        "ENS_VOTE_042",
        "ENS_WEIGHTED_042"
    ]
},
}

STRATEGIES_DIR = Path(__file__).resolve().parent


def _load_component_module(strategy_id: str):
    """Load a component strategy module by ID."""
    module_path = STRATEGIES_DIR / f"strategy_{strategy_id.lower()}.py"
    if not module_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        f"strategy_{strategy_id.lower()}", str(module_path),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Generate ensemble signals by combining component strategy signals."""
    df = df.copy()

    # Compute ATR for SL/TP
    atr_period = p.get("atr_period", 14)
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=atr_period,
    )

    component_ids = p["component_ids"]
    weights = p.get("weights", {})
    method = p.get("method", "vote")

    # Collect signals from each component
    all_signals = {}
    for sid in component_ids:
        mod = _load_component_module(sid)
        if mod is None:
            continue
        mod_params = getattr(mod, "PARAMS", {})
        try:
            result = mod.generate_signals(df.copy(), mod_params)
            if "signal" in result.columns:
                all_signals[sid] = result["signal"]
        except Exception:
            continue

    if not all_signals:
        df["signal"] = 0
        return df

    sig_df = pd.DataFrame(all_signals)

    if method == "weighted":
        weighted_sum = pd.Series(0.0, index=df.index)
        for sid in sig_df.columns:
            w = weights.get(sid, 1.0)
            weighted_sum += sig_df[sid].fillna(0) * w
        df["signal"] = np.sign(weighted_sum).astype(int)
    else:
        vote_sum = sig_df.fillna(0).sum(axis=1)
        df["signal"] = np.sign(vote_sum).astype(int)

    return df
