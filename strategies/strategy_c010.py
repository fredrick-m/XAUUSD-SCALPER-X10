"""
Strategy C010: Support/Resistance + RSI Bounce (M5)
Family  : S/R + Momentum
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: Bounce entries near rolling support/resistance levels confirmed
             by RSI extremes, with EMA(100) trend filter.

Parameters:
  sr_lookback: 50
  proximity_atr_mult: 0.5
  rsi_period: 14
  rsi_long_thresh: 35
  rsi_short_thresh: 65
  ema_trend: 100
  session_start: 7
  session_end: 20
  cooldown: 20
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : Price within 0.5*ATR of 50-bar low + RSI<35 + above EMA(100) → long
         Price within 0.5*ATR of 50-bar high + RSI>65 + below EMA(100) → short
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sr_lookback": 50,
    "proximity_atr_mult": 0.5,
    "rsi_period": 14,
    "rsi_long_thresh": 35,
    "rsi_short_thresh": 65,
    "ema_trend": 100,
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

    # Support / Resistance
    df["support"] = df["Low"].rolling(p["sr_lookback"]).min()
    df["resistance"] = df["High"].rolling(p["sr_lookback"]).max()

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

    # --- signal logic (all shifted by 1) ---
    close_prev = df["Close"].shift(1)
    atr_prev = df["ATR"].shift(1)
    support_prev = df["support"].shift(1)
    resistance_prev = df["resistance"].shift(1)
    rsi_prev = df["RSI"].shift(1)
    ema_prev = df["EMA_trend"].shift(1)

    near_support = (close_prev - support_prev).abs() <= p["proximity_atr_mult"] * atr_prev
    near_resistance = (resistance_prev - close_prev).abs() <= p["proximity_atr_mult"] * atr_prev

    rsi_oversold = rsi_prev < p["rsi_long_thresh"]
    rsi_overbought = rsi_prev > p["rsi_short_thresh"]

    above_trend = close_prev > ema_prev
    below_trend = close_prev < ema_prev

    long_raw = near_support & rsi_oversold & above_trend & in_session
    short_raw = near_resistance & rsi_overbought & below_trend & in_session

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
