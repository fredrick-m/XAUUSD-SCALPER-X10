"""
Strategy C002: EMA Pullback + ADX Trend (M5)
Family  : EMA + ADX
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: Triple EMA trend alignment with ADX strength filter and pullback entry.

Parameters:
  ema_fast: 8
  ema_mid: 21
  ema_slow: 50
  adx_period: 14
  adx_threshold: 25
  pullback_atr_mult: 0.5
  session_start: 7
  session_end: 20
  cooldown: 15
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : Long:  EMA(8) > EMA(21) > EMA(50) AND ADX > 25 AND price within 0.5 ATR of EMA(21)
                AND bullish candle (Close > Open)
         Short: EMA(8) < EMA(21) < EMA(50) AND ADX > 25 AND price within 0.5 ATR of EMA(21)
                AND bearish candle (Close < Open)
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "ema_fast": 8,
    "ema_mid": 21,
    "ema_slow": 50,
    "adx_period": 14,
    "adx_threshold": 25,
    "pullback_atr_mult": 0.5,
    "session_start": 7,
    "session_end": 20,
    "cooldown": 15,
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
    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_mid"] = ta.trend.ema_indicator(df["Close"], window=p["ema_mid"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
    df["ADX"] = ta.trend.adx(df["High"], df["Low"], df["Close"], window=p["adx_period"])

    # Shifted values to prevent look-ahead bias
    ema_fast_prev = df["EMA_fast"].shift(1)
    ema_mid_prev = df["EMA_mid"].shift(1)
    ema_slow_prev = df["EMA_slow"].shift(1)
    adx_prev = df["ADX"].shift(1)
    atr_prev = df["ATR"].shift(1)
    low_prev = df["Low"].shift(1)
    high_prev = df["High"].shift(1)
    close_prev = df["Close"].shift(1)
    open_prev = df["Open"].shift(1)

    # Session filter
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        hour = pd.to_datetime(df["Time"]).dt.hour
    else:
        hour = df.index.to_series().apply(lambda x: 12)

    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # Uptrend: EMA(8) > EMA(21) > EMA(50)
    uptrend = (ema_fast_prev > ema_mid_prev) & (ema_mid_prev > ema_slow_prev)
    # Downtrend: EMA(8) < EMA(21) < EMA(50)
    downtrend = (ema_fast_prev < ema_mid_prev) & (ema_mid_prev < ema_slow_prev)

    # ADX filter
    strong_trend = adx_prev > p["adx_threshold"]

    # Pullback: price touches within 0.5 ATR of EMA(21)
    pullback_dist = p["pullback_atr_mult"] * atr_prev
    pullback_long = low_prev <= (ema_mid_prev + pullback_dist)
    pullback_short = high_prev >= (ema_mid_prev - pullback_dist)

    # Candle confirmation
    bullish_candle = close_prev > open_prev
    bearish_candle = close_prev < open_prev

    # Long signal
    long_cond = uptrend & strong_trend & pullback_long & bullish_candle & in_session

    # Short signal
    short_cond = downtrend & strong_trend & pullback_short & bearish_candle & in_session

    df["signal"] = 0
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # Cooldown
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
