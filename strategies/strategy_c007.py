"""
Strategy C007: Keltner Channel + RSI (M5)
Family  : Channel + Momentum
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: Mean-reversion entries off Keltner Channel bands confirmed by
             RSI extremes, with EMA(50) trend filter.

Parameters:
  kc_ema: 20
  kc_atr: 10
  kc_mult: 2.0
  rsi_period: 14
  rsi_long_thresh: 40
  rsi_short_thresh: 60
  ema_trend: 50
  session_start: 7
  session_end: 20
  cooldown: 20
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : Price touches lower KC + RSI < 40 + above EMA(50) → long
         Price touches upper KC + RSI > 60 + below EMA(50) → short
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "kc_ema": 20,
    "kc_atr": 10,
    "kc_mult": 2.0,
    "rsi_period": 14,
    "rsi_long_thresh": 40,
    "rsi_short_thresh": 60,
    "ema_trend": 50,
    "session_start": 7,
    "session_end": 20,
    "cooldown": 20,
    "atr_period": 14,
    "sl_atr": 2.0,
    "tp_atr": 3.0,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # Keltner Channel
    kc_atr = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["kc_atr"]
    )
    kc_mid = ta.trend.ema_indicator(df["Close"], window=p["kc_ema"])
    df["KC_upper"] = kc_mid + p["kc_mult"] * kc_atr
    df["KC_lower"] = kc_mid - p["kc_mult"] * kc_atr

    # Trend filter
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # --- session filter ---
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif df.index.dtype == "datetime64[ns]":
        hour = df.index.hour
    else:
        hour = pd.Series(12, index=df.index)

    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # --- signal logic (shifted to prevent look-ahead) ---
    touch_lower = df["Low"].shift(1) <= df["KC_lower"].shift(1)
    rsi_oversold = df["RSI"].shift(1) < p["rsi_long_thresh"]
    above_trend = df["Close"].shift(1) > df["EMA_trend"].shift(1)

    touch_upper = df["High"].shift(1) >= df["KC_upper"].shift(1)
    rsi_overbought = df["RSI"].shift(1) > p["rsi_short_thresh"]
    below_trend = df["Close"].shift(1) < df["EMA_trend"].shift(1)

    long_raw = touch_lower & rsi_oversold & above_trend & in_session
    short_raw = touch_upper & rsi_overbought & below_trend & in_session

    df["signal"] = 0
    df.loc[long_raw, "signal"] = 1
    df.loc[short_raw, "signal"] = -1

    # --- cooldown ---
    cooldown = p["cooldown"]
    last_signal_bar = -cooldown - 1
    signals = df["signal"].values.copy()
    for i in range(len(signals)):
        if signals[i] != 0:
            if i - last_signal_bar <= cooldown:
                signals[i] = 0
            else:
                last_signal_bar = i
    df["signal"] = signals

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
