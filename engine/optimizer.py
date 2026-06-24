"""
Optuna-based parameter optimizer for trading strategies.

Wraps the backtest engine to optimize strategy PARAMS using Bayesian optimization
with in-sample/out-of-sample data splitting.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import optuna

from engine.backtest import run_simulation

# Silence Optuna's verbose logging
optuna.logging.set_verbosity(optuna.logging.WARNING)


def composite_score(metrics: dict) -> float:
    """
    Compute a 0-1 composite fitness score from backtest metrics.

    Weights:
      - win_rate:       25%
      - profit_factor:  30%  (capped at 4.0 → 1.0)
      - (1 - drawdown): 20%
      - x10_count:      25%  (capped at 5 → 1.0)

    Returns 0.0 if total_trades == 0.
    """
    if metrics.get("total_trades", 0) == 0:
        return 0.0

    wr = metrics.get("win_rate", 0.0)
    pf = metrics.get("profit_factor", 0.0)
    dd = metrics.get("max_drawdown", 1.0)
    x10 = metrics.get("x10_count", 0)

    score = (
        wr * 0.25
        + min(pf / 4.0, 1.0) * 0.30
        + (1.0 - dd) * 0.20
        + min(x10 / 5.0, 1.0) * 0.25
    )
    return round(max(0.0, min(score, 1.0)), 6)


def split_data(df: pd.DataFrame, ratio: float = 0.7) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split DataFrame into train/test by ratio (chronological, no shuffle)."""
    split_idx = int(len(df) * ratio)
    return df.iloc[:split_idx].copy().reset_index(drop=True), df.iloc[split_idx:].copy().reset_index(drop=True)


def _build_signals(module, df: pd.DataFrame, params: dict):
    """
    Run module.generate_signals and extract signal/SL/TP series.

    Returns (signals, sl_prices, tp_prices, directions) or None on failure.
    """
    sl_atr = params.get("sl_atr", 1.5)
    tp_atr = params.get("tp_atr", 2.5)

    result_df = module.generate_signals(df.copy(), params)

    if "signal" not in result_df.columns or "ATR" not in result_df.columns:
        return None

    signals = result_df["signal"]
    atr = result_df["ATR"]
    close = result_df["Close"]

    sl_prices = pd.Series(np.nan, index=df.index)
    tp_prices = pd.Series(np.nan, index=df.index)
    directions = pd.Series(0, index=df.index)

    long_mask = signals == 1
    short_mask = signals == -1

    sl_prices[long_mask] = close[long_mask] - sl_atr * atr[long_mask]
    tp_prices[long_mask] = close[long_mask] + tp_atr * atr[long_mask]
    sl_prices[short_mask] = close[short_mask] + sl_atr * atr[short_mask]
    tp_prices[short_mask] = close[short_mask] - tp_atr * atr[short_mask]
    directions[long_mask] = 1
    directions[short_mask] = -1

    return signals, sl_prices, tp_prices, directions


def _evaluate(module, df: pd.DataFrame, params: dict) -> float:
    """Run backtest with given params and return composite_score. Returns 0.0 on failure."""
    signal_data = _build_signals(module, df, params)
    if signal_data is None:
        return 0.0

    signals, sl_prices, tp_prices, directions = signal_data
    try:
        metrics = run_simulation(
            df, signals, sl_prices, tp_prices, directions,
            risk_pct=params.get("risk_pct", 0.05),
            trailing_stop=True,
            max_bars_in_trade=params.get("max_bars_in_trade", 60),
            session_filter=True,
            session_hours=(7, 21),
        )
    except Exception:
        return 0.0

    return composite_score(metrics)


def optimize_strategy(
    module,
    df: pd.DataFrame,
    param_space: Dict[str, Tuple[float, float]],
    n_trials: int = 50,
    split_ratio: float = 0.7,
) -> Tuple[dict, float]:
    """
    Optimize strategy parameters using Optuna.

    Parameters
    ----------
    module       : Strategy module with PARAMS dict and generate_signals().
    df           : Full OHLCV DataFrame.
    param_space  : Dict mapping param name to (min_val, max_val) float range.
    n_trials     : Number of Optuna trials.
    split_ratio  : Train/test split ratio (chronological).

    Returns
    -------
    (best_params, best_in_sample_score) — best params found on in-sample data.
    """
    train_df, _ = split_data(df, ratio=split_ratio)
    base_params = dict(getattr(module, "PARAMS", {}))

    def objective(trial: optuna.Trial) -> float:
        params = dict(base_params)
        for name, (lo, hi) in param_space.items():
            params[name] = trial.suggest_float(name, lo, hi)
        return _evaluate(module, train_df, params)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_params = dict(base_params)
    best_params.update(study.best_params)
    return best_params, study.best_value
