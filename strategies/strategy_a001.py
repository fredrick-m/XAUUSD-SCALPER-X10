"""
Strategy A001: Mean Reversion BB+RSI
Family  : Mean Reversion
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Bollinger Band + RSI mean-reversion in ranging markets

Parameters:
  bb_period: 20      BB window
  bb_std: 2.0        BB std-dev multiplier
  rsi_period: 14     RSI window
  rsi_lower: 30      RSI oversold threshold
  rsi_upper: 70      RSI overbought threshold
  adx_period: 14     ADX window
  adx_max: 25        ADX ceiling (only trade when ranging)
  atr_period: 14
  sl_atr: 1.0
  tp_atr: 1.5

Entry  : Long  — Close < lower BB AND RSI < 30 AND ADX < 25
         Short — Close > upper BB AND RSI > 70 AND ADX < 25
Exit   : SL = sl_atr * ATR(14)  |  TP = tp_atr * ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "bb_period": 20,
    "bb_std": 2.0,
    "rsi_period": 14,
    "rsi_lower": 30,
    "rsi_upper": 70,
    "adx_period": 14,
    "adx_max": 25,
    "atr_period": 14,
    "sl_atr": 1.0,
    "tp_atr": 1.5,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- ATR (always required) ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # --- Bollinger Bands ---
    bb = ta.volatility.BollingerBands(
        close=df["Close"], window=p["bb_period"], window_dev=p["bb_std"]
    )
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()

    # --- RSI ---
    df["rsi"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # --- ADX (ranging filter) ---
    df["adx"] = ta.trend.adx(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )

    # --- Signal logic (use .shift(1) to avoid look-ahead bias) ---
    prev_close = df["Close"].shift(1)
    prev_rsi = df["rsi"].shift(1)
    prev_adx = df["adx"].shift(1)
    prev_bb_lower = df["bb_lower"].shift(1)
    prev_bb_upper = df["bb_upper"].shift(1)

    ranging = prev_adx < p["adx_max"]

    long_cond = (prev_close < prev_bb_lower) & (prev_rsi < p["rsi_lower"]) & ranging
    short_cond = (prev_close > prev_bb_upper) & (prev_rsi > p["rsi_upper"]) & ranging

    df["signal"] = 0
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
