"""
Strategy A010: Range Fade with Pivot Points
Family  : Pivot-Point Reversion
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Fade price at daily pivot support/resistance levels when RSI
             confirms overbought/oversold and ADX indicates range-bound market.

Parameters:
  atr_period: 14
  sl_atr: 0.8
  tp_atr: 1.0
  rsi_period: 14
  rsi_ob: 70        — overbought threshold for shorts
  rsi_os: 30        — oversold threshold for longs
  adx_period: 14
  adx_max: 30       — only trade when ADX < this (not trending)
  pivot_tolerance_atr: 0.3  — how close price must be to pivot level (in ATR)
  session_start: 7
  session_end: 20

Entry Short: Price near R1 or R2, RSI > 70, ADX < 30
Entry Long : Price near S1 or S2, RSI < 30, ADX < 30
Exit       : SL = sl_atr × ATR  |  TP = tp_atr × ATR
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_period": 14,
    "sl_atr": 0.824392,
    "tp_atr": 0.843627,
    "rsi_period": 14,
    "rsi_ob": 72,
    "rsi_os": 25,
    "adx_period": 16,
    "adx_max": 35,
    "pivot_tolerance_atr": 0.241721,
    "session_start": 7,
    "session_end": 20
}


def _compute_daily_pivots(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate classic daily pivot points from previous day's HLC.
    Adds columns: Pivot, R1, R2, S1, S2 — forward-filled within each day.
    """
    df = df.copy()
    df["_date"] = df["time"].dt.date

    # Get previous day's High, Low, Close
    daily = df.groupby("_date").agg(
        day_high=("High", "max"),
        day_low=("Low", "min"),
        day_close=("Close", "last"),
    )
    daily["Pivot"] = (daily["day_high"] + daily["day_low"] + daily["day_close"]) / 3.0
    daily["R1"] = 2.0 * daily["Pivot"] - daily["day_low"]
    daily["S1"] = 2.0 * daily["Pivot"] - daily["day_high"]
    daily["R2"] = daily["Pivot"] + (daily["day_high"] - daily["day_low"])
    daily["S2"] = daily["Pivot"] - (daily["day_high"] - daily["day_low"])

    # Shift by one day so today uses yesterday's pivots
    daily = daily.shift(1)

    # Map back to intraday bars
    pivot_map = daily[["Pivot", "R1", "R2", "S1", "S2"]]
    df = df.merge(pivot_map, left_on="_date", right_index=True, how="left")
    df.drop(columns=["_date"], inplace=True)

    return df


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # Core ATR
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # RSI
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # ADX (trend strength)
    df["ADX"] = ta.trend.adx(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )

    # Daily pivot points
    df = _compute_daily_pivots(df)

    # Session filter
    hour = df["time"].dt.hour
    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # Tolerance band for "touching" a pivot level
    tol = p["pivot_tolerance_atr"] * df["ATR"]

    # Proximity checks — price near resistance or support
    near_r1 = (df["High"] >= df["R1"] - tol) & (df["High"] <= df["R1"] + tol)
    near_r2 = (df["High"] >= df["R2"] - tol) & (df["High"] <= df["R2"] + tol)
    near_s1 = (df["Low"] >= df["S1"] - tol) & (df["Low"] <= df["S1"] + tol)
    near_s2 = (df["Low"] >= df["S2"] - tol) & (df["Low"] <= df["S2"] + tol)

    near_resistance = near_r1 | near_r2
    near_support = near_s1 | near_s2

    # Filters
    rsi_overbought = df["RSI"] > p["rsi_ob"]
    rsi_oversold = df["RSI"] < p["rsi_os"]
    adx_ranging = df["ADX"] < p["adx_max"]

    # Signal generation
    df["signal"] = 0

    short_cond = near_resistance & rsi_overbought & adx_ranging & in_session
    long_cond = near_support & rsi_oversold & adx_ranging & in_session

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
