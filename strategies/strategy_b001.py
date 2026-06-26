"""
Strategy B001: Pullback to EMA in Strong Trend
Family  : Trend-Following / Pullback
Goal    : XAUUSD-SCALPER-X10 — high win-rate via buying dips in confirmed trends
Timeframe: M1 (XAUUSD)
Description:
    Detect strong trend via ADX>30 + stacked EMAs (8>21>50 for long).
    Wait for price to pull back to EMA(21) after being above it 10+ bars.
    Enter long when first candle touches EMA(21) then closes above it.
    Wide SL (below EMA(50)), tight TP (ride the bounce).
    Session filter: 08:00-18:00 UTC only.

Parameters:
  ema_fast: 8
  ema_mid: 21
  ema_slow: 50
  adx_period: 14
  adx_threshold: 30
  atr_period: 14
  sl_atr: 2.5
  tp_atr: 1.0
  bars_above_ema: 10
  session_start: 8
  session_end: 18
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "ema_fast": 8,
    "ema_mid": 21,
    "ema_slow": 50,
    "adx_period": 14,
    "adx_threshold": 30,
    "atr_period": 14,
    "sl_atr": 2.5,
    "tp_atr": 1.0,
    "bars_above_ema": 10,
    "session_start": 8,
    "session_end": 18,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- Indicators ---
    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_mid"] = ta.trend.ema_indicator(df["Close"], window=p["ema_mid"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
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
        hour = df.index.to_series().apply(lambda x: 12)  # fallback: always in session
    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # --- Trend conditions (use shifted values to avoid look-ahead) ---
    ema_f = df["EMA_fast"].shift(1)
    ema_m = df["EMA_mid"].shift(1)
    ema_s = df["EMA_slow"].shift(1)
    adx = df["ADX"].shift(1)
    close_prev = df["Close"].shift(1)
    low_curr = df["Low"]
    close_curr = df["Close"]

    strong_uptrend = (adx > p["adx_threshold"]) & (ema_f > ema_m) & (ema_m > ema_s)
    strong_downtrend = (adx > p["adx_threshold"]) & (ema_f < ema_m) & (ema_m < ema_s)

    # --- Count consecutive bars above/below EMA_mid ---
    # Price above EMA_mid (shifted — checking previous bar state)
    above_ema_mid = (close_prev > ema_m).astype(int)
    below_ema_mid = (close_prev < ema_m).astype(int)

    # Rolling sum of bars above/below EMA_mid over lookback window
    bars_above = above_ema_mid.rolling(window=p["bars_above_ema"], min_periods=p["bars_above_ema"]).sum()
    bars_below = below_ema_mid.rolling(window=p["bars_above_ema"], min_periods=p["bars_above_ema"]).sum()

    # --- Pullback detection ---
    # Long: price was above EMA_mid for 10+ bars, now touches it (Low <= EMA_mid) but closes above
    pullback_long = (
        (bars_above >= p["bars_above_ema"])
        & (low_curr <= df["EMA_mid"])  # candle touches EMA_mid
        & (close_curr > df["EMA_mid"])  # but closes above it
    )

    # Short: price was below EMA_mid for 10+ bars, now touches it (High >= EMA_mid) but closes below
    pullback_short = (
        (bars_below >= p["bars_above_ema"])
        & (df["High"] >= df["EMA_mid"])  # candle touches EMA_mid
        & (close_curr < df["EMA_mid"])  # but closes below it
    )

    # --- Signal generation ---
    df["signal"] = 0
    long_cond = strong_uptrend & pullback_long & in_session
    short_cond = strong_downtrend & pullback_short & in_session

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # --- Throttle: max 1 signal per 60 bars (~ 1 hour cooldown) ---
    signals = df["signal"].values.copy()
    cooldown = 60
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
