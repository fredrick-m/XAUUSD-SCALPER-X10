"""
Strategy C009: Momentum Burst (M5)
Family  : Momentum
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: Rate-of-change breakout confirmed by dual-EMA alignment and
             ADX strength filter.

Parameters:
  roc_period: 5
  roc_thresh: 0.15
  ema_fast: 8
  ema_slow: 21
  adx_period: 14
  adx_thresh: 25
  session_start: 7
  session_end: 20
  cooldown: 15
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : ROC(5) > 0.15% + EMA(8)>EMA(21) + ADX>25 → long
         ROC(5) < -0.15% + EMA(8)<EMA(21) + ADX>25 → short
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "roc_period": 5,
    "roc_thresh": 0.15,
    "ema_fast": 8,
    "ema_slow": 21,
    "adx_period": 14,
    "adx_thresh": 25,
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

    # --- indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # Rate of Change
    df["ROC"] = (
        (df["Close"] - df["Close"].shift(p["roc_period"]))
        / df["Close"].shift(p["roc_period"])
        * 100
    )

    # Dual EMA
    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])

    # ADX
    df["ADX"] = ta.trend.adx(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )

    # --- session filter ---
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif df.index.dtype == "datetime64[ns]":
        hour = df.index.hour
    else:
        hour = pd.Series(12, index=df.index)

    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # --- signal logic (shifted by 1) ---
    roc_up = df["ROC"].shift(1) > p["roc_thresh"]
    roc_down = df["ROC"].shift(1) < -p["roc_thresh"]
    ema_bull = df["EMA_fast"].shift(1) > df["EMA_slow"].shift(1)
    ema_bear = df["EMA_fast"].shift(1) < df["EMA_slow"].shift(1)
    adx_strong = df["ADX"].shift(1) > p["adx_thresh"]

    long_raw = roc_up & ema_bull & adx_strong & in_session
    short_raw = roc_down & ema_bear & adx_strong & in_session

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
