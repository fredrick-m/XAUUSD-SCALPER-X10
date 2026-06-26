"""
Strategy A009: Stochastic + Ichimoku
Family  : Momentum + Cloud
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Use Stochastic Oscillator crossovers filtered by Ichimoku Cloud
             position and Tenkan/Kijun alignment for high-probability entries.

Parameters:
  atr_period: 14
  sl_atr: 1.2
  tp_atr: 2.0
  stoch_k: 14
  stoch_d: 3
  stoch_smooth: 3
  stoch_long: 20    — %K must be below this for longs
  stoch_short: 80   — %K must be above this for shorts
  tenkan: 9
  kijun: 26
  senkou_b: 52

Entry Long : Stoch %K < 20 and crosses above %D, price above Kumo, Tenkan > Kijun
Entry Short: Stoch %K > 80 and crosses below %D, price below Kumo, Tenkan < Kijun
Exit       : SL = sl_atr × ATR  |  TP = tp_atr × ATR
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_period": 14,
    "sl_atr": 1.2,
    "tp_atr": 2.0,
    "stoch_k": 14,
    "stoch_d": 3,
    "stoch_smooth": 3,
    "stoch_long": 20,
    "stoch_short": 80,
    "tenkan": 9,
    "kijun": 26,
    "senkou_b": 52,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # Core ATR
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # --- Stochastic Oscillator ---
    stoch = ta.momentum.StochasticOscillator(
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        window=p["stoch_k"],
        smooth_window=p["stoch_smooth"],
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # --- Ichimoku components ---
    # Tenkan-sen (conversion line): midpoint of highest high and lowest low over window
    df["tenkan"] = (
        df["High"].rolling(p["tenkan"]).max() + df["Low"].rolling(p["tenkan"]).min()
    ) / 2.0

    # Kijun-sen (base line)
    df["kijun"] = (
        df["High"].rolling(p["kijun"]).max() + df["Low"].rolling(p["kijun"]).min()
    ) / 2.0

    # Senkou Span A (leading span A) = (Tenkan + Kijun) / 2, shifted forward 26
    df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2.0).shift(p["kijun"])

    # Senkou Span B (leading span B) = midpoint of 52-period high/low, shifted forward 26
    df["senkou_b"] = (
        (
            df["High"].rolling(p["senkou_b"]).max()
            + df["Low"].rolling(p["senkou_b"]).min()
        )
        / 2.0
    ).shift(p["kijun"])

    # Kumo (cloud) boundaries
    kumo_top = df[["senkou_a", "senkou_b"]].max(axis=1)
    kumo_bottom = df[["senkou_a", "senkou_b"]].min(axis=1)

    # --- Conditions ---
    # Price vs cloud
    above_cloud = df["Close"] > kumo_top
    below_cloud = df["Close"] < kumo_bottom

    # Tenkan / Kijun alignment
    tenkan_above_kijun = df["tenkan"] > df["kijun"]
    tenkan_below_kijun = df["tenkan"] < df["kijun"]

    # Stochastic crossovers (use .shift(1) to avoid look-ahead)
    k_prev = df["stoch_k"].shift(1)
    d_prev = df["stoch_d"].shift(1)
    k_cross_above_d = (k_prev <= d_prev) & (df["stoch_k"] > df["stoch_d"])
    k_cross_below_d = (k_prev >= d_prev) & (df["stoch_k"] < df["stoch_d"])

    stoch_oversold = df["stoch_k"] < p["stoch_long"]
    stoch_overbought = df["stoch_k"] > p["stoch_short"]

    # --- Signals ---
    df["signal"] = 0

    long_cond = (
        stoch_oversold
        & k_cross_above_d
        & above_cloud
        & tenkan_above_kijun
    )
    short_cond = (
        stoch_overbought
        & k_cross_below_d
        & below_cloud
        & tenkan_below_kijun
    )

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
