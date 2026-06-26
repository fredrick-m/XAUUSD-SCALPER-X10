"""
H001 - EMA Stack + Stochastic Pullback (M5)
Uses proven EMA(8/21/50) stack filter (20+ bars) with Stochastic %K/%D
pullback entry. Enters when Stoch drops below 20 in bull trend.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 2.5,
    "atr_period": 14,
    "cooldown": 100,
    "ema_fast": 8,
    "ema_mid": 21,
    "ema_slow": 50,
    "stack_bars": 20,
    "stoch_k": 14,
    "stoch_d": 3,
    "stoch_oversold": 20,
    "stoch_overbought": 80,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    stoch = ta.momentum.StochasticOscillator(
        df["High"], df["Low"], df["Close"],
        window=p["stoch_k"], smooth_window=p["stoch_d"]
    )
    df["Stoch_K"] = stoch.stoch()
    df["Stoch_D"] = stoch.stoch_signal()

    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_mid"] = ta.trend.ema_indicator(df["Close"], window=p["ema_mid"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])

    df["bull_stack"] = (
        (df["EMA_fast"] > df["EMA_mid"]) & (df["EMA_mid"] > df["EMA_slow"])
    ).astype(int)
    df["bear_stack"] = (
        (df["EMA_fast"] < df["EMA_mid"]) & (df["EMA_mid"] < df["EMA_slow"])
    ).astype(int)

    df["bull_break"] = (df["bull_stack"] != df["bull_stack"].shift(1)).astype(int)
    df["bull_group"] = df["bull_break"].cumsum()
    df["bull_consec"] = df.groupby("bull_group").cumcount() + 1
    df.loc[df["bull_stack"] == 0, "bull_consec"] = 0

    df["bear_break"] = (df["bear_stack"] != df["bear_stack"].shift(1)).astype(int)
    df["bear_group"] = df["bear_break"].cumsum()
    df["bear_consec"] = df.groupby("bear_group").cumcount() + 1
    df.loc[df["bear_stack"] == 0, "bear_consec"] = 0

    stoch_k = df["Stoch_K"].shift(1)
    bull_consec = df["bull_consec"].shift(1)
    bear_consec = df["bear_consec"].shift(1)

    long_cond = (
        (bull_consec >= p["stack_bars"])
        & (stoch_k < p["stoch_oversold"])
    )
    short_cond = (
        (bear_consec >= p["stack_bars"])
        & (stoch_k > p["stoch_overbought"])
    )

    df["raw_signal"] = 0
    df.loc[long_cond, "raw_signal"] = 1
    df.loc[short_cond, "raw_signal"] = -1

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
