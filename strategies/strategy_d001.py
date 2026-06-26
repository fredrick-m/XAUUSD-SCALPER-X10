"""
D001 - RSI Extreme + Trend + Volume Surge (M5)
Ultra-selective: RSI(7) at extremes (< 20 / > 80) with trend alignment
and volume surge confirmation. Targets ~100-300 signals over 200K bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 2.0,
    "tp_atr": 3.0,
    "atr_period": 14,
    "cooldown": 80,
    "rsi_period": 7,
    "rsi_oversold": 20,
    "rsi_overbought": 80,
    "ema_trend": 100,
    "vol_mult": 2.0,
    "vol_window": 50,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])
    df["vol_avg"] = df["Volume"].rolling(window=p["vol_window"]).mean()

    # Shifted indicators (no lookahead)
    rsi = df["RSI"].shift(1)
    ema = df["EMA_trend"].shift(1)
    close = df["Close"].shift(1)
    vol = df["Volume"].shift(1)
    vol_avg = df["vol_avg"].shift(1)

    # Long: RSI < 20, price above EMA(100), volume surge
    long_cond = (
        (rsi < p["rsi_oversold"])
        & (close > ema)
        & (vol > p["vol_mult"] * vol_avg)
    )

    # Short: RSI > 80, price below EMA(100), volume surge
    short_cond = (
        (rsi > p["rsi_overbought"])
        & (close < ema)
        & (vol > p["vol_mult"] * vol_avg)
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
