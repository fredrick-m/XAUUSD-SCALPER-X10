"""
XAUUSD-SCALPER-X10 Strategy Generator
Generates 50 scalping strategies for XAUUSD M1 timeframe.
Uses: pandas, numpy, ta (technical analysis library)
"""

import os
import json
from pathlib import Path

STRATEGIES_DIR = Path(__file__).parent
DATA_DIR = Path(__file__).parent.parent / "data" / "raw"

# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------

STRATEGIES = [
    # ── EMA crossover only (1-10) ──────────────────────────────────────────
    {
        "id": "S001", "name": "EMA_3_8_Cross",
        "family": "EMA", "description": "EMA 3/8 fast crossover scalp",
        "params": {"ema_fast": 3, "ema_slow": 8, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5},
        "template": "ema_cross",
    },
    {
        "id": "S002", "name": "EMA_5_13_Cross",
        "family": "EMA", "description": "EMA 5/13 crossover scalp",
        "params": {"ema_fast": 5, "ema_slow": 13, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5},
        "template": "ema_cross",
    },
    {
        "id": "S003", "name": "EMA_8_21_Cross",
        "family": "EMA", "description": "EMA 8/21 crossover scalp",
        "params": {"ema_fast": 8, "ema_slow": 21, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_cross",
    },
    {
        "id": "S004", "name": "EMA_10_20_Cross",
        "family": "EMA", "description": "EMA 10/20 crossover scalp",
        "params": {"ema_fast": 10, "ema_slow": 20, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_cross",
    },
    {
        "id": "S005", "name": "EMA_3_13_Cross",
        "family": "EMA", "description": "EMA 3/13 aggressive scalp",
        "params": {"ema_fast": 3, "ema_slow": 13, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "ema_cross",
    },
    {
        "id": "S006", "name": "EMA_5_21_Cross",
        "family": "EMA", "description": "EMA 5/21 medium scalp",
        "params": {"ema_fast": 5, "ema_slow": 21, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_cross",
    },
    {
        "id": "S007", "name": "EMA_3_21_Cross",
        "family": "EMA", "description": "EMA 3/21 wide-span scalp",
        "params": {"ema_fast": 3, "ema_slow": 21, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.5},
        "template": "ema_cross",
    },
    {
        "id": "S008", "name": "EMA_7_14_Cross",
        "family": "EMA", "description": "EMA 7/14 harmonic scalp",
        "params": {"ema_fast": 7, "ema_slow": 14, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5},
        "template": "ema_cross",
    },
    {
        "id": "S009", "name": "EMA_9_18_Cross",
        "family": "EMA", "description": "EMA 9/18 double-period scalp",
        "params": {"ema_fast": 9, "ema_slow": 18, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_cross",
    },
    {
        "id": "S010", "name": "EMA_4_12_Cross",
        "family": "EMA", "description": "EMA 4/12 triple-factor scalp",
        "params": {"ema_fast": 4, "ema_slow": 12, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5},
        "template": "ema_cross",
    },
    # ── RSI only (11-15) ───────────────────────────────────────────────────
    {
        "id": "S011", "name": "RSI_14_30_70",
        "family": "RSI", "description": "RSI 14 with classic 30/70 levels",
        "params": {"rsi_period": 14, "rsi_ob": 70, "rsi_os": 30, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5},
        "template": "rsi_reversal",
    },
    {
        "id": "S012", "name": "RSI_7_25_75",
        "family": "RSI", "description": "RSI 7 extreme scalp",
        "params": {"rsi_period": 7, "rsi_ob": 75, "rsi_os": 25, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "rsi_reversal",
    },
    {
        "id": "S013", "name": "RSI_21_35_65",
        "family": "RSI", "description": "RSI 21 conservative scalp",
        "params": {"rsi_period": 21, "rsi_ob": 65, "rsi_os": 35, "atr_period": 14, "sl_atr": 2.0, "tp_atr": 3.0},
        "template": "rsi_reversal",
    },
    {
        "id": "S014", "name": "RSI_9_20_80",
        "family": "RSI", "description": "RSI 9 extreme reversal scalp",
        "params": {"rsi_period": 9, "rsi_ob": 80, "rsi_os": 20, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.5},
        "template": "rsi_reversal",
    },
    {
        "id": "S015", "name": "RSI_14_40_60",
        "family": "RSI", "description": "RSI 14 tight mid-band scalp",
        "params": {"rsi_period": 14, "rsi_ob": 60, "rsi_os": 40, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 1.5},
        "template": "rsi_reversal",
    },
    # ── Bollinger Bands only (16-20) ───────────────────────────────────────
    {
        "id": "S016", "name": "BB_20_2_Breakout",
        "family": "BB", "description": "BB(20,2) standard breakout",
        "params": {"bb_period": 20, "bb_std": 2.0, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "bb_breakout",
    },
    {
        "id": "S017", "name": "BB_10_1p5_Breakout",
        "family": "BB", "description": "BB(10,1.5) tight breakout",
        "params": {"bb_period": 10, "bb_std": 1.5, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "bb_breakout",
    },
    {
        "id": "S018", "name": "BB_20_2p5_Breakout",
        "family": "BB", "description": "BB(20,2.5) wide-band breakout",
        "params": {"bb_period": 20, "bb_std": 2.5, "atr_period": 14, "sl_atr": 2.0, "tp_atr": 4.0},
        "template": "bb_breakout",
    },
    {
        "id": "S019", "name": "BB_14_2_Breakout",
        "family": "BB", "description": "BB(14,2) mid-period breakout",
        "params": {"bb_period": 14, "bb_std": 2.0, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "bb_breakout",
    },
    {
        "id": "S020", "name": "BB_20_2_Reversion",
        "family": "BB", "description": "BB(20,2) mean reversion scalp",
        "params": {"bb_period": 20, "bb_std": 2.0, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.0},
        "template": "bb_reversion",
    },
    # ── MACD only (21-25) ──────────────────────────────────────────────────
    {
        "id": "S021", "name": "MACD_12_26_9_Cross",
        "family": "MACD", "description": "MACD(12,26,9) classic line crossover",
        "params": {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "macd_cross",
    },
    {
        "id": "S022", "name": "MACD_5_13_5_Cross",
        "family": "MACD", "description": "MACD(5,13,5) fast scalp crossover",
        "params": {"macd_fast": 5, "macd_slow": 13, "macd_signal": 5, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "macd_cross",
    },
    {
        "id": "S023", "name": "MACD_8_21_5_Cross",
        "family": "MACD", "description": "MACD(8,21,5) medium scalp crossover",
        "params": {"macd_fast": 8, "macd_slow": 21, "macd_signal": 5, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5},
        "template": "macd_cross",
    },
    {
        "id": "S024", "name": "MACD_3_10_5_Cross",
        "family": "MACD", "description": "MACD(3,10,5) ultra-fast scalp",
        "params": {"macd_fast": 3, "macd_slow": 10, "macd_signal": 5, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "macd_cross",
    },
    {
        "id": "S025", "name": "MACD_12_26_9_Histogram",
        "family": "MACD", "description": "MACD(12,26,9) histogram zero-cross",
        "params": {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "macd_histogram",
    },
    # ── ATR-based (26-30) ──────────────────────────────────────────────────
    {
        "id": "S026", "name": "ATR_Breakout_14",
        "family": "ATR", "description": "ATR(14) channel breakout",
        "params": {"atr_period": 14, "atr_mult": 1.0, "lookback": 10, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "atr_breakout",
    },
    {
        "id": "S027", "name": "ATR_Breakout_7",
        "family": "ATR", "description": "ATR(7) fast channel breakout",
        "params": {"atr_period": 7, "atr_mult": 1.0, "lookback": 5, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "atr_breakout",
    },
    {
        "id": "S028", "name": "ATR_Channel_20",
        "family": "ATR", "description": "ATR(20) trend channel scalp",
        "params": {"atr_period": 20, "atr_mult": 1.5, "lookback": 15, "sl_atr": 2.0, "tp_atr": 3.5},
        "template": "atr_breakout",
    },
    {
        "id": "S029", "name": "ATR_Momentum_10",
        "family": "ATR", "description": "ATR(10) momentum squeeze",
        "params": {"atr_period": 10, "atr_mult": 0.75, "lookback": 8, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "atr_breakout",
    },
    {
        "id": "S030", "name": "ATR_MeanReversion_14",
        "family": "ATR", "description": "ATR(14) mean reversion scalp",
        "params": {"atr_period": 14, "atr_mult": 1.5, "lookback": 10, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "atr_reversion",
    },
    # ── EMA + RSI confluence (31-35) ───────────────────────────────────────
    {
        "id": "S031", "name": "EMA_3_8_RSI_14",
        "family": "EMA+RSI", "description": "EMA 3/8 cross + RSI 14 filter",
        "params": {"ema_fast": 3, "ema_slow": 8, "rsi_period": 14, "rsi_ob": 70, "rsi_os": 30, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5},
        "template": "ema_rsi",
    },
    {
        "id": "S032", "name": "EMA_5_13_RSI_7",
        "family": "EMA+RSI", "description": "EMA 5/13 cross + RSI 7 filter",
        "params": {"ema_fast": 5, "ema_slow": 13, "rsi_period": 7, "rsi_ob": 75, "rsi_os": 25, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "ema_rsi",
    },
    {
        "id": "S033", "name": "EMA_8_21_RSI_14",
        "family": "EMA+RSI", "description": "EMA 8/21 cross + RSI 14 filter",
        "params": {"ema_fast": 8, "ema_slow": 21, "rsi_period": 14, "rsi_ob": 65, "rsi_os": 35, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_rsi",
    },
    {
        "id": "S034", "name": "EMA_3_13_RSI_9",
        "family": "EMA+RSI", "description": "EMA 3/13 cross + RSI 9 filter",
        "params": {"ema_fast": 3, "ema_slow": 13, "rsi_period": 9, "rsi_ob": 75, "rsi_os": 25, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "ema_rsi",
    },
    {
        "id": "S035", "name": "EMA_10_20_RSI_21",
        "family": "EMA+RSI", "description": "EMA 10/20 cross + RSI 21 filter",
        "params": {"ema_fast": 10, "ema_slow": 20, "rsi_period": 21, "rsi_ob": 65, "rsi_os": 35, "atr_period": 14, "sl_atr": 2.0, "tp_atr": 3.5},
        "template": "ema_rsi",
    },
    # ── EMA + BB confluence (36-40) ────────────────────────────────────────
    {
        "id": "S036", "name": "EMA_5_21_BB_20_2",
        "family": "EMA+BB", "description": "EMA 5/21 cross + BB(20,2) confirmation",
        "params": {"ema_fast": 5, "ema_slow": 21, "bb_period": 20, "bb_std": 2.0, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_bb",
    },
    {
        "id": "S037", "name": "EMA_8_21_BB_14_2",
        "family": "EMA+BB", "description": "EMA 8/21 cross + BB(14,2) confirmation",
        "params": {"ema_fast": 8, "ema_slow": 21, "bb_period": 14, "bb_std": 2.0, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_bb",
    },
    {
        "id": "S038", "name": "EMA_3_8_BB_20_2p5",
        "family": "EMA+BB", "description": "EMA 3/8 cross + BB(20,2.5) expansion",
        "params": {"ema_fast": 3, "ema_slow": 8, "bb_period": 20, "bb_std": 2.5, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_bb",
    },
    {
        "id": "S039", "name": "EMA_10_20_BB_20_2",
        "family": "EMA+BB", "description": "EMA 10/20 cross + BB(20,2) filter",
        "params": {"ema_fast": 10, "ema_slow": 20, "bb_period": 20, "bb_std": 2.0, "atr_period": 14, "sl_atr": 2.0, "tp_atr": 3.5},
        "template": "ema_bb",
    },
    {
        "id": "S040", "name": "EMA_5_13_BB_10_1p5",
        "family": "EMA+BB", "description": "EMA 5/13 cross + BB(10,1.5) tight filter",
        "params": {"ema_fast": 5, "ema_slow": 13, "bb_period": 10, "bb_std": 1.5, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "ema_bb",
    },
    # ── MACD + RSI confluence (41-45) ─────────────────────────────────────
    {
        "id": "S041", "name": "MACD_12_26_9_RSI_14",
        "family": "MACD+RSI", "description": "MACD(12,26,9) cross + RSI 14 filter",
        "params": {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "rsi_period": 14, "rsi_ob": 70, "rsi_os": 30, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "macd_rsi",
    },
    {
        "id": "S042", "name": "MACD_5_13_5_RSI_7",
        "family": "MACD+RSI", "description": "MACD(5,13,5) cross + RSI 7 filter",
        "params": {"macd_fast": 5, "macd_slow": 13, "macd_signal": 5, "rsi_period": 7, "rsi_ob": 75, "rsi_os": 25, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "macd_rsi",
    },
    {
        "id": "S043", "name": "MACD_8_21_5_RSI_14",
        "family": "MACD+RSI", "description": "MACD(8,21,5) cross + RSI 14 filter",
        "params": {"macd_fast": 8, "macd_slow": 21, "macd_signal": 5, "rsi_period": 14, "rsi_ob": 65, "rsi_os": 35, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5},
        "template": "macd_rsi",
    },
    {
        "id": "S044", "name": "MACD_3_10_5_RSI_9",
        "family": "MACD+RSI", "description": "MACD(3,10,5) cross + RSI 9 filter",
        "params": {"macd_fast": 3, "macd_slow": 10, "macd_signal": 5, "rsi_period": 9, "rsi_ob": 80, "rsi_os": 20, "atr_period": 14, "sl_atr": 1.0, "tp_atr": 2.0},
        "template": "macd_rsi",
    },
    {
        "id": "S045", "name": "MACD_12_26_9_RSI_21",
        "family": "MACD+RSI", "description": "MACD(12,26,9) cross + RSI 21 slow filter",
        "params": {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "rsi_period": 21, "rsi_ob": 65, "rsi_os": 35, "atr_period": 14, "sl_atr": 2.0, "tp_atr": 3.5},
        "template": "macd_rsi",
    },
    # ── Triple confluence (46-50) ──────────────────────────────────────────
    {
        "id": "S046", "name": "EMA_5_13_RSI_14_BB_20_2",
        "family": "EMA+RSI+BB", "description": "EMA 5/13 + RSI 14 + BB(20,2) triple confluence",
        "params": {"ema_fast": 5, "ema_slow": 13, "rsi_period": 14, "rsi_ob": 70, "rsi_os": 30, "bb_period": 20, "bb_std": 2.0, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_rsi_bb",
    },
    {
        "id": "S047", "name": "EMA_8_21_MACD_12_26_9_RSI_14",
        "family": "EMA+MACD+RSI", "description": "EMA 8/21 + MACD(12,26,9) + RSI 14 triple confluence",
        "params": {"ema_fast": 8, "ema_slow": 21, "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "rsi_period": 14, "rsi_ob": 70, "rsi_os": 30, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "ema_macd_rsi",
    },
    {
        "id": "S048", "name": "EMA_3_8_RSI_7_ATR_14",
        "family": "EMA+RSI+ATR", "description": "EMA 3/8 + RSI 7 + ATR(14) triple confluence",
        "params": {"ema_fast": 3, "ema_slow": 8, "rsi_period": 7, "rsi_ob": 75, "rsi_os": 25, "atr_period": 14, "atr_mult": 1.0, "sl_atr": 1.0, "tp_atr": 2.5},
        "template": "ema_rsi_atr",
    },
    {
        "id": "S049", "name": "EMA_10_20_BB_20_2_ATR_14",
        "family": "EMA+BB+ATR", "description": "EMA 10/20 + BB(20,2) + ATR(14) triple confluence",
        "params": {"ema_fast": 10, "ema_slow": 20, "bb_period": 20, "bb_std": 2.0, "atr_period": 14, "atr_mult": 1.0, "sl_atr": 2.0, "tp_atr": 3.5},
        "template": "ema_bb_atr",
    },
    {
        "id": "S050", "name": "MACD_5_13_5_RSI_14_BB_20_2",
        "family": "MACD+RSI+BB", "description": "MACD(5,13,5) + RSI 14 + BB(20,2) triple confluence",
        "params": {"macd_fast": 5, "macd_slow": 13, "macd_signal": 5, "rsi_period": 14, "rsi_ob": 70, "rsi_os": 30, "bb_period": 20, "bb_std": 2.0, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0},
        "template": "macd_rsi_bb",
    },
]

# ---------------------------------------------------------------------------
# Code templates
# ---------------------------------------------------------------------------

HEADER = '''"""
Strategy {id}: {name}
Family  : {family}
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: {description}

Parameters (all configurable via PARAMS dict below):
{param_doc}

Entry  : {entry_summary}
Exit   : SL = sl_atr × ATR({atr_p})  |  TP = tp_atr × ATR({atr_p})
"""

import pandas as pd
import numpy as np
import ta

DATA_PATH = r"C:\\Users\\hp\\XAUUSD-SCALPER-X10\\data\\raw\\XAUUSD_M1.csv"

PARAMS = {params_repr}


def load_data(path: str = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"])
    df = df.rename(columns={{"open": "Open", "high": "High", "low": "Low",
                             "close": "Close", "tick_volume": "Volume"}})
    df = df.sort_values("time").reset_index(drop=True)
    return df


def add_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
'''

FOOTER = '''

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
    print(f"Strategy {id_placeholder}")
    print(f"  Trades    : {{result['total_trades']}}")
    print(f"  Win rate  : {{result['win_rate']:.1%}}")
    print(f"  Return    : {{result['return_pct']:.2f}}%")
    print(f"  Balance   : ${{result['final_balance']:,.2f}}")
'''

# ---------------------------------------------------------------------------
# Per-template indicator + signal bodies
# ---------------------------------------------------------------------------

TEMPLATES = {

"ema_cross": {
    "entry_summary": "Bullish: fast EMA crosses above slow EMA; Bearish: fast crosses below slow",
    "body": '''    p_ema_f = p["ema_fast"]
    p_ema_s = p["ema_slow"]
    p_atr   = p["atr_period"]
    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p_ema_f)
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p_ema_s)
    df["ATR"]      = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p_atr)
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_up   = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    cross_down = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))
    df["signal"] = 0
    df.loc[cross_up,   "signal"] =  1
    df.loc[cross_down, "signal"] = -1
    return df
''',
},

"rsi_reversal": {
    "entry_summary": "Long: RSI crosses above oversold level; Short: RSI crosses below overbought",
    "body": '''    p_rsi = p["rsi_period"]
    p_ob  = p["rsi_ob"]
    p_os  = p["rsi_os"]
    p_atr = p["atr_period"]
    df["RSI"] = ta.momentum.rsi(df["Close"], window=p_rsi)
    df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p_atr)
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    long_entry  = (df["RSI"] > p["rsi_os"]) & (df["RSI"].shift(1) <= p["rsi_os"])
    short_entry = (df["RSI"] < p["rsi_ob"]) & (df["RSI"].shift(1) >= p["rsi_ob"])
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"bb_breakout": {
    "entry_summary": "Long: close breaks above upper BB; Short: close breaks below lower BB",
    "body": '''    p_bb  = p["bb_period"]
    p_std = p["bb_std"]
    p_atr = p["atr_period"]
    bb = ta.volatility.BollingerBands(df["Close"], window=p_bb, window_dev=p_std)
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["ATR"]      = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p_atr)
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    long_entry  = (df["Close"] > df["BB_upper"]) & (df["Close"].shift(1) <= df["BB_upper"].shift(1))
    short_entry = (df["Close"] < df["BB_lower"]) & (df["Close"].shift(1) >= df["BB_lower"].shift(1))
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"bb_reversion": {
    "entry_summary": "Long: close touches/crosses below lower BB then re-enters; Short: touches upper BB then re-enters",
    "body": '''    p_bb  = p["bb_period"]
    p_std = p["bb_std"]
    p_atr = p["atr_period"]
    bb = ta.volatility.BollingerBands(df["Close"], window=p_bb, window_dev=p_std)
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["ATR"]      = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p_atr)
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    long_entry  = (df["Close"] > df["BB_lower"]) & (df["Close"].shift(1) <= df["BB_lower"].shift(1))
    short_entry = (df["Close"] < df["BB_upper"]) & (df["Close"].shift(1) >= df["BB_upper"].shift(1))
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"macd_cross": {
    "entry_summary": "Long: MACD line crosses above signal; Short: MACD line crosses below signal",
    "body": '''    p_mf  = p["macd_fast"]
    p_ms  = p["macd_slow"]
    p_msig = p["macd_signal"]
    p_atr = p["atr_period"]
    macd_obj = ta.trend.MACD(df["Close"], window_slow=p_ms, window_fast=p_mf, window_sign=p_msig)
    df["MACD"]        = macd_obj.macd()
    df["MACD_signal"] = macd_obj.macd_signal()
    df["ATR"]         = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p_atr)
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_up   = (df["MACD"] > df["MACD_signal"]) & (df["MACD"].shift(1) <= df["MACD_signal"].shift(1))
    cross_down = (df["MACD"] < df["MACD_signal"]) & (df["MACD"].shift(1) >= df["MACD_signal"].shift(1))
    df["signal"] = 0
    df.loc[cross_up,   "signal"] =  1
    df.loc[cross_down, "signal"] = -1
    return df
''',
},

"macd_histogram": {
    "entry_summary": "Long: MACD histogram crosses from negative to positive; Short: crosses negative",
    "body": '''    p_mf   = p["macd_fast"]
    p_ms   = p["macd_slow"]
    p_msig = p["macd_signal"]
    p_atr  = p["atr_period"]
    macd_obj = ta.trend.MACD(df["Close"], window_slow=p_ms, window_fast=p_mf, window_sign=p_msig)
    df["MACD_hist"] = macd_obj.macd_diff()
    df["ATR"]       = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p_atr)
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_pos = (df["MACD_hist"] > 0) & (df["MACD_hist"].shift(1) <= 0)
    cross_neg = (df["MACD_hist"] < 0) & (df["MACD_hist"].shift(1) >= 0)
    df["signal"] = 0
    df.loc[cross_pos, "signal"] =  1
    df.loc[cross_neg, "signal"] = -1
    return df
''',
},

"atr_breakout": {
    "entry_summary": "Long: close breaks above recent high + ATR buffer; Short: close breaks below recent low - ATR buffer",
    "body": '''    p_atr  = p["atr_period"]
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
''',
},

"atr_reversion": {
    "entry_summary": "Long: price dips > ATR_mult ATRs below recent high; Short: price rallies > ATR_mult ATRs above recent low",
    "body": '''    p_atr  = p["atr_period"]
    p_mult = p["atr_mult"]
    p_lb   = p["lookback"]
    df["ATR"]        = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p_atr)
    df["recent_high"] = df["High"].rolling(p_lb).max().shift(1)
    df["recent_low"]  = df["Low"].rolling(p_lb).min().shift(1)
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    mult = p["atr_mult"]
    long_entry  = df["Close"] < df["recent_high"] - mult * df["ATR"]
    short_entry = df["Close"] > df["recent_low"]  + mult * df["ATR"]
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"ema_rsi": {
    "entry_summary": "Long: fast EMA crosses above slow AND RSI below overbought; Short: cross down AND RSI above oversold",
    "body": '''    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
    df["RSI"]      = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["ATR"]      = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_up   = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    cross_down = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))
    long_entry  = cross_up   & (df["RSI"] < p["rsi_ob"])
    short_entry = cross_down & (df["RSI"] > p["rsi_os"])
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"ema_bb": {
    "entry_summary": "Long: fast EMA crosses above slow AND close near/above BB upper; Short: cross down AND close near/below BB lower",
    "body": '''    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
    bb = ta.volatility.BollingerBands(df["Close"], window=p["bb_period"], window_dev=p["bb_std"])
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["BB_mid"]   = bb.bollinger_mavg()
    df["ATR"]      = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_up   = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    cross_down = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))
    long_entry  = cross_up   & (df["Close"] > df["BB_mid"])
    short_entry = cross_down & (df["Close"] < df["BB_mid"])
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"macd_rsi": {
    "entry_summary": "Long: MACD crosses above signal AND RSI not overbought; Short: MACD crosses below AND RSI not oversold",
    "body": '''    macd_obj = ta.trend.MACD(df["Close"], window_slow=p["macd_slow"], window_fast=p["macd_fast"], window_sign=p["macd_signal"])
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
''',
},

"ema_rsi_bb": {
    "entry_summary": "Long: EMA cross up + RSI < ob + close > BB mid; Short: EMA cross down + RSI > os + close < BB mid",
    "body": '''    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
    df["RSI"]      = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    bb = ta.volatility.BollingerBands(df["Close"], window=p["bb_period"], window_dev=p["bb_std"])
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["BB_mid"]   = bb.bollinger_mavg()
    df["ATR"]      = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_up   = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    cross_down = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))
    long_entry  = cross_up   & (df["RSI"] < p["rsi_ob"])  & (df["Close"] > df["BB_mid"])
    short_entry = cross_down & (df["RSI"] > p["rsi_os"]) & (df["Close"] < df["BB_mid"])
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"ema_macd_rsi": {
    "entry_summary": "Long: EMA cross up + MACD cross up + RSI < ob; Short: EMA cross down + MACD cross down + RSI > os",
    "body": '''    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
    macd_obj = ta.trend.MACD(df["Close"], window_slow=p["macd_slow"], window_fast=p["macd_fast"], window_sign=p["macd_signal"])
    df["MACD"]        = macd_obj.macd()
    df["MACD_signal"] = macd_obj.macd_signal()
    df["RSI"]         = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["ATR"]         = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    ema_up    = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    ema_down  = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))
    macd_up   = (df["MACD"] > df["MACD_signal"]) & (df["MACD"].shift(1) <= df["MACD_signal"].shift(1))
    macd_down = (df["MACD"] < df["MACD_signal"]) & (df["MACD"].shift(1) >= df["MACD_signal"].shift(1))
    long_entry  = ema_up   & macd_up   & (df["RSI"] < p["rsi_ob"])
    short_entry = ema_down & macd_down & (df["RSI"] > p["rsi_os"])
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"ema_rsi_atr": {
    "entry_summary": "Long: EMA cross up + RSI < ob + ATR confirms volatility; Short: EMA cross down + RSI > os + ATR confirms",
    "body": '''    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
    df["RSI"]      = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    df["ATR"]      = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    df["ATR_avg"]  = df["ATR"].rolling(20).mean()
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_up   = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    cross_down = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))
    atr_active  = df["ATR"] >= p["atr_mult"] * df["ATR_avg"]
    long_entry  = cross_up   & (df["RSI"] < p["rsi_ob"]) & atr_active
    short_entry = cross_down & (df["RSI"] > p["rsi_os"]) & atr_active
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"ema_bb_atr": {
    "entry_summary": "Long: EMA cross up + price above BB mid + ATR active; Short: cross down + price below BB mid + ATR active",
    "body": '''    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=p["ema_fast"])
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=p["ema_slow"])
    bb = ta.volatility.BollingerBands(df["Close"], window=p["bb_period"], window_dev=p["bb_std"])
    df["BB_mid"]  = bb.bollinger_mavg()
    df["ATR"]     = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    df["ATR_avg"] = df["ATR"].rolling(20).mean()
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_up   = (df["EMA_fast"] > df["EMA_slow"]) & (df["EMA_fast"].shift(1) <= df["EMA_slow"].shift(1))
    cross_down = (df["EMA_fast"] < df["EMA_slow"]) & (df["EMA_fast"].shift(1) >= df["EMA_slow"].shift(1))
    atr_active  = df["ATR"] >= p["atr_mult"] * df["ATR_avg"]
    long_entry  = cross_up   & (df["Close"] > df["BB_mid"]) & atr_active
    short_entry = cross_down & (df["Close"] < df["BB_mid"]) & atr_active
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

"macd_rsi_bb": {
    "entry_summary": "Long: MACD cross up + RSI < ob + price above BB mid; Short: MACD cross down + RSI > os + price below BB mid",
    "body": '''    macd_obj = ta.trend.MACD(df["Close"], window_slow=p["macd_slow"], window_fast=p["macd_fast"], window_sign=p["macd_signal"])
    df["MACD"]        = macd_obj.macd()
    df["MACD_signal"] = macd_obj.macd_signal()
    df["RSI"]         = ta.momentum.rsi(df["Close"], window=p["rsi_period"])
    bb = ta.volatility.BollingerBands(df["Close"], window=p["bb_period"], window_dev=p["bb_std"])
    df["BB_mid"]  = bb.bollinger_mavg()
    df["ATR"]     = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=p["atr_period"])
    return df


def _signal_logic(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    cross_up   = (df["MACD"] > df["MACD_signal"]) & (df["MACD"].shift(1) <= df["MACD_signal"].shift(1))
    cross_down = (df["MACD"] < df["MACD_signal"]) & (df["MACD"].shift(1) >= df["MACD_signal"].shift(1))
    long_entry  = cross_up   & (df["RSI"] < p["rsi_ob"]) & (df["Close"] > df["BB_mid"])
    short_entry = cross_down & (df["RSI"] > p["rsi_os"]) & (df["Close"] < df["BB_mid"])
    df["signal"] = 0
    df.loc[long_entry,  "signal"] =  1
    df.loc[short_entry, "signal"] = -1
    return df
''',
},

}

# ---------------------------------------------------------------------------
# File generator
# ---------------------------------------------------------------------------

def _param_doc(params: dict) -> str:
    lines = []
    for k, v in params.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _params_repr(params: dict) -> str:
    lines = ["{"]
    for k, v in params.items():
        lines.append(f'    "{k}": {v},')
    lines.append("}")
    return "\n".join(lines)


def generate_strategy_file(s: dict) -> str:
    tmpl = TEMPLATES[s["template"]]
    atr_p = s["params"].get("atr_period", 14)
    header = HEADER.format(
        id=s["id"],
        name=s["name"],
        family=s["family"],
        description=s["description"],
        param_doc=_param_doc(s["params"]),
        entry_summary=tmpl["entry_summary"],
        atr_p=atr_p,
        params_repr=_params_repr(s["params"]),
    )
    footer = FOOTER.replace("{id_placeholder}", f'"{s["id"]}: {s["name"]}"')
    return header + tmpl["body"] + footer


def write_all_strategies(output_dir: Path = STRATEGIES_DIR) -> list:
    index = []
    for s in STRATEGIES:
        code = generate_strategy_file(s)
        fname = f"strategy_{s['id'].lower()}.py"
        fpath = output_dir / fname
        fpath.write_text(code, encoding="utf-8")
        index.append({
            "id": s["id"],
            "name": s["name"],
            "file": fname,
            "family": s["family"],
            "description": s["description"],
            "template": s["template"],
            "params": s["params"],
        })
        print(f"  wrote {fname}")
    return index


def write_index(index: list, output_dir: Path = STRATEGIES_DIR) -> None:
    idx_path = output_dir / "index.json"
    idx_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"\nindex.json written with {len(index)} strategies.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Generating {len(STRATEGIES)} strategies -> {STRATEGIES_DIR}\n")
    index = write_all_strategies()
    write_index(index)
    print("\nDone.")
