"""
Strategy ENS_WEIGHTED_012: Ensemble Weighted Vote
Family  : ensemble
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Ensemble Weighted Vote combining 3 validated strategies
Components: ["c007", "T01736", "T00836"]

Parameters:
  sl_atr: 1.8032
  tp_atr: 3.3382
  method: weighted
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import ta

PARAMS = {
    "sl_atr": 1.8032,
    "tp_atr": 3.3382,
    "atr_period": 14,
    "method": "weighted",
    "component_ids": ["c007", "T01736", "T00836"],
    "weights": {"c007": 6.7682, "T01736": 2.9218, "T00836": 2.6619},
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
    method = p.get("method", "weighted")

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
