"""
Strategy B045: EMA_5_13_ADX_PULLBACK_RSI
Family  : EMA_NEW_VARIANTS
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Base    : S002
Filters : ADX > 25, pullback entry (price retraces to EMA5), RSI > 50 (long) / RSI < 50 (short)
TP/SL   : 4.5x / 1.0x ATR  (ratio: 4.5x)
"""

import pandas as pd
import numpy as np
import ta

DATA_PATH = r"C:\Users\hp\XAUUSD-SCALPER-X10\data\raw\XAUUSD_M1.csv"

PARAMS = {
    "ema_fast": 5,
    "ema_slow": 13,
    "adx_period": 14,
    "adx_threshold": 25,
    "atr_period": 14,
    "rsi_period": 14,
    "pullback_tolerance": 0.001,
    "sl_atr": 1.0,
    "tp_atr": 4.5,
}


def load_data(path: str = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"])
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                             "close": "Close", "tick_volume": "Volume"})
    df = df.sort_values("time").reset_index(drop=True)
    return df


def add_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
    df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    adx_ind = ta.trend.ADXIndicator(df["High"], df["Low"], df["Close"], window=p["adx_period"])
    df["ADX"] = adx_ind.adx()
    df["RSI"] = ta.momentum.RSIIndicator(df["Close"], window=p["rsi_period"]).rsi()
    return df


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = add_indicators(df.copy(), p)

    # EMA is above/below — already in trend
    ema_bull = df["EMA_fast"] > df["EMA_slow"]
    ema_bear = df["EMA_fast"] < df["EMA_slow"]

    # Pullback: price touched or came close to the fast EMA (within tolerance)
    tol = p["pullback_tolerance"]
    pullback_long  = (df["Low"] <= df["EMA_fast"] * (1 + tol)) & (df["Close"] > df["EMA_fast"])
    pullback_short = (df["High"] >= df["EMA_fast"] * (1 - tol)) & (df["Close"] < df["EMA_fast"])

    trend_filter = df["ADX"] > p["adx_threshold"]

    long_conf  = trend_filter & ema_bull & pullback_long  & (df["RSI"] > 50)
    short_conf = trend_filter & ema_bear & pullback_short & (df["RSI"] < 50)

    df["signal"] = 0
    df.loc[long_conf,  "signal"] =  1
    df.loc[short_conf, "signal"] = -1

    df["sl_atr"] = p["sl_atr"]
    df["tp_atr"] = p["tp_atr"]

    return df


if __name__ == "__main__":
    df = load_data()
    result_df = generate_signals(df)
    n_signals = (result_df["signal"] != 0).sum()
    print(f"Strategy B045: EMA_5_13_ADX_PULLBACK_RSI")
    print(f"  Signals   : {n_signals}")
    print(f"  Long      : {(result_df['signal'] == 1).sum()}")
    print(f"  Short     : {(result_df['signal'] == -1).sum()}")
