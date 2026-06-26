"""
Strategy A005: Multi-Confluence Filter
Family  : Multi-Factor Confluence
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Quality-over-quantity approach requiring five independent
             conditions to align before entering a trade.

Parameters:
  ema_fast: 8
  ema_mid: 21
  ema_slow: 50
  rsi_period: 14
  rsi_lower: 40       RSI neutral-zone lower bound
  rsi_upper: 60       RSI neutral-zone upper bound
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  adx_period: 14
  adx_min: 25         Minimum ADX (trending market)
  vol_avg_period: 20
  atr_period: 14
  sl_atr: 1.0
  tp_atr: 2.0

Entry  : ALL five must be true:
         1. EMA stack — 8 > 21 > 50 for long (reverse for short)
         2. RSI 40-60 (not overbought / oversold)
         3. MACD histogram positive AND rising for long (reverse for short)
         4. ADX > 25 (trending)
         5. Volume > 20-period average
Exit   : SL = sl_atr * ATR(14)  |  TP = tp_atr * ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "ema_fast": 8,
    "ema_mid": 21,
    "ema_slow": 50,
    "rsi_period": 14,
    "rsi_lower": 40,
    "rsi_upper": 60,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "adx_period": 14,
    "adx_min": 25,
    "vol_avg_period": 20,
    "atr_period": 14,
    "sl_atr": 1.0,
    "tp_atr": 2.0,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- ATR (always required) ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # --- Triple EMA ---
    ema_f = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    ema_m = ta.trend.ema_indicator(df["Close"], window=p["ema_mid"])
    ema_s = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])

    # Use shifted values to avoid look-ahead bias
    ema_f_prev = ema_f.shift(1)
    ema_m_prev = ema_m.shift(1)
    ema_s_prev = ema_s.shift(1)

    ema_bull = (ema_f_prev > ema_m_prev) & (ema_m_prev > ema_s_prev)
    ema_bear = (ema_f_prev < ema_m_prev) & (ema_m_prev < ema_s_prev)

    # --- RSI in neutral zone ---
    rsi = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    rsi_prev = rsi.shift(1)
    rsi_neutral = (rsi_prev >= p["rsi_lower"]) & (rsi_prev <= p["rsi_upper"])

    # --- MACD histogram positive/negative AND rising/falling ---
    macd_ind = ta.trend.MACD(
        df["Close"],
        window_fast=p["macd_fast"],
        window_slow=p["macd_slow"],
        window_sign=p["macd_signal"],
    )
    hist = macd_ind.macd_diff()
    hist_prev = hist.shift(1)
    hist_prev2 = hist.shift(2)

    macd_bull = (hist_prev > 0) & (hist_prev > hist_prev2)  # positive and rising
    macd_bear = (hist_prev < 0) & (hist_prev < hist_prev2)  # negative and falling

    # --- ADX trending ---
    adx = ta.trend.adx(df["High"], df["Low"], df["Close"], window=p["adx_period"])
    adx_prev = adx.shift(1)
    adx_trending = adx_prev > p["adx_min"]

    # --- Volume above average ---
    vol_avg = df["Volume"].rolling(window=p["vol_avg_period"], min_periods=1).mean()
    vol_prev = df["Volume"].shift(1)
    vol_avg_prev = vol_avg.shift(1)
    vol_ok = vol_prev > vol_avg_prev

    # --- Confluence: ALL five conditions ---
    long_cond = ema_bull & rsi_neutral & macd_bull & adx_trending & vol_ok
    short_cond = ema_bear & rsi_neutral & macd_bear & adx_trending & vol_ok

    df["signal"] = 0
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
