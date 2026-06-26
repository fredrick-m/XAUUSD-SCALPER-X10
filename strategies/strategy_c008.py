"""
Strategy C008: Triple Indicator Confluence (M5)
Family  : Multi-Indicator
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: Confluence of RSI, MACD histogram, EMA trend, ADX strength,
             and volume filter for high-probability entries.

Parameters:
  rsi_period: 14
  rsi_long_thresh: 40
  rsi_short_thresh: 60
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  ema_trend: 50
  adx_period: 14
  adx_thresh: 20
  vol_lookback: 20
  session_start: 8
  session_end: 19
  cooldown: 25
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : RSI<40 + MACD hist>0 + Close>EMA(50) + ADX>20 + Vol>avg → long
         RSI>60 + MACD hist<0 + Close<EMA(50) + ADX>20 + Vol>avg → short
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "rsi_period": 14,
    "rsi_long_thresh": 40,
    "rsi_short_thresh": 60,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "ema_trend": 50,
    "adx_period": 14,
    "adx_thresh": 20,
    "vol_lookback": 20,
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

    # --- indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # MACD
    macd_obj = ta.trend.MACD(
        df["Close"],
        window_fast=p["macd_fast"],
        window_slow=p["macd_slow"],
        window_sign=p["macd_signal"],
    )
    df["MACD_hist"] = macd_obj.macd_diff()

    # EMA trend
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # ADX
    df["ADX"] = ta.trend.adx(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )

    # Volume filter
    vol_col = "Volume" if "Volume" in df.columns else "tick_volume"
    if vol_col in df.columns:
        df["vol_avg"] = df[vol_col].rolling(p["vol_lookback"]).mean()
        vol_above = df[vol_col].shift(1) > df["vol_avg"].shift(1)
    else:
        vol_above = pd.Series(True, index=df.index)

    # --- session filter ---
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif df.index.dtype == "datetime64[ns]":
        hour = df.index.hour
    else:
        hour = pd.Series(12, index=df.index)

    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # --- signal logic (all shifted by 1) ---
    rsi_low = df["RSI"].shift(1) < p["rsi_long_thresh"]
    rsi_high = df["RSI"].shift(1) > p["rsi_short_thresh"]
    macd_pos = df["MACD_hist"].shift(1) > 0
    macd_neg = df["MACD_hist"].shift(1) < 0
    above_ema = df["Close"].shift(1) > df["EMA_trend"].shift(1)
    below_ema = df["Close"].shift(1) < df["EMA_trend"].shift(1)
    adx_strong = df["ADX"].shift(1) > p["adx_thresh"]

    long_raw = rsi_low & macd_pos & above_ema & adx_strong & vol_above & in_session
    short_raw = rsi_high & macd_neg & below_ema & adx_strong & vol_above & in_session

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
