"""
D008v2 - ATR Expansion + Trend Entry (M5) — OPTIMIZED
Based on D008 with tuned parameters:
- stack_bars: 30 → 20 (more signals: 113 → 193 trades)
- sl_atr: 2.0 → 1.5 (tighter SL captures more of the trend move)
- tp_atr: 3.0 → 4.0 (wider TP for higher R:R)

Best results: PF=1.33-1.89, $50→$420 (+740%) at risk=12%
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 4.0,
    "atr_period": 14,
    "cooldown": 100,
    "atr_expansion_mult": 1.5,
    "atr_avg_window": 50,
    "ema_fast": 8,
    "ema_mid": 21,
    "ema_slow": 50,
    "stack_bars": 20,
    "pullback_atr_mult": 0.5,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["ATR_avg"] = df["ATR"].rolling(window=p["atr_avg_window"]).mean()

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

    # Shifted indicators (no lookahead)
    atr = df["ATR"].shift(1)
    atr_avg = df["ATR_avg"].shift(1)
    close = df["Close"].shift(1)
    ema_mid = df["EMA_mid"].shift(1)
    bull_consec = df["bull_consec"].shift(1)
    bear_consec = df["bear_consec"].shift(1)

    # Pullback distance
    dist_to_mid = (close - ema_mid).abs()
    pullback_threshold = p["pullback_atr_mult"] * atr

    # ATR expansion
    atr_expanding = atr > p["atr_expansion_mult"] * atr_avg

    # Long: bull stack 20+ bars, ATR expanding, price pulls back near EMA(21)
    long_cond = (
        (bull_consec >= p["stack_bars"])
        & atr_expanding
        & (dist_to_mid <= pullback_threshold)
        & (close > ema_mid)
    )

    # Short: bear stack 20+ bars, ATR expanding, price pulls back near EMA(21)
    short_cond = (
        (bear_consec >= p["stack_bars"])
        & atr_expanding
        & (dist_to_mid <= pullback_threshold)
        & (close < ema_mid)
    )

    df["raw_signal"] = 0
    df.loc[long_cond, "raw_signal"] = 1
    df.loc[short_cond, "raw_signal"] = -1

    # Vectorized cooldown
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
