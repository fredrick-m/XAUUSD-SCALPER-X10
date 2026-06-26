"""
F001 - Momentum Breakout (M5)
Price breaks N-bar high/low with ATR expansion confirmation.
Ultra-selective: target <300 signals over 200K M5 bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 4.0,
    "atr_period": 14,
    "cooldown": 80,
    "lookback": 60,        # bars to check for high/low breakout
    "atr_expansion_mult": 1.3,
    "atr_avg_window": 50,
    "volume_mult": 1.5,    # volume must be 1.5x average
    "volume_avg_window": 30,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # ATR
    df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    df["ATR_avg"] = df["ATR"].rolling(window=p["atr_avg_window"]).mean()

    # Price breakout channels
    df["high_N"] = df["High"].rolling(window=p["lookback"]).max()
    df["low_N"] = df["Low"].rolling(window=p["lookback"]).min()

    # Volume filter
    df["vol_avg"] = df["Volume"].rolling(window=p["volume_avg_window"]).mean()

    # Shift everything by 1 to avoid lookahead
    atr = df["ATR"].shift(1)
    atr_avg = df["ATR_avg"].shift(1)
    close = df["Close"].shift(1)
    high_n = df["high_N"].shift(2)  # shift by 2 since high_N already includes current bar
    low_n = df["low_N"].shift(2)
    vol = df["Volume"].shift(1)
    vol_avg = df["vol_avg"].shift(1)

    # ATR expanding
    atr_expanding = atr > p["atr_expansion_mult"] * atr_avg

    # Volume surge
    vol_surge = vol > p["volume_mult"] * vol_avg

    # Breakout conditions
    long_cond = (close > high_n) & atr_expanding & vol_surge
    short_cond = (close < low_n) & atr_expanding & vol_surge

    df["raw_signal"] = 0
    df.loc[long_cond, "raw_signal"] = 1
    df.loc[short_cond, "raw_signal"] = -1

    # Cooldown
    raw = df["raw_signal"].copy()
    cooldown = p["cooldown"]
    last_signal_idx = -cooldown - 1
    for i in range(len(raw)):
        if raw.iloc[i] != 0:
            if i - last_signal_idx > cooldown:
                last_signal_idx = i
            else:
                raw.iloc[i] = 0
    df["signal"] = raw.fillna(0).astype(int)

    return df
