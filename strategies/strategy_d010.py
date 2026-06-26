"""
D010 - Pin Bar + Key Level (M5)
Ultra-selective: Detects pin bars (long wick > 2x body, small body)
at key levels (within 1 ATR of 100-bar high/low). Volume and EMA
trend confirmation. Targets ~100-300 signals over 200K bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 2.0,
    "tp_atr": 3.0,
    "atr_period": 14,
    "cooldown": 80,
    "wick_body_ratio": 2.0,
    "key_level_window": 100,
    "key_level_atr_mult": 1.0,
    "ema_trend": 50,
    "vol_mult": 1.5,
    "vol_window": 50,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])
    df["vol_avg"] = df["Volume"].rolling(window=p["vol_window"]).mean()

    # Key levels: rolling 100-bar high and low
    df["key_high"] = df["High"].rolling(window=p["key_level_window"]).max()
    df["key_low"] = df["Low"].rolling(window=p["key_level_window"]).min()

    # Pin bar detection
    df["body"] = (df["Close"] - df["Open"]).abs()
    df["upper_wick"] = df["High"] - df[["Close", "Open"]].max(axis=1)
    df["lower_wick"] = df[["Close", "Open"]].min(axis=1) - df["Low"]

    # Ensure body is not zero for ratio calculation (use small epsilon)
    body_safe = df["body"].replace(0, 1e-10)

    # Bullish pin bar: lower wick > 2x body, close > open (bullish candle)
    df["bull_pin"] = (
        (df["lower_wick"] > p["wick_body_ratio"] * body_safe)
        & (df["Close"] > df["Open"])
    ).astype(int)

    # Bearish pin bar: upper wick > 2x body, close < open (bearish candle)
    df["bear_pin"] = (
        (df["upper_wick"] > p["wick_body_ratio"] * body_safe)
        & (df["Close"] < df["Open"])
    ).astype(int)

    # Shifted indicators (no lookahead)
    bull_pin = df["bull_pin"].shift(1)
    bear_pin = df["bear_pin"].shift(1)
    close = df["Close"].shift(1)
    low_prev = df["Low"].shift(1)
    high_prev = df["High"].shift(1)
    key_low = df["key_low"].shift(1)
    key_high = df["key_high"].shift(1)
    atr = df["ATR"].shift(1)
    ema = df["EMA_trend"].shift(1)
    vol = df["Volume"].shift(1)
    vol_avg = df["vol_avg"].shift(1)

    # Key level proximity
    near_key_low = (low_prev - key_low).abs() <= p["key_level_atr_mult"] * atr
    near_key_high = (high_prev - key_high).abs() <= p["key_level_atr_mult"] * atr

    # Long: bullish pin bar near 100-bar low, above EMA trend, volume surge
    long_cond = (
        (bull_pin == 1)
        & near_key_low
        & (close > ema)
        & (vol > p["vol_mult"] * vol_avg)
    )

    # Short: bearish pin bar near 100-bar high, below EMA trend, volume surge
    short_cond = (
        (bear_pin == 1)
        & near_key_high
        & (close < ema)
        & (vol > p["vol_mult"] * vol_avg)
    )

    df["raw_signal"] = 0
    df.loc[long_cond, "raw_signal"] = 1
    df.loc[short_cond, "raw_signal"] = -1

    # Vectorized cooldown
    raw = df["raw_signal"].copy()
    cooldown = p["cooldown"]
    last_signal_idx = -cooldown - 1
    for i in range(len(raw)):
        if raw.iloc[i] != 0:
            if i - last_signal_idx > cooldown:
                last_signal_idx = i
            else:
                raw.iloc[i] = 0
    df["signal"] = raw

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
