"""Explore new entry triggers within EMA-stack framework."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np
import glob
import os
import ta

# Load M5 data
files = glob.glob("data/raw/XAUUSD_M1*.csv")
largest = max(files, key=lambda f: os.path.getsize(f))
df1 = pd.read_csv(largest, parse_dates=["time"])
df1.set_index("time", inplace=True)
df5 = df1.resample("5min").agg(
    {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
).dropna()
df5.reset_index(inplace=True)
print(f"M5 bars: {len(df5)}")

from engine.backtest import run_simulation

# Build common indicators
df = df5.copy()
df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=14)
df["EMA_f"] = ta.trend.ema_indicator(df["Close"], window=8)
df["EMA_m"] = ta.trend.ema_indicator(df["Close"], window=21)
df["EMA_s"] = ta.trend.ema_indicator(df["Close"], window=50)
df["RSI"] = ta.momentum.rsi(df["Close"], window=14)

# EMA stacking
df["bull_stack"] = ((df["EMA_f"] > df["EMA_m"]) & (df["EMA_m"] > df["EMA_s"])).astype(int)
df["bear_stack"] = ((df["EMA_f"] < df["EMA_m"]) & (df["EMA_m"] < df["EMA_s"])).astype(int)
df["bull_break"] = (df["bull_stack"] != df["bull_stack"].shift(1)).astype(int)
df["bull_group"] = df["bull_break"].cumsum()
df["bull_c"] = df.groupby("bull_group").cumcount() + 1
df.loc[df["bull_stack"] == 0, "bull_c"] = 0
df["bear_break"] = (df["bear_stack"] != df["bear_stack"].shift(1)).astype(int)
df["bear_group"] = df["bear_break"].cumsum()
df["bear_c"] = df.groupby("bear_group").cumcount() + 1
df.loc[df["bear_stack"] == 0, "bear_c"] = 0

# Volume stats
df["vol_avg"] = df["Volume"].rolling(50).mean()
df["vol_ratio"] = df["Volume"] / df["vol_avg"]

# ATR avg for expansion
df["ATR_avg"] = df["ATR"].rolling(50).mean()

# Shifted (no lookahead)
bull_c = df["bull_c"].shift(1)
bear_c = df["bear_c"].shift(1)
rsi = df["RSI"].shift(1)
atr = df["ATR"].shift(1)
close = df["Close"].shift(1)
ema_m = df["EMA_m"].shift(1)
vol_ratio = df["vol_ratio"].shift(1)
atr_avg = df["ATR_avg"].shift(1)
dist = (close - ema_m).abs()


def apply_cooldown(raw_signal, cooldown):
    raw = raw_signal.copy()
    last_idx = -cooldown - 1
    for i in range(len(raw)):
        if raw.iloc[i] != 0:
            if i - last_idx > cooldown:
                last_idx = i
            else:
                raw.iloc[i] = 0
    return raw


def test_signal(label, long_cond, short_cond, cd=100, sl_tp_pairs=None):
    if sl_tp_pairs is None:
        sl_tp_pairs = [(1.5, 3.0), (1.5, 2.5), (2.0, 3.0)]

    raw = pd.Series(0, index=df.index)
    raw[long_cond] = 1
    raw[short_cond] = -1
    raw = apply_cooldown(raw, cd)

    sig_count = (raw != 0).sum()
    if sig_count < 20 or sig_count > 500:
        return

    for sl_, tp_ in sl_tp_pairs:
        use_t = tp_ < 3.0
        sl_p = np.where(raw == 1, df["Close"] - sl_ * atr,
                       np.where(raw == -1, df["Close"] + sl_ * atr, 0))
        tp_p = np.where(raw == 1, df["Close"] + tp_ * atr,
                       np.where(raw == -1, df["Close"] - tp_ * atr, 0))

        stats = run_simulation(
            df=df, signals=raw,
            sl_prices=pd.Series(sl_p, index=df.index),
            tp_prices=pd.Series(tp_p, index=df.index),
            directions=raw, risk_pct=0.04,
            trailing_stop=use_t, max_bars_in_trade=200,
            session_filter=True, session_hours=(7, 20),
        )

        if stats["profit_factor"] > 1.0 and stats["total_trades"] >= 20:
            print(
                f"{label} sl={sl_} tp={tp_}: "
                f"sigs={sig_count} trades={stats['total_trades']} "
                f"WR={stats['win_rate']:.1%} PF={stats['profit_factor']:.2f} "
                f"bal=${stats['final_balance']:.0f}"
            )


print("\n=== VOLUME SPIKE TRIGGER ===")
for sb in [15, 20]:
    for vol_mult in [1.5, 2.0, 2.5]:
        for cd in [80, 100]:
            long = (bull_c >= sb) & (vol_ratio > vol_mult) & (close > ema_m)
            short = (bear_c >= sb) & (vol_ratio > vol_mult) & (close < ema_m)
            test_signal(f"VOL sb={sb} vm={vol_mult} cd={cd}", long, short, cd)


print("\n=== ENGULFING CANDLE TRIGGER ===")
prev_bear = df["Close"].shift(2) < df["Open"].shift(2)
curr_bull = df["Close"].shift(1) > df["Open"].shift(1)
engulf_bull = prev_bear & curr_bull & (df["Close"].shift(1) - df["Open"].shift(1) > df["Open"].shift(2) - df["Close"].shift(2))

prev_bull = df["Close"].shift(2) > df["Open"].shift(2)
curr_bear = df["Close"].shift(1) < df["Open"].shift(1)
engulf_bear = prev_bull & curr_bear & (df["Open"].shift(1) - df["Close"].shift(1) > df["Close"].shift(2) - df["Open"].shift(2))

for sb in [15, 20]:
    for cd in [80, 100]:
        long = (bull_c >= sb) & engulf_bull
        short = (bear_c >= sb) & engulf_bear
        test_signal(f"ENGULF sb={sb} cd={cd}", long, short, cd)


print("\n=== I003 + VOLUME CONFIRMATION ===")
rsi_pull_bull = (rsi < 40) & (rsi > 25)
rsi_pull_bear = (rsi > 60) & (rsi < 75)
atr_exp = atr > 1.5 * atr_avg
pullback = dist <= 0.5 * atr
atr_trig_bull = atr_exp & pullback & (close > ema_m)
atr_trig_bear = atr_exp & pullback & (close < ema_m)

for vol_min in [1.0, 1.2, 1.5, 2.0]:
    vol_ok = vol_ratio >= vol_min
    long = (bull_c >= 20) & (rsi_pull_bull | atr_trig_bull) & vol_ok
    short = (bear_c >= 20) & (rsi_pull_bear | atr_trig_bear) & vol_ok
    test_signal(f"I003+VOL vm={vol_min}", long, short, cd=100, sl_tp_pairs=[(1.5, 3.0)])


print("\n=== PINBAR TRIGGER ===")
# Pinbar: small body relative to range, long lower wick (bullish) or upper wick (bearish)
body = (df["Close"].shift(1) - df["Open"].shift(1)).abs()
range_ = (df["High"].shift(1) - df["Low"].shift(1)).replace(0, np.nan)
lower_wick = pd.Series(np.minimum(df["Close"].shift(1), df["Open"].shift(1)) - df["Low"].shift(1), index=df.index)
upper_wick = pd.Series(df["High"].shift(1) - np.maximum(df["Close"].shift(1), df["Open"].shift(1)), index=df.index)

pin_bull = (body < 0.3 * range_) & (lower_wick > 0.6 * range_)
pin_bear = (body < 0.3 * range_) & (upper_wick > 0.6 * range_)

for sb in [15, 20]:
    for cd in [80, 100]:
        long = (bull_c >= sb) & pin_bull
        short = (bear_c >= sb) & pin_bear
        test_signal(f"PINBAR sb={sb} cd={cd}", long, short, cd)


print("\nDone.")
