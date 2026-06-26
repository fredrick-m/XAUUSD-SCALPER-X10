"""
Strategy B003: RSI Mean Reversion with Trend Alignment
Family  : Mean Reversion / RSI
Goal    : XAUUSD-SCALPER-X10 — high win-rate mean reversion in direction of trend
Timeframe: M1 (XAUUSD)
Description:
    Only trade in direction of EMA(100) trend.
    Long: RSI(7) < 25 AND price above EMA(100) AND RSI starts reversing (RSI > RSI[1]).
    Short: RSI(7) > 75 AND price below EMA(100) AND RSI starts reversing down.
    Very wide SL to let mean reversion play out. Tight TP.
    Session: 07:00-20:00 UTC.

Parameters:
  rsi_period: 7
  rsi_oversold: 25
  rsi_overbought: 75
  ema_trend: 100
  atr_period: 14
  sl_atr: 3.0
  tp_atr: 1.0
  session_start: 7
  session_end: 20
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "rsi_period": 7,
    "rsi_oversold": 25,
    "rsi_overbought": 75,
    "ema_trend": 100,
    "atr_period": 14,
    "sl_atr": 3.0,
    "tp_atr": 1.0,
    "session_start": 7,
    "session_end": 20,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- Indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # --- Session filter ---
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        hour = pd.to_datetime(df["Time"]).dt.hour
    else:
        hour = df.index.to_series().apply(lambda x: 12)
    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # --- Conditions (all shifted by 1 to avoid look-ahead on entry bar) ---
    rsi_prev = df["RSI"].shift(1)
    rsi_prev2 = df["RSI"].shift(2)
    close_prev = df["Close"].shift(1)
    ema_trend_prev = df["EMA_trend"].shift(1)

    # Trend alignment
    uptrend = close_prev > ema_trend_prev
    downtrend = close_prev < ema_trend_prev

    # RSI oversold / overbought (previous bar was in extreme zone)
    rsi_oversold = rsi_prev < p["rsi_oversold"]
    rsi_overbought = rsi_prev > p["rsi_overbought"]

    # RSI reversal: RSI is starting to turn
    # For long: RSI was oversold AND is now turning up (RSI[1] > RSI[2])
    rsi_turning_up = rsi_prev > rsi_prev2
    # For short: RSI was overbought AND is now turning down
    rsi_turning_down = rsi_prev < rsi_prev2

    # Extra confirmation: RSI was recently higher (came from >30 down to <25)
    # Check that RSI was > 30 within last 10 bars
    rsi_was_above_30 = df["RSI"].shift(1).rolling(window=10, min_periods=1).max() > 30
    rsi_was_below_70 = df["RSI"].shift(1).rolling(window=10, min_periods=1).min() < 70

    # --- Signal generation ---
    df["signal"] = 0

    long_cond = (
        uptrend
        & rsi_oversold
        & rsi_turning_up
        & rsi_was_above_30
        & in_session
    )

    short_cond = (
        downtrend
        & rsi_overbought
        & rsi_turning_down
        & rsi_was_below_70
        & in_session
    )

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # --- Throttle: cooldown of 90 bars (~1.5 hours) between signals ---
    signals = df["signal"].values.copy()
    cooldown = 90
    last_signal_idx = -cooldown
    for i in range(len(signals)):
        if signals[i] != 0:
            if i - last_signal_idx < cooldown:
                signals[i] = 0
            else:
                last_signal_idx = i
    df["signal"] = signals

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
