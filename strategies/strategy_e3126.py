"""
I003 - EMA Stack + OR Logic (RSI Pullback | ATR Expansion) — M5
Combines the entry triggers from D008v2 and G001v2 with OR logic:
signal fires if EITHER RSI pullback OR ATR expansion+pullback is met.

Profile: BALANCED — 279 signals, 192 trades, WR=44.3%, PF=1.50
$50 → $1197 at 10% risk (sl=1.5, tp=3.0, trailing=False)

Key: tp_atr=3.0 so trailing stop MUST be disabled (trailing stop rule).
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 3.0,
    "trailing_stop": false,
    "risk_pct": 0.04,
    "timeframe": "M5",
    "entry_logic": "OR(RSI_pullback, ATR_expansion+pullback) within EMA_stack",
    "walk_forward": {
        "is_pf": 1.18,
        "oos_pf": 1.75,
        "ratio": 1.48,
        "passed": true
    },
    "monte_carlo": {
        "median_dd": 0.357,
        "p95_dd": 0.357,
        "p_x10": 0.0,
        "p_ruin": 0.018,
        "n_simulations": 10000,
        "risk_pct": 0.04,
        "note": "Results at optimal 4% risk. At 10% risk p_ruin=60%."
    },
    "monte_carlo_tested": 1,
    "optimal_risk": 0.04,
    "risk_analysis": {
        "2pct": {
            "balance": 125,
            "p_ruin": 0.0,
            "dd": 0.159
        },
        "3pct": {
            "balance": 194,
            "p_ruin": 0.001,
            "dd": 0.199
        },
        "4pct": {
            "balance": 264,
            "p_ruin": 0.017,
            "dd": 0.264
        },
        "5pct": {
            "balance": 392,
            "p_ruin": 0.093,
            "dd": 0.312
        },
        "6pct": {
            "balance": 545,
            "p_ruin": 0.211,
            "dd": 0.363
        },
        "10pct": {
            "balance": 1377,
            "p_ruin": 0.605,
            "dd": 0.54
        }
    }
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["ATR_avg"] = df["ATR"].rolling(window=p["atr_avg_window"]).mean()
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_mid"] = ta.trend.ema_indicator(df["Close"], window=p["ema_mid"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])

    # EMA stacking conditions
    df["bull_stack"] = (
        (df["EMA_fast"] > df["EMA_mid"]) & (df["EMA_mid"] > df["EMA_slow"])
    ).astype(int)
    df["bear_stack"] = (
        (df["EMA_fast"] < df["EMA_mid"]) & (df["EMA_mid"] < df["EMA_slow"])
    ).astype(int)

    # Count consecutive bars of perfect stacking
    df["bull_break"] = (df["bull_stack"] != df["bull_stack"].shift(1)).astype(int)
    df["bull_group"] = df["bull_break"].cumsum()
    df["bull_consec"] = df.groupby("bull_group").cumcount() + 1
    df.loc[df["bull_stack"] == 0, "bull_consec"] = 0

    df["bear_break"] = (df["bear_stack"] != df["bear_stack"].shift(1)).astype(int)
    df["bear_group"] = df["bear_break"].cumsum()
    df["bear_consec"] = df.groupby("bear_group").cumcount() + 1
    df.loc[df["bear_stack"] == 0, "bear_consec"] = 0

    # Shifted to avoid lookahead
    atr = df["ATR"].shift(1)
    atr_avg = df["ATR_avg"].shift(1)
    rsi = df["RSI"].shift(1)
    close = df["Close"].shift(1)
    ema_mid = df["EMA_mid"].shift(1)
    bull_consec = df["bull_consec"].shift(1)
    bear_consec = df["bear_consec"].shift(1)

    # Entry trigger components
    # 1. RSI pullback (from G001v2)
    rsi_pull_bull = (rsi < p["rsi_low"]) & (rsi > p["rsi_floor"])
    rsi_pull_bear = (rsi > p["rsi_high"]) & (rsi < p["rsi_ceil"])

    # 2. ATR expansion + pullback (from D008v2)
    atr_expanding = atr > p["atr_expansion_mult"] * atr_avg
    dist_to_mid = (close - ema_mid).abs()
    pullback = dist_to_mid <= p["pullback_atr_mult"] * atr

    atr_trigger_bull = atr_expanding & pullback & (close > ema_mid)
    atr_trigger_bear = atr_expanding & pullback & (close < ema_mid)

    # OR logic: signal if EITHER trigger fires within EMA-stack filter
    long_cond = (bull_consec >= p["stack_bars"]) & (rsi_pull_bull | atr_trigger_bull)
    short_cond = (bear_consec >= p["stack_bars"]) & (rsi_pull_bear | atr_trigger_bear)

    df["raw_signal"] = 0
    df.loc[long_cond, "raw_signal"] = 1
    df.loc[short_cond, "raw_signal"] = -1

    # Cooldown
    raw = df["raw_signal"].copy()
    cooldown = p["cooldown"]
    last_signal_idx = -cooldown - 1
    for i in range(len(raw)):
        if raw.iloc[i] != 0:
            if i - last_signal_idx > cooldown:
                last_signal_idx = i
            else:
                raw.iloc[i] = 0
    df["signal"] = raw

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
