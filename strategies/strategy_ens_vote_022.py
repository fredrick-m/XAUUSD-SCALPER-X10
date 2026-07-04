"""
Strategy ENS_VOTE_022: Ensemble Majority Vote
Family  : ensemble
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Ensemble Majority Vote combining 59 validated strategies
Components: ["ENS_VOTE_006", "ENS_WEIGHTED_006", "ENS_VOTE_013", "ENS_WEIGHTED_013", "ENS_VOTE_002", "ENS_WEIGHTED_002", "c007", "T01769", "ENS_VOTE_015", "ENS_WEIGHTED_015", "ENS_WEIGHTED_014", "ENS_VOTE_014", "ENS_VOTE_016", "ENS_WEIGHTED_016", "ENS_VOTE_003", "ENS_WEIGHTED_003", "ENS_VOTE_009", "ENS_WEIGHTED_009", "ENS_WEIGHTED_011", "ENS_VOTE_019", "ENS_WEIGHTED_019", "ENS_VOTE_007", "ENS_WEIGHTED_007", "ENS_VOTE_011", "ENS_VOTE_008", "ENS_WEIGHTED_008", "ENS_VOTE_004", "T02218", "ENS_WEIGHTED_004", "T01736", "T01471", "T02136", "ENS_VOTE_021", "ENS_WEIGHTED_021", "T00836", "ENS_VOTE_005", "ENS_WEIGHTED_005", "T00903", "ENS_VOTE_010", "ENS_WEIGHTED_010", "T01798", "ENS_VOTE_012", "ENS_WEIGHTED_012", "ENS_VOTE_018", "ENS_WEIGHTED_018", "T01021", "ENS_VOTE_017", "ENS_WEIGHTED_017", "T00926", "ENS_VOTE_020", "ENS_WEIGHTED_020", "T01450", "T01698", "T00725", "ENS_WEIGHTED_001", "T01884", "ENS_VOTE_001", "T02150", "T00844"]

Parameters:
  sl_atr: 1.9488
  tp_atr: 2.9880
  method: vote
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import ta

PARAMS = {
    "sl_atr": 1.9488,
    "tp_atr": 2.9880,
    "atr_period": 14,
    "method": "vote",
    "component_ids": ["ENS_VOTE_006", "ENS_WEIGHTED_006", "ENS_VOTE_013", "ENS_WEIGHTED_013", "ENS_VOTE_002", "ENS_WEIGHTED_002", "c007", "T01769", "ENS_VOTE_015", "ENS_WEIGHTED_015", "ENS_WEIGHTED_014", "ENS_VOTE_014", "ENS_VOTE_016", "ENS_WEIGHTED_016", "ENS_VOTE_003", "ENS_WEIGHTED_003", "ENS_VOTE_009", "ENS_WEIGHTED_009", "ENS_WEIGHTED_011", "ENS_VOTE_019", "ENS_WEIGHTED_019", "ENS_VOTE_007", "ENS_WEIGHTED_007", "ENS_VOTE_011", "ENS_VOTE_008", "ENS_WEIGHTED_008", "ENS_VOTE_004", "T02218", "ENS_WEIGHTED_004", "T01736", "T01471", "T02136", "ENS_VOTE_021", "ENS_WEIGHTED_021", "T00836", "ENS_VOTE_005", "ENS_WEIGHTED_005", "T00903", "ENS_VOTE_010", "ENS_WEIGHTED_010", "T01798", "ENS_VOTE_012", "ENS_WEIGHTED_012", "ENS_VOTE_018", "ENS_WEIGHTED_018", "T01021", "ENS_VOTE_017", "ENS_WEIGHTED_017", "T00926", "ENS_VOTE_020", "ENS_WEIGHTED_020", "T01450", "T01698", "T00725", "ENS_WEIGHTED_001", "T01884", "ENS_VOTE_001", "T02150", "T00844"],
    "weights": {"ENS_VOTE_006": 8.1739, "ENS_WEIGHTED_006": 8.1739, "ENS_VOTE_013": 7.9189, "ENS_WEIGHTED_013": 7.9189, "ENS_VOTE_002": 7.8848, "ENS_WEIGHTED_002": 7.8848, "c007": 6.7682, "T01769": 4.8155, "ENS_VOTE_015": 4.6282, "ENS_WEIGHTED_015": 4.6282, "ENS_WEIGHTED_014": 4.5408, "ENS_VOTE_014": 4.3507, "ENS_VOTE_016": 4.2255, "ENS_WEIGHTED_016": 4.2255, "ENS_VOTE_003": 3.7784, "ENS_WEIGHTED_003": 3.7784, "ENS_VOTE_009": 3.6651, "ENS_WEIGHTED_009": 3.6651, "ENS_WEIGHTED_011": 3.3226, "ENS_VOTE_019": 3.2575, "ENS_WEIGHTED_019": 3.2575, "ENS_VOTE_007": 3.224, "ENS_WEIGHTED_007": 3.224, "ENS_VOTE_011": 3.0676, "ENS_VOTE_008": 3.0402, "ENS_WEIGHTED_008": 3.0402, "ENS_VOTE_004": 3.0377, "T02218": 3.0372, "ENS_WEIGHTED_004": 2.9254, "T01736": 2.9218, "T01471": 2.7698, "T02136": 2.7017, "ENS_VOTE_021": 2.673, "ENS_WEIGHTED_021": 2.673, "T00836": 2.6619, "ENS_VOTE_005": 2.6445, "ENS_WEIGHTED_005": 2.6445, "T00903": 2.6287, "ENS_VOTE_010": 2.6282, "ENS_WEIGHTED_010": 2.6282, "T01798": 2.5823, "ENS_VOTE_012": 2.5159, "ENS_WEIGHTED_012": 2.5159, "ENS_VOTE_018": 2.4833, "ENS_WEIGHTED_018": 2.4833, "T01021": 2.4392, "ENS_VOTE_017": 2.4125, "ENS_WEIGHTED_017": 2.4125, "T00926": 2.3097, "ENS_VOTE_020": 2.272, "ENS_WEIGHTED_020": 2.272, "T01450": 2.231, "T01698": 2.1818, "T00725": 2.1013, "ENS_WEIGHTED_001": 1.8047, "T01884": 1.7752, "ENS_VOTE_001": 1.7543, "T02150": 1.693, "T00844": 1.3428},
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
