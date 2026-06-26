"""
Strategy B002: London/NY Session Momentum Scalp
Family  : Momentum / Session-Based
Goal    : XAUUSD-SCALPER-X10 — high win-rate momentum entries during most volatile sessions
Timeframe: M1 (XAUUSD)
Description:
    Only trade during first 2 hours of London (07:00-09:00) and NY (13:00-15:00).
    Calculate 60-bar momentum. If momentum > 1.5*ATR and current bar closes in
    direction, enter. Volume must be > 2x 20-bar average. Max 1 trade per session.
    Wide SL with quick TP for high WR.

Parameters:
  momentum_period: 60
  momentum_threshold: 1.5  (x ATR)
  vol_lookback: 20
  vol_multiplier: 2.0
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 0.8
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "momentum_period": 60,
    "momentum_threshold": 1.5,
    "vol_lookback": 20,
    "vol_multiplier": 2.0,
    "atr_period": 14,
    "sl_atr": 2.0,
    "tp_atr": 0.8,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- Indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # Momentum: Close - Close[60] (shifted by 1 to use previous bar's data)
    df["momentum"] = df["Close"].shift(1) - df["Close"].shift(1 + p["momentum_period"])

    # Volume average (shifted to avoid look-ahead)
    vol_col = "Volume" if "Volume" in df.columns else "tick_volume"
    if vol_col not in df.columns:
        df["Volume"] = 1  # fallback
        vol_col = "Volume"
    df["vol_avg"] = df[vol_col].shift(1).rolling(window=p["vol_lookback"], min_periods=p["vol_lookback"]).mean()

    # --- Session filter ---
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        hour = pd.to_datetime(df["Time"]).dt.hour
    else:
        hour = df.index.to_series().apply(lambda x: 12)

    london_session = (hour >= 7) & (hour < 9)
    ny_session = (hour >= 13) & (hour < 15)
    in_session = london_session | ny_session

    # --- Conditions (use shifted ATR to avoid look-ahead) ---
    atr_prev = df["ATR"].shift(1)
    momentum = df["momentum"]  # already shifted
    vol_current = df[vol_col].shift(1)  # previous bar's volume
    vol_avg = df["vol_avg"]

    # Bullish momentum
    bull_momentum = momentum > (p["momentum_threshold"] * atr_prev)
    # Current bar closes up (bullish)
    bull_close = df["Close"] > df["Open"]

    # Bearish momentum
    bear_momentum = momentum < -(p["momentum_threshold"] * atr_prev)
    # Current bar closes down (bearish)
    bear_close = df["Close"] < df["Open"]

    # Volume spike
    vol_spike = vol_current > (p["vol_multiplier"] * vol_avg)

    # --- Signal generation ---
    df["signal"] = 0
    long_cond = bull_momentum & bull_close & vol_spike & in_session
    short_cond = bear_momentum & bear_close & vol_spike & in_session

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # --- Throttle: max 1 trade per session (120 bars = 2 hours) ---
    signals = df["signal"].values.copy()
    cooldown = 120
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
