"""
Strategy B024: EMA_9_18_ADX30_RSI_RANGE_VOL
Family  : EMA_9_18
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Base    : S009
Filters : ADX > 30, RSI 45-65 range (long) / RSI 35-55 (short), Volume > vol_ma
TP/SL   : 3.0x / 0.7x ATR  (ratio: 4.28x)
"""

import pandas as pd
import numpy as np
import ta

DATA_PATH = r"C:\Users\hp\XAUUSD-SCALPER-X10\data\raw\XAUUSD_M1.csv"

PARAMS = {
    "ema_fast": 9,
    "ema_slow": 18,
    "adx_period": 14,
    "adx_threshold": 30,
    "atr_period": 14,
    "rsi_period": 14,
    "rsi_long_lo": 45,
    "rsi_long_hi": 65,
    "rsi_short_lo": 35,
    "rsi_short_hi": 55,
    "vol_ma_period": 20,
    "sl_atr": 0.7,
    "tp_atr": 3.0,
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
    df["vol_ma"] = df["Volume"].rolling(p["vol_ma_period"]).mean()
    return df


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = add_indicators(df.copy(), p)

    cross_up   = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    cross_down = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))

    trend_filter    = df["ADX"] > p["adx_threshold"]
    vol_filter      = df["Volume"] > df["vol_ma"]
    rsi_long_range  = (df["RSI"] >= p["rsi_long_lo"])  & (df["RSI"] <= p["rsi_long_hi"])
    rsi_short_range = (df["RSI"] >= p["rsi_short_lo"]) & (df["RSI"] <= p["rsi_short_hi"])

    long_conf  = trend_filter & rsi_long_range  & vol_filter
    short_conf = trend_filter & rsi_short_range & vol_filter

    df["signal"] = 0
    df.loc[cross_up   & long_conf,  "signal"] =  1
    df.loc[cross_down & short_conf, "signal"] = -1

    df["sl_atr"] = p["sl_atr"]
    df["tp_atr"] = p["tp_atr"]

    return df


if __name__ == "__main__":
    df = load_data()
    result_df = generate_signals(df)
    n_signals = (result_df["signal"] != 0).sum()
    print(f"Strategy B024: EMA_9_18_ADX30_RSI_RANGE_VOL")
    print(f"  Signals   : {n_signals}")
    print(f"  Long      : {(result_df['signal'] == 1).sum()}")
    print(f"  Short     : {(result_df['signal'] == -1).sum()}")
