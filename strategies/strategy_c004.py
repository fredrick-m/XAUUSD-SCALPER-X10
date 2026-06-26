"""
Strategy C004: MACD Divergence Scalp (M5)
Family  : MACD + ADX + EMA
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: MACD histogram zero-line cross with EMA(50) trend filter and ADX strength.

Parameters:
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  ema_trend: 50
  adx_period: 14
  adx_threshold: 20
  session_start: 8
  session_end: 19
  cooldown: 25
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : Long:  MACD histogram crosses zero upward AND Close > EMA(50) AND ADX > 20
         Short: MACD histogram crosses zero downward AND Close < EMA(50) AND ADX > 20
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "ema_trend": 50,
    "adx_period": 14,
    "adx_threshold": 20,
    "session_start": 8,
    "session_end": 19,
    "cooldown": 25,
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

    macd_ind = ta.trend.MACD(
        df["Close"],
        window_fast=p["macd_fast"],
        window_slow=p["macd_slow"],
        window_sign=p["macd_signal"],
    )
    df["MACD_hist"] = macd_ind.macd_diff()

    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])
    df["ADX"] = ta.trend.adx(df["High"], df["Low"], df["Close"], window=p["adx_period"])

    # Shifted values to prevent look-ahead bias
    hist_prev = df["MACD_hist"].shift(1)
    hist_prev2 = df["MACD_hist"].shift(2)
    ema_prev = df["EMA_trend"].shift(1)
    close_prev = df["Close"].shift(1)
    adx_prev = df["ADX"].shift(1)

    # Session filter
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        hour = pd.to_datetime(df["Time"]).dt.hour
    else:
        hour = df.index.to_series().apply(lambda x: 12)

    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # MACD histogram zero-line cross
    hist_cross_up = (hist_prev > 0) & (hist_prev2 <= 0)
    hist_cross_down = (hist_prev < 0) & (hist_prev2 >= 0)

    # ADX filter
    trending = adx_prev > p["adx_threshold"]

    # Long: histogram crosses zero upward + price above EMA + trending
    long_cond = hist_cross_up & (close_prev > ema_prev) & trending & in_session

    # Short: histogram crosses zero downward + price below EMA + trending
    short_cond = hist_cross_down & (close_prev < ema_prev) & trending & in_session

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
