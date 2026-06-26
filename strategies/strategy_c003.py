"""
Strategy C003: Bollinger Band Reversion + Volume (M5)
Family  : BB + RSI + Volume
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: Bollinger Band touch with RSI and volume spike confirmation,
             filtered by EMA(50) trend direction.

Parameters:
  bb_period: 20
  bb_std: 2
  rsi_period: 14
  rsi_low: 35
  rsi_high: 65
  vol_mult: 1.5
  vol_period: 20
  ema_trend: 50
  session_start: 7
  session_end: 20
  cooldown: 20
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : Long:  Close touches lower BB AND RSI < 35 AND volume > 1.5x avg AND above EMA(50)
         Short: Close touches upper BB AND RSI > 65 AND volume > 1.5x avg AND below EMA(50)
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "bb_period": 20,
    "bb_std": 2,
    "rsi_period": 14,
    "rsi_low": 35,
    "rsi_high": 65,
    "vol_mult": 1.5,
    "vol_period": 20,
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

    # Indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    bb = ta.volatility.BollingerBands(
        df["Close"], window=p["bb_period"], window_dev=p["bb_std"]
    )
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()

    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # Volume average
    vol_col = "Volume" if "Volume" in df.columns else "tick_volume"
    df["vol_avg"] = df[vol_col].rolling(window=p["vol_period"]).mean()

    # Shifted values to prevent look-ahead bias
    close_prev = df["Close"].shift(1)
    rsi_prev = df["RSI"].shift(1)
    bb_lower_prev = df["BB_lower"].shift(1)
    bb_upper_prev = df["BB_upper"].shift(1)
    ema_prev = df["EMA_trend"].shift(1)
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

    # Volume spike
    vol_spike = vol_prev > (p["vol_mult"] * vol_avg_prev)

    # Long: price touches lower BB + RSI oversold + volume spike + above EMA trend
    long_cond = (
        (close_prev <= bb_lower_prev)
        & (rsi_prev < p["rsi_low"])
        & vol_spike
        & (close_prev > ema_prev)
        & in_session
    )

    # Short: price touches upper BB + RSI overbought + volume spike + below EMA trend
    short_cond = (
        (close_prev >= bb_upper_prev)
        & (rsi_prev > p["rsi_high"])
        & vol_spike
        & (close_prev < ema_prev)
        & in_session
    )

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
