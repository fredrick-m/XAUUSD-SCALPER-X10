"""
D003 - Keltner + RSI Extreme Confluence (M5)
Based on C007 (PF=5.42) but with wider tolerances to capture more signals.
Price near lower/upper Keltner channel + RSI extreme + trend filter.
Targets ~100-300 signals over 200K bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 2.0,
    "tp_atr": 3.0,
    "atr_period": 14,
    "cooldown": 60,
    "keltner_ema": 20,
    "keltner_atr": 10,
    "keltner_mult": 1.5,
    "keltner_tolerance_atr": 0.3,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
    "ema_trend": 50,
    "vol_mult": 1.2,
    "vol_window": 20,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["ATR_kc"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["keltner_atr"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["EMA_kc"] = ta.trend.ema_indicator(df["Close"], window=p["keltner_ema"])
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])
    df["vol_avg"] = df["Volume"].rolling(window=p["vol_window"]).mean()

    # Keltner Channel bands
    df["kc_lower"] = df["EMA_kc"] - p["keltner_mult"] * df["ATR_kc"]
    df["kc_upper"] = df["EMA_kc"] + p["keltner_mult"] * df["ATR_kc"]

    # Shifted indicators (no lookahead)
    close = df["Close"].shift(1)
    rsi = df["RSI"].shift(1)
    ema = df["EMA_trend"].shift(1)
    kc_lower = df["kc_lower"].shift(1)
    kc_upper = df["kc_upper"].shift(1)
    atr_kc = df["ATR_kc"].shift(1)
    vol = df["Volume"].shift(1)
    vol_avg = df["vol_avg"].shift(1)

    # Tolerance in price units
    tolerance = p["keltner_tolerance_atr"] * atr_kc

    # Long: price within tolerance of lower Keltner, RSI oversold, uptrend
    long_cond = (
        (close <= kc_lower + tolerance)
        & (rsi < p["rsi_oversold"])
        & (close > ema)
        & (vol > p["vol_mult"] * vol_avg)
    )

    # Short: price within tolerance of upper Keltner, RSI overbought, downtrend
    short_cond = (
        (close >= kc_upper - tolerance)
        & (rsi > p["rsi_overbought"])
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
