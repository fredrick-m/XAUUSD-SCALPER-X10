"""
Strategy B010: Micro Structure Reversal
Family  : Mean Reversion / Exhaustion
Goal    : High win-rate M1 counter-trend entry after candle exhaustion
Timeframe: M1 (XAUUSD)

Entry  : 5+ consecutive same-direction candles (exhaustion detected).
         Reversal candle: opposite direction, body > avg body of last 5.
         Volume on reversal candle > 1.5× avg volume.
         EMA(50) supports reversal direction (price reverting toward EMA).
Exit   : SL = 2.5 × ATR  |  TP = 1.0 × ATR
Session: 07:00-20:00 UTC
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_period": 14,
    "sl_atr": 2.5,
    "tp_atr": 1.0,
    "ema_period": 50,
    "exhaust_min_bars": 5,
    "vol_multiplier": 1.5,
    "vol_avg_period": 20,
    "body_avg_period": 5,
    "session_start": 7,
    "session_end": 20,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # --- Indicators ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["EMA50"] = ta.trend.ema_indicator(df["Close"], window=p["ema_period"])

    # --- Session filter ---
    if "time" in df.columns:
        df["hour"] = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        df["hour"] = pd.to_datetime(df["Time"]).dt.hour
    else:
        df["hour"] = 12

    in_session = (df["hour"] >= p["session_start"]) & (df["hour"] < p["session_end"])

    # --- Candle direction ---
    df["bullish"] = (df["Close"] > df["Open"]).astype(int)
    df["bearish"] = (df["Close"] < df["Open"]).astype(int)

    # --- Count consecutive same-direction candles ---
    # Bullish streaks
    bull_group = (~df["bullish"].astype(bool)).cumsum()
    bull_streak = df["bullish"].groupby(bull_group).cumsum()

    # Bearish streaks
    bear_group = (~df["bearish"].astype(bool)).cumsum()
    bear_streak = df["bearish"].groupby(bear_group).cumsum()

    # --- Body size ---
    df["body"] = (df["Close"] - df["Open"]).abs()
    df["body_avg"] = df["body"].rolling(window=p["body_avg_period"]).mean()

    # --- Volume ---
    vol_col = "Volume" if "Volume" in df.columns else "tick_volume"
    vol = df[vol_col].astype(float)
    df["vol_avg"] = vol.rolling(window=p["vol_avg_period"]).mean()

    # --- Conditions (all using .shift(1) for the prior bar being the reversal candle) ---
    # The exhaustion run is on bars before the reversal candle
    # So: bars shift(2) through shift(exhaust_min_bars+1) were the run,
    # and shift(1) is the reversal candle

    # After bullish exhaustion (5+ bullish bars ending at shift(2)),
    # reversal candle at shift(1) is bearish
    bull_exhaust = bull_streak.shift(2) >= p["exhaust_min_bars"]
    bear_exhaust = bear_streak.shift(2) >= p["exhaust_min_bars"]

    # Reversal candle properties (at shift(1))
    rev_bearish = df["bearish"].shift(1) == 1  # bearish reversal after bull run
    rev_bullish = df["bullish"].shift(1) == 1  # bullish reversal after bear run

    # Reversal candle body larger than avg of last 5
    big_body = df["body"].shift(1) > df["body_avg"].shift(1)

    # Volume spike on reversal candle
    vol_spike = vol.shift(1) > (p["vol_multiplier"] * df["vol_avg"].shift(1))

    # EMA50 supports the reversal direction:
    # After bull exhaustion → short reversal → price should be above EMA50 (reverting down toward it)
    # After bear exhaustion → long reversal → price should be below EMA50 (reverting up toward it)
    price_above_ema = df["Close"].shift(1) > df["EMA50"].shift(1)
    price_below_ema = df["Close"].shift(1) < df["EMA50"].shift(1)

    # --- Signals ---
    df["signal"] = 0

    # Short: after bullish exhaustion, bearish reversal, price above EMA (reverting down)
    short_cond = (
        in_session
        & bull_exhaust
        & rev_bearish
        & big_body
        & vol_spike
        & price_above_ema
    )

    # Long: after bearish exhaustion, bullish reversal, price below EMA (reverting up)
    long_cond = (
        in_session
        & bear_exhaust
        & rev_bullish
        & big_body
        & vol_spike
        & price_below_ema
    )

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # --- Cleanup ---
    df.drop(
        columns=["EMA50", "hour", "bullish", "bearish", "body", "body_avg", "vol_avg"],
        inplace=True,
        errors="ignore",
    )
    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
