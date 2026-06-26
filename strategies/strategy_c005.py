"""
Strategy C005: Stochastic + Trend Confluence (M5)
Family  : Stochastic + EMA + Volume
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: Stochastic %K/%D crossover at extremes with EMA(50) trend filter
             and volume confirmation.

Parameters:
  stoch_k: 14
  stoch_d: 3
  stoch_smooth: 3
  stoch_low: 25
  stoch_high: 75
  ema_trend: 50
  vol_period: 20
  session_start: 7
  session_end: 20
  cooldown: 20
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : Long:  %K crosses above %D below 25 AND Close > EMA(50) AND volume > 20-bar avg
         Short: %K crosses below %D above 75 AND Close < EMA(50) AND volume > 20-bar avg
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "stoch_k": 14,
    "stoch_d": 3,
    "stoch_smooth": 3,
    "stoch_low": 25,
    "stoch_high": 75,
    "ema_trend": 50,
    "vol_period": 20,
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

    stoch = ta.momentum.StochasticOscillator(
        df["High"],
        df["Low"],
        df["Close"],
        window=p["stoch_k"],
        smooth_window=p["stoch_smooth"],
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # Volume average
    vol_col = "Volume" if "Volume" in df.columns else "tick_volume"
    df["vol_avg"] = df[vol_col].rolling(window=p["vol_period"]).mean()

    # Shifted values to prevent look-ahead bias
    k_prev = df["stoch_k"].shift(1)
    k_prev2 = df["stoch_k"].shift(2)
    d_prev = df["stoch_d"].shift(1)
    d_prev2 = df["stoch_d"].shift(2)
    ema_prev = df["EMA_trend"].shift(1)
    close_prev = df["Close"].shift(1)
    vol_prev = df[vol_col].shift(1)
    vol_avg_prev = df["vol_avg"].shift(1)

    # Session filter
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        hour = pd.to_datetime(df["Time"]).dt.hour
    else:
        hour = df.index.to_series().apply(lambda x: 12)

    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # Volume above average
    vol_ok = vol_prev > vol_avg_prev

    # %K crosses above %D in oversold zone
    k_cross_up = (k_prev > d_prev) & (k_prev2 <= d_prev2) & (k_prev < p["stoch_low"])

    # %K crosses below %D in overbought zone
    k_cross_down = (k_prev < d_prev) & (k_prev2 >= d_prev2) & (k_prev > p["stoch_high"])

    # Long: stoch cross up in oversold + above EMA + volume
    long_cond = k_cross_up & (close_prev > ema_prev) & vol_ok & in_session

    # Short: stoch cross down in overbought + below EMA + volume
    short_cond = k_cross_down & (close_prev < ema_prev) & vol_ok & in_session

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
