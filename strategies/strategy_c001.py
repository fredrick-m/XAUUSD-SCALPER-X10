"""
Strategy C001: RSI Mean Reversion + Trend (M5 optimized)
Family  : RSI + EMA
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: RSI(7) mean reversion with EMA(100) trend filter and reversal confirmation.
             Based on B003 which achieved PF=1.59 on M5.

Parameters:
  rsi_period: 7
  ema_trend: 100
  rsi_oversold: 30
  rsi_overbought: 70
  session_start: 7
  session_end: 20
  cooldown: 20
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : Long:  RSI(7) < 30 (shifted) AND RSI reversal upward AND Close > EMA(100)
         Short: RSI(7) > 70 (shifted) AND RSI reversal downward AND Close < EMA(100)
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "rsi_period": 7,
    "ema_trend": 100,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
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

    # Indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # Shifted values to prevent look-ahead bias
    rsi_prev = df["RSI"].shift(1)
    rsi_prev2 = df["RSI"].shift(2)
    ema_prev = df["EMA_trend"].shift(1)
    close_prev = df["Close"].shift(1)

    # Session filter (hours 7-20 UTC)
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        hour = pd.to_datetime(df["Time"]).dt.hour
    else:
        hour = df.index.to_series().apply(lambda x: 12)  # fallback: always in session

    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # Long: RSI was oversold AND now reversing upward AND above EMA trend
    long_cond = (
        (rsi_prev2 < p["rsi_oversold"])
        & (rsi_prev > rsi_prev2)  # reversal confirmation
        & (close_prev > ema_prev)  # trend filter
        & in_session
    )

    # Short: RSI was overbought AND now reversing downward AND below EMA trend
    short_cond = (
        (rsi_prev2 > p["rsi_overbought"])
        & (rsi_prev < rsi_prev2)  # reversal confirmation
        & (close_prev < ema_prev)  # trend filter
        & in_session
    )

    df["signal"] = 0
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # Cooldown: suppress signals within N bars of the last signal
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
