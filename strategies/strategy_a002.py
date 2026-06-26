"""
Strategy A002: London Session Breakout
Family  : Session Breakout
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Trade breakouts from the Asian range at London open

Parameters:
  asian_start_hour: 0   Asian session start (UTC)
  asian_end_hour: 7     Asian session end / London open (UTC)
  london_end_hour: 10   Stop entering after this hour (UTC)
  vol_mult: 1.5         Current volume must exceed vol_mult * avg volume
  vol_avg_period: 20    Volume averaging window
  atr_period: 14
  sl_atr: 1.2
  tp_atr: 2.0

Entry  : Long  — price > Asian high, volume filter, within London window
         Short — price < Asian low,  volume filter, within London window
Exit   : SL = sl_atr * ATR(14)  |  TP = tp_atr * ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "asian_start_hour": 0,
    "asian_end_hour": 7,
    "london_end_hour": 10,
    "vol_mult": 1.5,
    "vol_avg_period": 20,
    "atr_period": 14,
    "sl_atr": 1.2,
    "tp_atr": 2.0,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- ATR (always required) ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # --- Parse time column ---
    df["_dt"] = pd.to_datetime(df["time"])
    df["_hour"] = df["_dt"].dt.hour
    df["_date"] = df["_dt"].dt.date

    # --- Build Asian session high/low per day ---
    asian_mask = (df["_hour"] >= p["asian_start_hour"]) & (df["_hour"] < p["asian_end_hour"])
    asian_data = df.loc[asian_mask].groupby("_date").agg(
        asian_high=("High", "max"),
        asian_low=("Low", "min"),
    )
    df = df.merge(asian_data, left_on="_date", right_index=True, how="left")

    # --- Volume filter ---
    df["vol_avg"] = df["Volume"].rolling(window=p["vol_avg_period"], min_periods=1).mean()
    vol_ok = df["Volume"] > p["vol_mult"] * df["vol_avg"]

    # --- London session window ---
    london_window = (df["_hour"] >= p["asian_end_hour"]) & (df["_hour"] < p["london_end_hour"])

    # --- Breakout detection (use shift(1) to avoid look-ahead) ---
    prev_close = df["Close"].shift(1)
    prev_asian_high = df["asian_high"].shift(1)
    prev_asian_low = df["asian_low"].shift(1)

    long_cond = london_window & vol_ok & (prev_close > prev_asian_high)
    short_cond = london_window & vol_ok & (prev_close < prev_asian_low)

    df["signal"] = 0
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # --- Only take first signal per day to keep signals sparse ---
    signalled = df["signal"] != 0
    df["_daily_sig_count"] = signalled.groupby(df["_date"]).cumsum()
    df.loc[df["_daily_sig_count"] > 1, "signal"] = 0

    # --- Clean up helper columns ---
    df.drop(columns=["_dt", "_hour", "_date", "asian_high", "asian_low",
                      "vol_avg", "_daily_sig_count"], inplace=True)

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
