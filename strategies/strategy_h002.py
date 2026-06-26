"""
H002 - EMA Stack + MACD Histogram Reversal (M5)
Uses proven EMA(8/21/50) stack filter (20+ bars). Enters when MACD histogram
reverses direction (turns positive in bull trend after being negative = pullback ending).
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 3.0,
    "atr_period": 14,
    "cooldown": 100,
    "ema_fast": 8,
    "ema_mid": 21,
    "ema_slow": 50,
    "stack_bars": 20,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    macd_ind = ta.trend.MACD(
        df["Close"], window_fast=p["macd_fast"],
        window_slow=p["macd_slow"], window_sign=p["macd_signal"]
    )
    df["MACD_hist"] = macd_ind.macd_diff()

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

    hist = df["MACD_hist"].shift(1)
    hist_prev = df["MACD_hist"].shift(2)
    bull_consec = df["bull_consec"].shift(1)
    bear_consec = df["bear_consec"].shift(1)

    # MACD histogram turns positive (from negative) in bull trend = pullback ended
    long_cond = (
        (bull_consec >= p["stack_bars"])
        & (hist > 0)
        & (hist_prev <= 0)
    )
    # MACD histogram turns negative (from positive) in bear trend = bounce ended
    short_cond = (
        (bear_consec >= p["stack_bars"])
        & (hist < 0)
        & (hist_prev >= 0)
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
