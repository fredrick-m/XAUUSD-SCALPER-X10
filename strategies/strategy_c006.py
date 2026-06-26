"""
Strategy C006: Engulfing + EMA Trend (M5)
Family  : Candlestick + Trend
Goal    : XAUUSD-SCALPER-X10
Timeframe: M5 (XAUUSD)
Description: Bullish/bearish engulfing candle with EMA(50) trend filter,
             body-size filter, and session constraint.

Parameters:
  ema_trend: 50
  body_mult: 1.2
  body_lookback: 10
  session_start: 7
  session_end: 20
  cooldown: 15
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.0

Entry  : Bullish engulfing + price > EMA(50) → long
         Bearish engulfing + price < EMA(50) → short
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "ema_trend": 50,
    "body_mult": 1.2,
    "body_lookback": 10,
    "session_start": 7,
    "session_end": 20,
    "cooldown": 15,
    "atr_period": 14,
    "sl_atr": 2.0,
    "tp_atr": 3.0,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # --- candle body ---
    df["body"] = (df["Close"] - df["Open"]).abs()
    df["avg_body"] = df["body"].rolling(p["body_lookback"]).mean()

    # --- session filter (UTC hour) ---
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif df.index.dtype == "datetime64[ns]":
        hour = df.index.hour
    else:
        hour = pd.Series(12, index=df.index)  # fallback: always in-session

    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # --- engulfing detection (use .shift(1) to avoid look-ahead) ---
    prev_open = df["Open"].shift(1)
    prev_close = df["Close"].shift(1)
    curr_open = df["Open"].shift(1)   # signal on PREVIOUS bar's pattern
    curr_close = df["Close"].shift(1)

    # We detect the pattern on bar i-1 and fire signal on bar i
    prev2_open = df["Open"].shift(2)
    prev2_close = df["Close"].shift(2)
    prev1_open = df["Open"].shift(1)
    prev1_close = df["Close"].shift(1)

    bullish_engulf = (
        (prev1_close > prev1_open)          # current candle bullish
        & (prev2_close < prev2_open)         # previous candle bearish
        & (prev1_close > prev2_open)         # close > prev open
        & (prev1_open < prev2_close)         # open < prev close
    )

    bearish_engulf = (
        (prev1_close < prev1_open)           # current candle bearish
        & (prev2_close > prev2_open)         # previous candle bullish
        & (prev1_close < prev2_open)         # close < prev open
        & (prev1_open > prev2_close)         # open > prev close
    )

    # --- body size filter (shifted) ---
    big_body = df["body"].shift(1) > p["body_mult"] * df["avg_body"].shift(1)

    # --- trend filter (shifted) ---
    above_ema = df["Close"].shift(1) > df["EMA_trend"].shift(1)
    below_ema = df["Close"].shift(1) < df["EMA_trend"].shift(1)

    # --- raw signals ---
    long_raw = bullish_engulf & big_body & above_ema & in_session
    short_raw = bearish_engulf & big_body & below_ema & in_session

    df["signal"] = 0
    df.loc[long_raw, "signal"] = 1
    df.loc[short_raw, "signal"] = -1

    # --- cooldown ---
    cooldown = p["cooldown"]
    last_signal_bar = -cooldown - 1
    signals = df["signal"].values.copy()
    for i in range(len(signals)):
        if signals[i] != 0:
            if i - last_signal_bar <= cooldown:
                signals[i] = 0
            else:
                last_signal_bar = i
    df["signal"] = signals

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
