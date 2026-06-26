"""
D007 - Multi-Indicator Alignment (M5)
Ultra-selective: ALL of RSI, MACD histogram, EMA trend, ADX, and
Stochastic must align simultaneously. Extremely rare confluence.
Targets ~100-300 signals over 200K bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 2.0,
    "tp_atr": 3.0,
    "atr_period": 14,
    "cooldown": 80,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 65,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "ema_trend": 50,
    "adx_period": 14,
    "adx_min": 20,
    "stoch_period": 14,
    "stoch_smooth": 3,
    "stoch_oversold": 30,
    "stoch_overbought": 70,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # MACD
    macd_ind = ta.trend.MACD(
        df["Close"],
        window_slow=p["macd_slow"],
        window_fast=p["macd_fast"],
        window_sign=p["macd_signal"],
    )
    df["MACD_hist"] = macd_ind.macd_diff()

    # EMA trend
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # ADX
    df["ADX"] = ta.trend.adx(
        df["High"], df["Low"], df["Close"], window=p["adx_period"]
    )

    # Stochastic
    stoch = ta.momentum.StochasticOscillator(
        df["High"], df["Low"], df["Close"],
        window=p["stoch_period"],
        smooth_window=p["stoch_smooth"],
    )
    df["Stoch_K"] = stoch.stoch()

    # Shifted indicators (no lookahead)
    rsi = df["RSI"].shift(1)
    macd_hist = df["MACD_hist"].shift(1)
    close = df["Close"].shift(1)
    ema = df["EMA_trend"].shift(1)
    adx = df["ADX"].shift(1)
    stoch_k = df["Stoch_K"].shift(1)

    # Long: ALL must align
    long_cond = (
        (rsi < p["rsi_oversold"])          # RSI oversold
        & (macd_hist > 0)                   # MACD histogram positive (momentum shifting up)
        & (close > ema)                     # above EMA (uptrend)
        & (adx > p["adx_min"])              # trending market
        & (stoch_k < p["stoch_oversold"])   # stochastic oversold
    )

    # Short: ALL must align (mirror)
    short_cond = (
        (rsi > p["rsi_overbought"])        # RSI overbought
        & (macd_hist < 0)                   # MACD histogram negative
        & (close < ema)                     # below EMA (downtrend)
        & (adx > p["adx_min"])              # trending market
        & (stoch_k > p["stoch_overbought"]) # stochastic overbought
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
