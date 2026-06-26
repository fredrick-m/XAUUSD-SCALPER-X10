"""
Strategy B006: Triple Moving Average Ribbon Scalp
Family  : EMA Ribbon
Goal    : High win-rate M1 scalp via perfectly stacked EMAs + MACD confirmation
Timeframe: M1 (XAUUSD)

Entry  : EMA(5)>EMA(13)>EMA(34) stacked 20+ bars, price within 0.5 ATR of EMA(5),
         MACD histogram positive & increasing (long). Mirror for short.
Exit   : SL = 2.5 × ATR  |  TP = 1.0 × ATR
Session: 07:00-20:00 UTC
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "ema_fast": 5,
    "ema_mid": 13,
    "ema_slow": 34,
    "atr_period": 14,
    "sl_atr": 2.5,
    "tp_atr": 1.0,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "stack_bars": 20,
    "price_atr_dist": 0.5,
    "session_start": 7,
    "session_end": 20,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # --- Indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["EMA5"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA13"] = ta.trend.ema_indicator(df["Close"], window=p["ema_mid"])
    df["EMA34"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])

    macd_obj = ta.trend.MACD(
        df["Close"],
        window_slow=p["macd_slow"],
        window_fast=p["macd_fast"],
        window_sign=p["macd_signal"],
    )
    df["MACD_hist"] = macd_obj.macd_diff()

    # --- Session filter ---
    if "time" in df.columns:
        df["hour"] = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        df["hour"] = pd.to_datetime(df["Time"]).dt.hour
    else:
        df["hour"] = 12  # fallback: always in session

    in_session = (df["hour"] >= p["session_start"]) & (df["hour"] < p["session_end"])

    # --- EMA stacking ---
    bullish_stack = (df["EMA5"] > df["EMA13"]) & (df["EMA13"] > df["EMA34"])
    bearish_stack = (df["EMA5"] < df["EMA13"]) & (df["EMA13"] < df["EMA34"])

    # Count consecutive bars of stacking
    bull_streak = bullish_stack.astype(int)
    bull_group = (~bullish_stack).cumsum()
    bull_count = bull_streak.groupby(bull_group).cumsum()

    bear_streak = bearish_stack.astype(int)
    bear_group = (~bearish_stack).cumsum()
    bear_count = bear_streak.groupby(bear_group).cumsum()

    confirmed_bull = bull_count >= p["stack_bars"]
    confirmed_bear = bear_count >= p["stack_bars"]

    # --- Price close to EMA5 ---
    price_dist = (df["Close"] - df["EMA5"]).abs()
    close_to_ema5 = price_dist < (p["price_atr_dist"] * df["ATR"])

    # --- MACD histogram conditions (use .shift(1) for prior bar) ---
    macd_bull = (df["MACD_hist"].shift(1) > 0) & (
        df["MACD_hist"].shift(1) > df["MACD_hist"].shift(2)
    )
    macd_bear = (df["MACD_hist"].shift(1) < 0) & (
        df["MACD_hist"].shift(1) < df["MACD_hist"].shift(2)
    )

    # --- Signals ---
    df["signal"] = 0

    long_cond = (
        in_session
        & confirmed_bull.shift(1)
        & close_to_ema5.shift(1)
        & macd_bull
    )
    short_cond = (
        in_session
        & confirmed_bear.shift(1)
        & close_to_ema5.shift(1)
        & macd_bear
    )

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # --- Cleanup ---
    df.drop(
        columns=["EMA5", "EMA13", "EMA34", "MACD_hist", "hour"],
        inplace=True,
        errors="ignore",
    )
    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
