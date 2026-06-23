"""
Strategy B031: EMA_9_18_ADX_VOL_BULLBAR
Family  : EMA_9_18
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Base    : S009
Filters : ADX > 25, Volume > vol_ma, bullish bar (close > open) / bearish bar (close < open)
TP/SL   : 4.0x / 0.8x ATR  (ratio: 5.0x)
"""

import pandas as pd
import numpy as np
import ta

DATA_PATH = r"C:\Users\hp\XAUUSD-SCALPER-X10\data\raw\XAUUSD_M1.csv"

PARAMS = {
    "ema_fast": 9,
    "ema_slow": 18,
    "adx_period": 14,
    "adx_threshold": 25,
    "atr_period": 14,
    "vol_ma_period": 20,
    "sl_atr": 0.8,
    "tp_atr": 4.0,
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
    df["vol_ma"] = df["Volume"].rolling(p["vol_ma_period"]).mean()
    return df


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = add_indicators(df.copy(), p)

    cross_up   = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    cross_down = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))

    trend_filter = df["ADX"] > p["adx_threshold"]
    vol_filter   = df["Volume"] > df["vol_ma"]
    bull_bar     = df["Close"] > df["Open"]
    bear_bar     = df["Close"] < df["Open"]

    long_conf  = trend_filter & vol_filter & bull_bar
    short_conf = trend_filter & vol_filter & bear_bar

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
    print(f"Strategy B031: EMA_9_18_ADX_VOL_BULLBAR")
    print(f"  Signals   : {n_signals}")
    print(f"  Long      : {(result_df['signal'] == 1).sum()}")
    print(f"  Short     : {(result_df['signal'] == -1).sum()}")
