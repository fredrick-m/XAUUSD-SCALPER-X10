"""
Strategy B005: Engulfing Pattern with Volume Spike
Family  : Candlestick Pattern / Price Action
Goal    : XAUUSD-SCALPER-X10 — high win-rate engulfing patterns confirmed by volume
Timeframe: M1 (XAUUSD)
Description:
    Detect bullish engulfing: current bar's body fully engulfs previous bar's body,
    AND current Close > previous High.
    Detect bearish engulfing: opposite.
    Volume spike: current volume > 2x 20-bar average volume.
    Trend alignment: EMA(20) slope must agree (EMA(20) > EMA(20).shift(5) for long).
    Session: 07:00-20:00 UTC only.

Parameters:
  ema_slope_period: 20
  ema_slope_lookback: 5
  vol_lookback: 20
  vol_multiplier: 2.0
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 1.0
  session_start: 7
  session_end: 20
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "ema_slope_period": 20,
    "ema_slope_lookback": 5,
    "vol_lookback": 20,
    "vol_multiplier": 2.0,
    "atr_period": 14,
    "sl_atr": 2.0,
    "tp_atr": 1.0,
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
    df["EMA_slope"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slope_period"])

    # Volume
    vol_col = "Volume" if "Volume" in df.columns else "tick_volume"
    if vol_col not in df.columns:
        df["Volume"] = 1
        vol_col = "Volume"
    df["vol_avg"] = df[vol_col].shift(1).rolling(
        window=p["vol_lookback"], min_periods=p["vol_lookback"]
    ).mean()

    # --- Session filter ---
    if "time" in df.columns:
        hour = pd.to_datetime(df["time"]).dt.hour
    elif "Time" in df.columns:
        hour = pd.to_datetime(df["Time"]).dt.hour
    else:
        hour = df.index.to_series().apply(lambda x: 12)
    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # --- Candlestick pattern detection ---
    # Use shifted values for the "previous" candle relative to signal bar
    # Signal bar = current bar (i). Previous candle = shift(1).
    # We detect the pattern on the PREVIOUS completed candle pair: shift(1) engulfs shift(2)
    # Then signal on current bar.

    prev_open = df["Open"].shift(1)
    prev_close = df["Close"].shift(1)
    prev_high = df["High"].shift(1)
    prev_low = df["Low"].shift(1)
    prev_body_top = np.maximum(prev_open, prev_close)
    prev_body_bot = np.minimum(prev_open, prev_close)

    prev2_open = df["Open"].shift(2)
    prev2_close = df["Close"].shift(2)
    prev2_high = df["High"].shift(2)
    prev2_body_top = np.maximum(prev2_open, prev2_close)
    prev2_body_bot = np.minimum(prev2_open, prev2_close)

    # Bullish engulfing: previous bar (shift(1)) engulfs the bar before it (shift(2))
    # - shift(1) is bullish (close > open)
    # - shift(1) body fully contains shift(2) body
    # - shift(1) close > shift(2) high (strong engulfing)
    bullish_engulf = (
        (prev_close > prev_open)  # prev bar is bullish
        & (prev2_close < prev2_open)  # bar before was bearish
        & (prev_body_bot <= prev2_body_bot)  # engulfing body covers lower
        & (prev_body_top >= prev2_body_top)  # engulfing body covers upper
        & (prev_close > prev2_high)  # close above previous high = strong
    )

    # Bearish engulfing: opposite
    bearish_engulf = (
        (prev_close < prev_open)  # prev bar is bearish
        & (prev2_close > prev2_open)  # bar before was bullish
        & (prev_body_top >= prev2_body_top)  # engulfing body covers upper
        & (prev_body_bot <= prev2_body_bot)  # engulfing body covers lower
        & (prev_close < df["Low"].shift(2))  # close below previous low = strong
    )

    # --- Volume spike (on the engulfing bar = shift(1)) ---
    prev_vol = df[vol_col].shift(1)
    vol_spike = prev_vol > (p["vol_multiplier"] * df["vol_avg"])

    # --- Trend alignment: EMA slope ---
    ema_slope = df["EMA_slope"].shift(1)
    ema_slope_lagged = df["EMA_slope"].shift(1 + p["ema_slope_lookback"])
    ema_rising = ema_slope > ema_slope_lagged
    ema_falling = ema_slope < ema_slope_lagged

    # --- Signal generation ---
    df["signal"] = 0

    long_cond = bullish_engulf & vol_spike & ema_rising & in_session
    short_cond = bearish_engulf & vol_spike & ema_falling & in_session

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    # --- Throttle: cooldown of 60 bars between signals ---
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
