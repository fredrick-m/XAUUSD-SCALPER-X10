"""
Strategy B025: EMA_9_18_ADX_STOCH_EMA200SLOPE
Family  : EMA_9_18
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Base    : S009
Filters : ADX > 25, Stochastic not overbought/oversold, EMA200 slope positive (long) / negative (short)
TP/SL   : 4.5x / 1.0x ATR  (ratio: 4.5x)
"""

import pandas as pd
import numpy as np
import ta

DATA_PATH = r"C:\Users\hp\XAUUSD-SCALPER-X10\data\raw\XAUUSD_M1.csv"

PARAMS = {
    "ema_fast": 9,
    "ema_slow": 18,
    "ema_trend": 200,
    "adx_period": 14,
    "adx_threshold": 25,
    "atr_period": 14,
    "stoch_overbought": 80,
    "stoch_oversold": 20,
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
    df["EMA200"]   = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])
    df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    adx_ind = ta.trend.ADXIndicator(df["High"], df["Low"], df["Close"], window=p["adx_period"])
    df["ADX"] = adx_ind.adx()
    stoch = ta.momentum.StochasticOscillator(df["High"], df["Low"], df["Close"])
    df["STOCH_K"] = stoch.stoch()
    return df


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    df = add_indicators(df.copy(), p)

    cross_up   = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    cross_down = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))

    trend_filter      = df["ADX"] > p["adx_threshold"]
    ema200_slope_up   = df["EMA200"] > df["EMA200"].shift(3)
    ema200_slope_down = df["EMA200"] < df["EMA200"].shift(3)
    stoch_not_ob      = df["STOCH_K"] < p["stoch_overbought"]
    stoch_not_os      = df["STOCH_K"] > p["stoch_oversold"]

    long_conf  = trend_filter & stoch_not_ob & ema200_slope_up
    short_conf = trend_filter & stoch_not_os & ema200_slope_down

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
    print(f"Strategy B025: EMA_9_18_ADX_STOCH_EMA200SLOPE")
    print(f"  Signals   : {n_signals}")
    print(f"  Long      : {(result_df['signal'] == 1).sum()}")
    print(f"  Short     : {(result_df['signal'] == -1).sum()}")
