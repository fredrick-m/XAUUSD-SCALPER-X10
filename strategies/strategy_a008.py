"""
Strategy A008: Keltner Channel Bounce
Family  : Channel Bounce / Mean-Reversion
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Fade touches of Keltner Channel bands when RSI confirms
             oversold/overbought and the trend filter agrees.

Parameters:
  atr_period: 14
  sl_atr: 0.8
  tp_atr: 1.5
  kc_ema: 20         — Keltner center EMA period
  kc_atr_mult: 2.0   — Keltner band width in ATR multiples
  rsi_period: 14
  rsi_long: 35       — RSI threshold for long entries
  rsi_short: 65      — RSI threshold for short entries
  trend_ema: 50      — EMA for trend filter
  trend_shift: 5     — lookback for trend direction
  session_start: 7
  session_end: 21

Entry Long : Low <= lower Keltner, RSI < 35, EMA(50) rising
Entry Short: High >= upper Keltner, RSI > 65, EMA(50) falling
Exit       : SL = sl_atr × ATR  |  TP = tp_atr × ATR
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_period": 14,
    "sl_atr": 0.8,
    "tp_atr": 1.5,
    "kc_ema": 20,
    "kc_atr_mult": 2.0,
    "rsi_period": 14,
    "rsi_long": 35,
    "rsi_short": 65,
    "trend_ema": 50,
    "trend_shift": 5,
    "session_start": 7,
    "session_end": 21,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # Core ATR
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # Keltner Channels
    df["KC_mid"] = ta.trend.ema_indicator(df["Close"], window=p["kc_ema"])
    df["KC_upper"] = df["KC_mid"] + p["kc_atr_mult"] * df["ATR"]
    df["KC_lower"] = df["KC_mid"] - p["kc_atr_mult"] * df["ATR"]

    # RSI
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # Trend filter: EMA(50) direction
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["trend_ema"])
    ema_rising = df["EMA_trend"] > df["EMA_trend"].shift(p["trend_shift"])
    ema_falling = df["EMA_trend"] < df["EMA_trend"].shift(p["trend_shift"])

    # Session filter
    hour = df["time"].dt.hour
    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # Channel touch detection
    touch_lower = df["Low"] <= df["KC_lower"]
    touch_upper = df["High"] >= df["KC_upper"]

    # RSI confirmation
    rsi_oversold = df["RSI"] < p["rsi_long"]
    rsi_overbought = df["RSI"] > p["rsi_short"]

    # Signal generation
    df["signal"] = 0

    long_cond = touch_lower & rsi_oversold & ema_rising & in_session
    short_cond = touch_upper & rsi_overbought & ema_falling & in_session

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
