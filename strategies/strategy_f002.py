"""
F002 - RSI Divergence Reversal (M5)
Detects bearish divergence (price higher high, RSI lower high) and
bullish divergence (price lower low, RSI higher low).
Ultra-selective: target <300 signals over 200K M5 bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 3.5,
    "atr_period": 14,
    "cooldown": 100,
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "divergence_window": 30,  # bars to look back for divergence
    "min_price_move_atr": 1.0,  # minimum price move in ATR units for divergence
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # Find local highs and lows using rolling window
    win = p["divergence_window"]
    df["price_high_roll"] = df["High"].rolling(window=win).max()
    df["price_low_roll"] = df["Low"].rolling(window=win).min()
    df["rsi_high_roll"] = df["RSI"].rolling(window=win).max()
    df["rsi_low_roll"] = df["RSI"].rolling(window=win).min()

    # Shift to avoid lookahead
    atr = df["ATR"].shift(1)
    close = df["Close"].shift(1)
    rsi = df["RSI"].shift(1)

    # Current vs recent peaks/troughs (shifted by 1)
    prev_price_high = df["price_high_roll"].shift(win + 1)
    prev_rsi_high = df["rsi_high_roll"].shift(win + 1)
    curr_price_high = df["price_high_roll"].shift(1)
    curr_rsi_high = df["rsi_high_roll"].shift(1)

    prev_price_low = df["price_low_roll"].shift(win + 1)
    prev_rsi_low = df["rsi_low_roll"].shift(win + 1)
    curr_price_low = df["price_low_roll"].shift(1)
    curr_rsi_low = df["rsi_low_roll"].shift(1)

    min_move = p["min_price_move_atr"] * atr

    # Bearish divergence: price makes higher high, RSI makes lower high, RSI in overbought zone
    bear_div = (
        (curr_price_high > prev_price_high + min_move) &
        (curr_rsi_high < prev_rsi_high) &
        (rsi > p["rsi_overbought"])
    )

    # Bullish divergence: price makes lower low, RSI makes higher low, RSI in oversold zone
    bull_div = (
        (curr_price_low < prev_price_low - min_move) &
        (curr_rsi_low > prev_rsi_low) &
        (rsi < p["rsi_oversold"])
    )

    df["raw_signal"] = 0
    df.loc[bull_div, "raw_signal"] = 1   # buy on bullish divergence
    df.loc[bear_div, "raw_signal"] = -1  # sell on bearish divergence

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
