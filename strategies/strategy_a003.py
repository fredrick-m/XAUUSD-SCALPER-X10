"""
Strategy A003: RSI Divergence + MACD Confirmation
Family  : Divergence
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Detect RSI divergence from price, confirm with MACD histogram,
             filter with EMA(50) trend direction.

Parameters:
  rsi_period: 14
  lookback: 20         Window (bars) for swing-high / swing-low detection
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  ema_trend: 50        Trend filter EMA
  atr_period: 14
  sl_atr: 1.5
  tp_atr: 3.0

Entry  : Bullish divergence — price lower low + RSI higher low + MACD hist > 0
                              + Close > EMA(50)
         Bearish divergence — price higher high + RSI lower high + MACD hist < 0
                              + Close < EMA(50)
Exit   : SL = sl_atr * ATR(14)  |  TP = tp_atr * ATR(14)
"""

import pandas as pd
import numpy as np
import ta

PARAMS = {
    "rsi_period": 14,
    "lookback": 20,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "ema_trend": 50,
    "atr_period": 14,
    "sl_atr": 1.5,
    "tp_atr": 3.0,
}


def _rolling_min_idx(series: pd.Series, window: int) -> pd.Series:
    """Index of the rolling minimum (for swing-low detection)."""
    return series.rolling(window, min_periods=window).apply(
        lambda x: x.argmin(), raw=True
    )


def _rolling_max_idx(series: pd.Series, window: int) -> pd.Series:
    """Index of the rolling maximum (for swing-high detection)."""
    return series.rolling(window, min_periods=window).apply(
        lambda x: x.argmax(), raw=True
    )


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = df.copy()
    lb = p["lookback"]

    # --- ATR ---
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=p["atr_period"]
    )

    # --- RSI ---
    df["rsi"] = ta.momentum.rsi(df["Close"], window=p["rsi_period"])

    # --- MACD histogram ---
    macd_ind = ta.trend.MACD(
        df["Close"],
        window_fast=p["macd_fast"],
        window_slow=p["macd_slow"],
        window_sign=p["macd_signal"],
    )
    df["macd_hist"] = macd_ind.macd_diff()

    # --- EMA trend filter ---
    df["ema_trend"] = ta.trend.ema_indicator(df["Close"], window=p["ema_trend"])

    # --- Divergence detection ---
    # Rolling lows (for bullish divergence)
    price_low = df["Low"].rolling(lb, min_periods=lb).min()
    rsi_at_price_low_window = df["rsi"].rolling(lb, min_periods=lb).min()

    # Current bar's low vs previous window low (price makes lower low)
    prev_price_low = price_low.shift(lb)
    prev_rsi_low = rsi_at_price_low_window.shift(lb)

    bull_div = (price_low < prev_price_low) & (rsi_at_price_low_window > prev_rsi_low)

    # Rolling highs (for bearish divergence)
    price_high = df["High"].rolling(lb, min_periods=lb).max()
    rsi_at_price_high_window = df["rsi"].rolling(lb, min_periods=lb).max()

    prev_price_high = price_high.shift(lb)
    prev_rsi_high = rsi_at_price_high_window.shift(lb)

    bear_div = (price_high > prev_price_high) & (rsi_at_price_high_window < prev_rsi_high)

    # --- Confirmation filters (shifted to avoid look-ahead) ---
    prev_macd_hist = df["macd_hist"].shift(1)
    prev_close = df["Close"].shift(1)
    prev_ema = df["ema_trend"].shift(1)

    # Shift divergence signals by 1 bar as well
    bull_div_prev = bull_div.shift(1).astype(bool).fillna(False)
    bear_div_prev = bear_div.shift(1).astype(bool).fillna(False)

    long_cond = bull_div_prev & (prev_macd_hist > 0) & (prev_close > prev_ema)
    short_cond = bear_div_prev & (prev_macd_hist < 0) & (prev_close < prev_ema)

    df["signal"] = 0
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["signal"] = df["signal"].fillna(0).astype(int)
    return df
