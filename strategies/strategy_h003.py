"""
H003 - EMA Stack + Inside Bar Breakout (M5)
Uses proven EMA(8/21/50) stack filter (20+ bars). Enters on inside bar breakout
(a bar whose range is contained within the prior bar, then breaks out).
Price action based — no additional indicators needed beyond EMAs.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 3.5,
    "atr_period": 14,
    "cooldown": 100,
    "ema_fast": 8,
    "ema_mid": 21,
    "ema_slow": 50,
    "stack_bars": 20,
    "min_inside_bars": 2,  # require N consecutive inside bars (compression)
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_mid"] = ta.trend.ema_indicator(df["Close"], window=p["ema_mid"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])

    df["bull_stack"] = (
        (df["EMA_fast"] > df["EMA_mid"]) & (df["EMA_mid"] > df["EMA_slow"])
    ).astype(int)
    df["bear_stack"] = (
        (df["EMA_fast"] < df["EMA_mid"]) & (df["EMA_mid"] < df["EMA_slow"])
    ).astype(int)

    df["bull_break"] = (df["bull_stack"] != df["bull_stack"].shift(1)).astype(int)
    df["bull_group"] = df["bull_break"].cumsum()
    df["bull_consec"] = df.groupby("bull_group").cumcount() + 1
    df.loc[df["bull_stack"] == 0, "bull_consec"] = 0

    df["bear_break"] = (df["bear_stack"] != df["bear_stack"].shift(1)).astype(int)
    df["bear_group"] = df["bear_break"].cumsum()
    df["bear_consec"] = df.groupby("bear_group").cumcount() + 1
    df.loc[df["bear_stack"] == 0, "bear_consec"] = 0

    # Inside bar detection: current bar's range contained within prior bar
    df["inside_bar"] = (
        (df["High"] <= df["High"].shift(1)) & (df["Low"] >= df["Low"].shift(1))
    ).astype(int)

    # Count consecutive inside bars
    df["ib_break"] = (df["inside_bar"] != df["inside_bar"].shift(1)).astype(int)
    df["ib_group"] = df["ib_break"].cumsum()
    df["ib_consec"] = df.groupby("ib_group").cumcount() + 1
    df.loc[df["inside_bar"] == 0, "ib_consec"] = 0

    # Breakout: was inside bar(s) then breaks out
    bull_consec = df["bull_consec"].shift(1)
    bear_consec = df["bear_consec"].shift(1)
    was_inside = df["ib_consec"].shift(1) >= p["min_inside_bars"]
    close = df["Close"].shift(1)
    prev_high = df["High"].shift(2)
    prev_low = df["Low"].shift(2)

    # Long: bull trend + was compressed inside bars + breaks above mother bar high
    long_cond = (
        (bull_consec >= p["stack_bars"])
        & was_inside
        & (close > prev_high)
    )
    # Short: bear trend + was compressed + breaks below mother bar low
    short_cond = (
        (bear_consec >= p["stack_bars"])
        & was_inside
        & (close < prev_low)
    )

    df["raw_signal"] = 0
    df.loc[long_cond, "raw_signal"] = 1
    df.loc[short_cond, "raw_signal"] = -1

    raw = df["raw_signal"].copy()
    cooldown = p["cooldown"]
    last_signal_idx = -cooldown - 1
    for i in range(len(raw)):
        if raw.iloc[i] != 0:
            if i - last_signal_idx > cooldown:
                last_signal_idx = i
            else:
                raw.iloc[i] = 0
    df["signal"] = raw.fillna(0).astype(int)

    return df
