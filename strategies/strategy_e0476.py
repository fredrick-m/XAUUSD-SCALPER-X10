"""
Strategy S045: MACD_12_26_9_RSI_21
Family  : MACD+RSI
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: MACD(12,26,9) cross + RSI 21 slow filter

Parameters (all configurable via PARAMS dict below):
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  rsi_period: 21
  rsi_ob: 65
  rsi_os: 35
  atr_period: 14
  sl_atr: 2.0
  tp_atr: 3.5

Entry  : Long: MACD crosses above signal AND RSI not overbought; Short: MACD crosses below AND RSI not oversold
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

DATA_PATH = r"C:\Users\hp\XAUUSD-SCALPER-X10\data\raw\XAUUSD_M1.csv"

PARAMS = {
    "macd_fast": 12,
    "macd_slow": 29,
    "macd_signal": 8,
    "rsi_period": 23,
    "rsi_ob": 68,
    "rsi_os": 41,
    "atr_period": 15,
    "sl_atr": 2.0,
    "tp_atr": 3.240256
}


def load_data(path: str = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"])
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                             "close": "Close", "tick_volume": "Volume"})
    df = df.sort_values("time").reset_index(drop=True)
    return df


def add_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    macd_obj = ta.trend.MACD(df["Close"], window_slow=p["macd_slow"], window_fast=p["macd_fast"], window_sign=p["macd_signal"])
    df["MACD"]        = macd_obj.macd()
    df["MACD_signal"] = macd_obj.macd_signal()
    df["RSI"]         = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["ATR"]         = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_up   = (df["MACD"] > df["MACD_signal"]) & (df["MACD"].shift(1) <= df["MACD_signal"].shift(1))
    cross_down = (df["MACD"] < df["MACD_signal"]) & (df["MACD"].shift(1) >= df["MACD_signal"].shift(1))
    long_entry  = cross_up   & (df["RSI"] < p["rsi_ob"])
    short_entry = cross_down & (df["RSI"] > p["rsi_os"])
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Return df with 'signal' column: 1=long, -1=short, 0=flat."""
    df = add_indicators(df.copy(), p)
    df = _signal_logic(df, p)
    return df


def backtest(df: pd.DataFrame, p: dict = PARAMS,
             initial_balance: float = 10_000.0,
             lot_size: float = 0.1) -> dict:
    """
    Vectorised backtest.
    Returns performance dict with equity, trades, win_rate, return_pct.
    """
    df = generate_signals(df, p)
    atr_col = "ATR"

    balance = initial_balance
    equity_curve = []
    trades = []
    in_trade = False
    entry_price = sl = tp = direction = 0.0

    for i, row in df.iterrows():
        if in_trade:
            if direction == 1:
                if row["Low"] <= sl:
                    pnl = (sl - entry_price) * lot_size * 100
                    balance += pnl
                    trades.append(pnl)
                    in_trade = False
                elif row["High"] >= tp:
                    pnl = (tp - entry_price) * lot_size * 100
                    balance += pnl
                    trades.append(pnl)
                    in_trade = False
            elif direction == -1:
                if row["High"] >= sl:
                    pnl = (entry_price - sl) * lot_size * 100
                    balance += pnl
                    trades.append(pnl)
                    in_trade = False
                elif row["Low"] <= tp:
                    pnl = (entry_price - tp) * lot_size * 100
                    balance += pnl
                    trades.append(pnl)
                    in_trade = False

        if not in_trade and not np.isnan(row.get(atr_col, np.nan)):
            atr = row[atr_col]
            if row["signal"] == 1:
                entry_price = row["Close"]
                sl = entry_price - p["sl_atr"] * atr
                tp = entry_price + p["tp_atr"] * atr
                direction = 1
                in_trade = True
            elif row["signal"] == -1:
                entry_price = row["Close"]
                sl = entry_price + p["sl_atr"] * atr
                tp = entry_price - p["tp_atr"] * atr
                direction = -1
                in_trade = True

        equity_curve.append(balance)

    n = len(trades)
    wins = sum(1 for t in trades if t > 0)
    win_rate = wins / n if n else 0.0
    total_return = (balance - initial_balance) / initial_balance * 100

    return {
        "total_trades": n,
        "win_rate": round(win_rate, 4),
        "final_balance": round(balance, 2),
        "return_pct": round(total_return, 2),
        "equity_curve": equity_curve,
    }


if __name__ == "__main__":
    df = load_data()
    result = backtest(df)
    print("Strategy S045: MACD_12_26_9_RSI_21")
    print(f"  Trades    : {{result['total_trades']}}")
    print(f"  Win rate  : {{result['win_rate']:.1%}}")
    print(f"  Return    : {{result['return_pct']:.2f}}%")
    print(f"  Balance   : ${{result['final_balance']:,.2f}}")
