"""
G001 - EMA Stack + RSI Pullback (M5)
Trend-following with RSI-based entry timing. Enters when price pulls back
to RSI<40 during a confirmed bull trend (EMA 8>21>50 stacked 15+ bars),
or RSI>60 during confirmed bear trend.

Decorrelated from D008v2: uses RSI pullback instead of ATR expansion + price pullback.
Higher WR (60%+) with tighter TP, vs D008v2's lower WR with wider TP.

Best results: PF=1.19-1.47, WR=60-64%, DD=19-58%
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 1.5,
    "tp_atr": 2.0,
    "atr_period": 14,
    "cooldown": 80,
    "ema_fast": 8,
    "ema_mid": 21,
    "ema_slow": 50,
    "stack_bars": 15,
    "rsi_period": 14,
    "rsi_low": 40,
    "rsi_floor": 25,
    "rsi_high": 60,
    "rsi_ceil": 75,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_mid"] = ta.trend.ema_indicator(df["Close"], window=p["ema_mid"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])

    # EMA stacking conditions
    df["bull_stack"] = (
        (df["EMA_fast"] > df["EMA_mid"]) & (df["EMA_mid"] > df["EMA_slow"])
    ).astype(int)
    df["bear_stack"] = (
        (df["EMA_fast"] < df["EMA_mid"]) & (df["EMA_mid"] < df["EMA_slow"])
    ).astype(int)

    # Count consecutive bars of perfect stacking
    df["bull_break"] = (df["bull_stack"] != df["bull_stack"].shift(1)).astype(int)
    df["bull_group"] = df["bull_break"].cumsum()
    df["bull_consec"] = df.groupby("bull_group").cumcount() + 1
    df.loc[df["bull_stack"] == 0, "bull_consec"] = 0

    df["bear_break"] = (df["bear_stack"] != df["bear_stack"].shift(1)).astype(int)
    df["bear_group"] = df["bear_break"].cumsum()
    df["bear_consec"] = df.groupby("bear_group").cumcount() + 1
    df.loc[df["bear_stack"] == 0, "bear_consec"] = 0

    # Shifted to avoid lookahead
    rsi = df["RSI"].shift(1)
    bull_consec = df["bull_consec"].shift(1)
    bear_consec = df["bear_consec"].shift(1)

    # Long: bull trend confirmed (15+ bars) + RSI pulls back to 25-40 zone
    long_cond = (
        (bull_consec >= p["stack_bars"])
        & (rsi < p["rsi_low"])
        & (rsi > p["rsi_floor"])
    )

    # Short: bear trend confirmed (15+ bars) + RSI bounces to 60-75 zone
    short_cond = (
        (bear_consec >= p["stack_bars"])
        & (rsi > p["rsi_high"])
        & (rsi < p["rsi_ceil"])
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
    df["signal"] = raw

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
