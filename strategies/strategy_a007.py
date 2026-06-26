"""
Strategy A007: Order Block Detector
Family  : Smart Money / Order Flow
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Detect institutional order blocks (last opposing candle before an
             impulsive move) and trade the retracement back into the zone.

Parameters:
  atr_period: 14
  sl_atr: 1.0
  tp_atr: 2.5
  impulse_bars: 3        — consecutive same-direction candles to confirm impulse
  impulse_atr_mult: 2.0  — total impulse range must exceed this × ATR
  ob_expiry: 100         — order block expires after N bars
  max_active_obs: 5      — max tracked order blocks per side

Entry Long : Price retraces into a bullish order block zone (Low <= OB High)
Entry Short: Price retraces into a bearish order block zone (High >= OB Low)
Exit       : SL = sl_atr × ATR  |  TP = tp_atr × ATR
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "atr_period": 14,
    "sl_atr": 1.0,
    "tp_atr": 2.5,
    "impulse_bars": 3,
    "impulse_atr_mult": 2.0,
    "ob_expiry": 100,
    "max_active_obs": 5,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()

    # Core indicator
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    n = len(df)
    signals = np.zeros(n, dtype=int)
    impulse_bars = p["impulse_bars"]
    impulse_mult = p["impulse_atr_mult"]
    ob_expiry = p["ob_expiry"]
    max_obs = p["max_active_obs"]

    # Pre-compute arrays for speed
    opens = df["Open"].values
    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    atr_vals = df["ATR"].values

    # Track order blocks as lists of dicts
    # Each OB: {"high": float, "low": float, "bar": int}
    bullish_obs = []  # zones to go long (last bearish candle before bullish impulse)
    bearish_obs = []  # zones to go short (last bullish candle before bearish impulse)

    for i in range(impulse_bars + 1, n):
        atr_i = atr_vals[i]
        if np.isnan(atr_i) or atr_i == 0:
            continue

        # --- Detect new order blocks at bar i ---
        # Check if bars [i-impulse_bars+1 .. i] form a bullish impulse
        all_bullish = True
        for k in range(i - impulse_bars + 1, i + 1):
            if closes[k] <= opens[k]:
                all_bullish = False
                break
        if all_bullish:
            impulse_range = closes[i] - opens[i - impulse_bars + 1]
            if impulse_range > impulse_mult * atr_i:
                # The bar before the impulse must be bearish
                ob_bar = i - impulse_bars
                if ob_bar >= 0 and closes[ob_bar] < opens[ob_bar]:
                    ob = {"high": highs[ob_bar], "low": lows[ob_bar], "bar": ob_bar}
                    bullish_obs.append(ob)
                    if len(bullish_obs) > max_obs:
                        bullish_obs.pop(0)

        # Check if bars [i-impulse_bars+1 .. i] form a bearish impulse
        all_bearish = True
        for k in range(i - impulse_bars + 1, i + 1):
            if closes[k] >= opens[k]:
                all_bearish = False
                break
        if all_bearish:
            impulse_range = opens[i - impulse_bars + 1] - closes[i]
            if impulse_range > impulse_mult * atr_i:
                ob_bar = i - impulse_bars
                if ob_bar >= 0 and closes[ob_bar] > opens[ob_bar]:
                    ob = {"high": highs[ob_bar], "low": lows[ob_bar], "bar": ob_bar}
                    bearish_obs.append(ob)
                    if len(bearish_obs) > max_obs:
                        bearish_obs.pop(0)

        # --- Expire old order blocks ---
        bullish_obs = [ob for ob in bullish_obs if (i - ob["bar"]) <= ob_expiry]
        bearish_obs = [ob for ob in bearish_obs if (i - ob["bar"]) <= ob_expiry]

        # --- Check for retracement into order blocks ---
        # Long signal: price retraces down into a bullish OB zone
        for ob in bullish_obs:
            if lows[i] <= ob["high"] and closes[i] >= ob["low"]:
                signals[i] = 1
                # Remove the used OB so we don't re-enter
                bullish_obs.remove(ob)
                break

        if signals[i] != 0:
            continue

        # Short signal: price retraces up into a bearish OB zone
        for ob in bearish_obs:
            if highs[i] >= ob["low"] and closes[i] <= ob["high"]:
                signals[i] = -1
                bearish_obs.remove(ob)
                break

    df["signal"] = signals
    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
