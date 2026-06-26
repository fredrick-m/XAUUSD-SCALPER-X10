"""
F005 - Keltner Channel + ADX Trend Strength (M5)
Combines Keltner Channel breakout with ADX trend strength filter.
Only enters when ADX confirms strong trend and price breaks channel.
Ultra-selective: target <300 signals over 200K M5 bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 4.5,
    "atr_period": 14,
    "cooldown": 90,
    "kc_period": 20,
    "kc_atr_mult": 2.0,    # Keltner channel width
    "adx_period": 14,
    "adx_threshold": 30,   # ADX must be above this for strong trend
    "adx_rising_bars": 5,  # ADX must be rising for N bars
    "ema_fast": 10,
    "ema_slow": 30,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # ATR
    df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])

    # Keltner Channels (EMA +/- mult * ATR)
    df["KC_mid"] = ta.trend.ema_indicator(df["Close"], window=p["kc_period"])
    kc_atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["kc_period"])
    df["KC_upper"] = df["KC_mid"] + p["kc_atr_mult"] * kc_atr
    df["KC_lower"] = df["KC_mid"] - p["kc_atr_mult"] * kc_atr

    # ADX for trend strength
    adx_indicator = ta.trend.ADXIndicator(df["High"], df["Low"], df["Close"], window=p["adx_period"])
    df["ADX"] = adx_indicator.adx()
    df["DI_plus"] = adx_indicator.adx_pos()
    df["DI_minus"] = adx_indicator.adx_neg()

    # EMAs for trend direction confirmation
    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])

    # ADX rising
    df["ADX_rising"] = (df["ADX"] > df["ADX"].shift(1)).rolling(window=p["adx_rising_bars"]).sum() == p["adx_rising_bars"]

    # Shift to avoid lookahead
    close = df["Close"].shift(1)
    kc_upper = df["KC_upper"].shift(1)
    kc_lower = df["KC_lower"].shift(1)
    adx = df["ADX"].shift(1)
    adx_rising = df["ADX_rising"].shift(1)
    di_plus = df["DI_plus"].shift(1)
    di_minus = df["DI_minus"].shift(1)
    ema_fast = df["EMA_fast"].shift(1)
    ema_slow = df["EMA_slow"].shift(1)

    # Strong trend conditions
    strong_trend = (adx > p["adx_threshold"]) & adx_rising

    # Long: price breaks above KC upper + strong uptrend + DI+ > DI- + EMA alignment
    long_cond = (
        (close > kc_upper) &
        strong_trend &
        (di_plus > di_minus) &
        (ema_fast > ema_slow)
    )

    # Short: price breaks below KC lower + strong downtrend + DI- > DI+ + EMA alignment
    short_cond = (
        (close < kc_lower) &
        strong_trend &
        (di_minus > di_plus) &
        (ema_fast < ema_slow)
    )

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
