"""
Strategy B004: Support/Resistance Bounce (Double Bottom/Top)
Family  : Support/Resistance / Price Action
Goal    : XAUUSD-SCALPER-X10 — high win-rate bounces off tested S/R levels
Timeframe: M1 (XAUUSD)
Description:
    Identify recent swing highs/lows (20-bar rolling max/min).
    Long when price bounces off swing low support (within 0.5*ATR) and closes bullish.
    Short when price bounces off swing high resistance and closes bearish.
    Require level tested at least twice (double bottom/top).
    ADX < 35 filter (works better in ranges/moderate trends).
    Session: 07:00-20:00 UTC.

Parameters:
  swing_lookback: 20
  sr_proximity: 0.5  (x ATR — how close to S/R level)
  sr_window: 120  (bars to look back for prior test of level)
  sr_tolerance: 0.3  (x ATR — how close prior test must be)
  adx_period: 14
  adx_max: 35
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 1.2
  session_start: 7
  session_end: 20
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "swing_lookback": 20,
    "sr_proximity": 0.5,
    "sr_window": 120,
    "sr_tolerance": 0.3,
    "adx_period": 14,
    "adx_max": 35,
    "atr_period": 14,
    "sl_atr": 2.0,
    "tp_atr": 1.2,
    "session_start": 7,
    "session_end": 20,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- Indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["ADX"] = ta.trend.adx(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )

    # --- Session filter ---
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        hour = pd.to_datetime(df["Time"]).dt.hour
    else:
        hour = df.index.to_series().apply(lambda x: 12)
    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # --- Swing highs and lows (shifted to avoid look-ahead) ---
    lookback = p["swing_lookback"]
    # Use shifted values: swing low/high computed from bars BEFORE the current bar
    df["swing_low"] = df["Low"].shift(1).rolling(window=lookback, min_periods=lookback).min()
    df["swing_high"] = df["High"].shift(1).rolling(window=lookback, min_periods=lookback).max()

    atr_prev = df["ATR"].shift(1)
    adx_prev = df["ADX"].shift(1)

    # --- Proximity to S/R level ---
    # Long: current Low is near swing_low (within sr_proximity * ATR)
    near_support = (df["Low"] - df["swing_low"]).abs() <= (p["sr_proximity"] * atr_prev)
    # Short: current High is near swing_high (within sr_proximity * ATR)
    near_resistance = (df["swing_high"] - df["High"]).abs() <= (p["sr_proximity"] * atr_prev)

    # --- Double test detection ---
    # Check if the swing low level was also tested in a wider lookback window
    # We look at the Low values in the [sr_window] bars before and check how many
    # times price came within sr_tolerance * ATR of the current swing_low
    sr_window = p["sr_window"]
    sr_tol = p["sr_tolerance"]

    # Vectorized double-test check using rolling operations
    # For each bar, count how many of the previous sr_window bars had Low near swing_low
    df["signal"] = 0

    # We need to iterate for the double-test check (hard to fully vectorize)
    signals = np.zeros(len(df), dtype=int)
    swing_low_arr = df["swing_low"].values
    swing_high_arr = df["swing_high"].values
    low_arr = df["Low"].values
    high_arr = df["High"].values
    close_arr = df["Close"].values
    open_arr = df["Open"].values
    atr_arr = atr_prev.values
    adx_arr = adx_prev.values
    session_arr = in_session.values

    cooldown = 90
    last_signal_idx = -cooldown

    for i in range(max(sr_window + lookback, 50), len(df)):
        if not session_arr[i]:
            continue
        if np.isnan(atr_arr[i]) or np.isnan(adx_arr[i]):
            continue
        if adx_arr[i] >= p["adx_max"]:
            continue
        if i - last_signal_idx < cooldown:
            continue

        atr_val = atr_arr[i]

        # --- Long: bounce off support ---
        if near_support.iloc[i] and close_arr[i] > open_arr[i]:  # bullish close
            sl = swing_low_arr[i]
            # Count prior tests of this support level
            test_count = 0
            for j in range(i - sr_window, i - lookback):
                if j < 0:
                    continue
                if abs(low_arr[j] - sl) <= sr_tol * atr_val:
                    test_count += 1
                    if test_count >= 2:
                        break
            if test_count >= 2:
                signals[i] = 1
                last_signal_idx = i
                continue

        # --- Short: bounce off resistance ---
        if near_resistance.iloc[i] and close_arr[i] < open_arr[i]:  # bearish close
            sh = swing_high_arr[i]
            test_count = 0
            for j in range(i - sr_window, i - lookback):
                if j < 0:
                    continue
                if abs(high_arr[j] - sh) <= sr_tol * atr_val:
                    test_count += 1
                    if test_count >= 2:
                        break
            if test_count >= 2:
                signals[i] = -1
                last_signal_idx = i

    df["signal"] = signals
    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
