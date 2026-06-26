"""
Strategy A004: ATR Squeeze Breakout
Family  : Volatility Breakout
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Detect volatility squeeze (ATR compression), then trade the
             breakout when squeeze releases, confirmed by rising ADX.

Parameters:
  atr_fast: 14        Fast ATR for squeeze detection
  atr_slow: 50        Slow ATR baseline
  squeeze_ratio: 0.5  Squeeze threshold: ATR_fast < ratio * ATR_slow
  min_squeeze_bars: 10  Minimum consecutive bars in squeeze
  ema_dir: 20         EMA for breakout direction
  adx_period: 14      ADX period
  atr_period: 14
  sl_atr: 1.0
  tp_atr: 2.5

Entry  : Squeeze ends (ATR_fast crosses above squeeze_ratio * ATR_slow)
         after >= min_squeeze_bars in squeeze.
         Direction from Close vs EMA(20).  ADX must be rising.
Exit   : SL = sl_atr * ATR(14)  |  TP = tp_atr * ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_fast": 14,
    "atr_slow": 50,
    "squeeze_ratio": 0.5,
    "min_squeeze_bars": 10,
    "ema_dir": 20,
    "adx_period": 14,
    "atr_period": 14,
    "sl_atr": 1.0,
    "tp_atr": 2.5,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # --- ATR (always required; also used for squeeze) ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    atr_fast = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_fast"]
    )
    atr_slow = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_slow"]
    )

    # --- Squeeze detection ---
    squeeze_threshold = p["squeeze_ratio"] * atr_slow
    in_squeeze = atr_fast < squeeze_threshold

    # Count consecutive bars in squeeze
    squeeze_group = (~in_squeeze).cumsum()
    squeeze_duration = in_squeeze.groupby(squeeze_group).cumsum()

    # Squeeze release: was in squeeze (shifted), now not in squeeze
    prev_in_squeeze = in_squeeze.shift(1).astype(bool).fillna(False)
    prev_duration = squeeze_duration.shift(1).fillna(0)
    squeeze_release = (~in_squeeze) & prev_in_squeeze & (prev_duration >= p["min_squeeze_bars"])

    # --- Direction via EMA ---
    df["ema_dir"] = ta.trend.ema_indicator(df["Close"], window=p["ema_dir"])

    # --- ADX rising confirmation ---
    df["adx"] = ta.trend.adx(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )
    adx_rising = df["adx"] > df["adx"].shift(1)

    # --- Signal logic (shift by 1 to avoid look-ahead) ---
    prev_close = df["Close"].shift(1)
    prev_ema = df["ema_dir"].shift(1)
    prev_adx_rising = adx_rising.shift(1).astype(bool).fillna(False)
    squeeze_release_prev = squeeze_release.shift(1).astype(bool).fillna(False)

    long_cond = squeeze_release_prev & (prev_close > prev_ema) & prev_adx_rising
    short_cond = squeeze_release_prev & (prev_close < prev_ema) & prev_adx_rising

    df["signal"] = 0
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
