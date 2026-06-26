"""
D005 - Support/Resistance Double Touch (M5)
Ultra-selective: Detects double bottom/top at rolling S/R levels.
Second touch must show RSI confirmation + EMA(100) trend alignment.
Targets ~100-300 signals over 200K bars.
"""
import pandas as pd
import numpy as np
import ta

PARAMS = {
    "sl_atr": 2.0,
    "tp_atr": 3.0,
    "atr_period": 14,
    "cooldown": 100,
    "sr_window": 100,
    "touch_lookback": 50,
    "touch_tolerance_atr": 0.5,
    "rsi_period": 14,
    "rsi_support": 40,
    "rsi_resistance": 60,
    "ema_trend": 100,
    "vol_mult": 1.3,
    "vol_window": 50,
}


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = df.copy()

    # Core indicators
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["EMA_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])
    df["vol_avg"] = df["Volume"].rolling(window=p["vol_window"]).mean()

    # Rolling S/R levels
    df["support"] = df["Low"].rolling(window=p["sr_window"]).min()
    df["resistance"] = df["High"].rolling(window=p["sr_window"]).max()

    # Tolerance for "touching" a level
    tol = p["touch_tolerance_atr"] * df["ATR"]

    # Detect touches of support (Low within tolerance of rolling support)
    df["touch_support"] = (df["Low"] <= df["support"] + tol).astype(int)
    # Detect touches of resistance (High within tolerance of rolling resistance)
    df["touch_resistance"] = (df["High"] >= df["resistance"] - tol).astype(int)

    # Count touches in lookback window
    df["support_touches"] = df["touch_support"].rolling(window=p["touch_lookback"]).sum()
    df["resistance_touches"] = df["touch_resistance"].rolling(window=p["touch_lookback"]).sum()

    # Shifted indicators (no lookahead)
    sup_touches = df["support_touches"].shift(1)
    res_touches = df["resistance_touches"].shift(1)
    touch_sup = df["touch_support"].shift(1)
    touch_res = df["touch_resistance"].shift(1)
    rsi = df["RSI"].shift(1)
    close = df["Close"].shift(1)
    ema = df["EMA_trend"].shift(1)
    vol = df["Volume"].shift(1)
    vol_avg = df["vol_avg"].shift(1)

    # Long: double bottom at support, RSI < 40, uptrend
    long_cond = (
        (sup_touches >= 2)                    # at least 2 touches in lookback
        & (touch_sup == 1)                    # current bar is touching support
        & (rsi < p["rsi_support"])            # RSI confirmation
        & (close > ema)                       # uptrend
        & (vol > p["vol_mult"] * vol_avg)     # volume
    )

    # Short: double top at resistance, RSI > 60, downtrend
    short_cond = (
        (res_touches >= 2)                    # at least 2 touches in lookback
        & (touch_res == 1)                    # current bar is touching resistance
        & (rsi > p["rsi_resistance"])          # RSI confirmation
        & (close < ema)                       # downtrend
        & (vol > p["vol_mult"] * vol_avg)     # volume
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
