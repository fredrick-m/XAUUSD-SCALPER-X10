"""
F004 - VWAP Mean Reversion (M5)
Price deviates far from volume-weighted moving average, then reverts.
Contrarian strategy — decorrelated from trend-following D008v2.
Ultra-selective: target <300 signals over 200K M5 bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 2.0,
    "tp_atr": 3.0,
    "atr_period": 14,
    "cooldown": 100,
    "vwap_period": 60,          # bars for rolling VWAP
    "deviation_atr_mult": 3.0,  # price must deviate 3x ATR from VWAP
    "rsi_period": 14,
    "rsi_oversold": 25,         # RSI confirms exhaustion
    "rsi_overbought": 75,
    "ema_slope_period": 10,     # check if VWAP slope is flattening
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # ATR
    df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])

    # Rolling VWAP approximation
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"].replace(0, 1)  # avoid div by zero
    df["VWAP"] = (typical_price * vol).rolling(window=p["vwap_period"]).sum() / vol.rolling(window=p["vwap_period"]).sum()

    # RSI for exhaustion confirmation
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # Shift to avoid lookahead
    atr = df["ATR"].shift(1)
    close = df["Close"].shift(1)
    vwap = df["VWAP"].shift(1)
    rsi = df["RSI"].shift(1)

    # Distance from VWAP in ATR units
    dist = (close - vwap).abs()
    deviation_threshold = p["deviation_atr_mult"] * atr

    # Mean reversion signals
    # Long: price far below VWAP + RSI oversold (exhausted selling)
    long_cond = (
        (close < vwap - deviation_threshold) &
        (rsi < p["rsi_oversold"])
    )

    # Short: price far above VWAP + RSI overbought (exhausted buying)
    short_cond = (
        (close > vwap + deviation_threshold) &
        (rsi > p["rsi_overbought"])
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
