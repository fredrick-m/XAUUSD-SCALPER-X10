"""
Strategy A006: VWAP Reversion
Family  : Mean-Reversion / VWAP
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Fade extreme deviations from session VWAP when price starts reverting.

Parameters:
  atr_period: 14
  sl_atr: 1.0
  tp_atr: 1.2
  vwap_atr_threshold: 1.5   — distance from VWAP in ATR multiples to qualify
  vol_lookback: 50           — bars for volume moving average
  session_start: 8           — UTC hour session open
  session_end: 20            — UTC hour session close

Entry Long : Close < VWAP - threshold*ATR, Close > Open (reverting up), volume > avg
Entry Short: Close > VWAP + threshold*ATR, Close < Open (reverting down), volume > avg
Exit       : SL = sl_atr × ATR  |  TP = tp_atr × ATR
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_period": 14,
    "sl_atr": 1.0,
    "tp_atr": 1.2,
    "vwap_atr_threshold": 1.5,
    "vol_lookback": 50,
    "session_start": 8,
    "session_end": 20,
}


def _compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Session-resetting VWAP: cumulative(volume*typical_price) / cumulative(volume) per day."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol_tp = typical_price * df["Volume"]

    # Day boundary: detect when the date changes
    day = df["time"].dt.date
    day_change = day != day.shift(1)

    # Cumulative sums that reset each day
    cum_vol_tp = pd.Series(np.nan, index=df.index, dtype=float)
    cum_vol = pd.Series(np.nan, index=df.index, dtype=float)

    running_vol_tp = 0.0
    running_vol = 0.0
    for i in df.index:
        if day_change.iloc[i] if isinstance(i, int) else day_change.loc[i]:
            running_vol_tp = 0.0
            running_vol = 0.0
        running_vol_tp += vol_tp.iloc[i] if isinstance(i, int) else vol_tp.loc[i]
        running_vol += df["Volume"].iloc[i] if isinstance(i, int) else df["Volume"].loc[i]
        if isinstance(i, int):
            cum_vol_tp.iloc[i] = running_vol_tp
            cum_vol.iloc[i] = running_vol
        else:
            cum_vol_tp.loc[i] = running_vol_tp
            cum_vol.loc[i] = running_vol

    vwap = cum_vol_tp / cum_vol.replace(0, np.nan)
    return vwap


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["VWAP"] = _compute_vwap(df)
    df["vol_ma"] = df["Volume"].rolling(window=p["vol_lookback"]).mean()

    # Session filter
    hour = df["time"].dt.hour
    in_session = (hour >= p["session_start"]) & (hour < p["session_end"])

    # Volume confirmation
    vol_above_avg = df["Volume"] > df["vol_ma"]

    # Reversion candle filters
    bullish_candle = df["Close"] > df["Open"]
    bearish_candle = df["Close"] < df["Open"]

    # Distance from VWAP
    threshold = p["vwap_atr_threshold"] * df["ATR"]
    below_vwap = df["Close"] < (df["VWAP"] - threshold)
    above_vwap = df["Close"] > (df["VWAP"] + threshold)

    # Signal generation
    df["signal"] = 0
    long_cond = below_vwap & bullish_candle & vol_above_avg & in_session
    short_cond = above_vwap & bearish_candle & vol_above_avg & in_session

    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
