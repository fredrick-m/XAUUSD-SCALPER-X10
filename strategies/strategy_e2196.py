"""
Strategy S026: ATR_Breakout_14
Family  : ATR
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: ATR(14) channel breakout

Parameters (all configurable via PARAMS dict below):
  atr_period: 14
  atr_mult: 1.0
  lookback: 10
  sl_atr: 1.5
  tp_atr: 3.0

Entry  : Long: close breaks above recent high + ATR buffer; Short: close breaks below recent low - ATR buffer
Exit   : SL = sl_atr × ATR(14)  |  TP = tp_atr × ATR(14)
"""

import pandas as pd
import numpy as np
import ta

DATA_PATH = r"C:\Users\hp\XAUUSD-SCALPER-X10\data\raw\XAUUSD_M1.csv"

PARAMS = {
    "rsi_period": 24,
    "atr_mult": 1.0,
    "rsi_ob": 74,
    "atr_period": 14,
    "tp_atr": 3.07258,
    "lookback": 10,
    "rsi_os": 35,
    "sl_atr": 2.0
}


def load_data(path: str = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"])
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                             "close": "Close", "tick_volume": "Volume"})
    df = df.sort_values("time").reset_index(drop=True)
    return df


def add_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    p_atr  = p["atr_period"]
    p_mult = p["atr_mult"]
    p_lb   = p["lookback"]
    df["ATR"]        = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p_atr)
    df["recent_high"] = df["High"].rolling(p_lb).max().shift(1)
    df["recent_low"]  = df["Low"].rolling(p_lb).min().shift(1)
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    mult = p["atr_mult"]
    long_entry  = df["Close"] > df["recent_high"] + mult * df["ATR"]
    short_entry = df["Close"] < df["recent_low"]  - mult * df["ATR"]
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
    print("Strategy S026: ATR_Breakout_14")
    print(f"  Trades    : {{result['total_trades']}}")
    print(f"  Win rate  : {{result['win_rate']:.1%}}")
    print(f"  Return    : {{result['return_pct']:.2f}}%")
    print(f"  Balance   : ${{result['final_balance']:,.2f}}")
