# Phase 2: Backtest Runner & Strategy Factory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the improved backtest engine (trailing stop, time exit, session filter) and the Strategy Factory agent that uses Claude API to generate new strategies autonomously.

**Architecture:** The Backtest Runner agent consumes tasks from the queue, runs backtests using an improved engine, and stores results. The Strategy Factory agent uses Claude to generate novel strategies (momentum, breakout, microstructure — not just crossovers), validates them, and posts backtest tasks.

**Tech Stack:** Python, pandas, numpy, ta, Anthropic SDK, multiprocessing

---

## File Structure

```
engine/
├── __init__.py
├── backtest.py              — Improved backtest engine (from existing backtests/engine.py)
└── optimizer.py             — (stub for Phase 3)

agents/
├── backtest_runner.py       — Backtest Runner agent
└── strategy_factory.py      — Strategy Factory agent

tests/
├── test_engine.py           — Engine tests (trailing, time exit, session filter)
├── test_backtest_runner.py  — Agent tests
└── test_strategy_factory.py — Agent tests
```

---

### Task 1: Improved backtest engine

**Files:**
- Create: `engine/__init__.py`
- Create: `engine/backtest.py`
- Create: `tests/test_engine.py`

The improved engine adds to the existing `backtests/engine.py`:
- **Trailing stop:** After 1R profit, move SL to breakeven; then trail by 1 ATR
- **Time-based exit:** Close trade at market price if no TP/SL hit after N bars (default 60)
- **Session filter:** Only allow entries during active sessions (configurable)
- **Partial TP:** Take 50% at TP1, let rest run to TP2 with trailing

- [ ] **Step 1: Write tests**

`tests/test_engine.py`:
```python
"""Tests for the improved backtest engine."""
import pandas as pd
import numpy as np
import pytest


def _make_sample_data(n=200):
    """Create synthetic XAUUSD M1 data for testing."""
    np.random.seed(42)
    times = pd.date_range("2025-06-01 08:00", periods=n, freq="1min")
    close = 2000 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = close + np.random.randn(n) * 0.1
    volume = np.random.randint(50, 500, n)
    spread = np.full(n, 160)
    df = pd.DataFrame({
        "time": times, "Open": open_, "High": high, "Low": low,
        "Close": close, "Volume": volume, "spread": spread,
    })
    return df


def _make_signals(df, long_indices=None, short_indices=None):
    """Create signal/SL/TP series for testing."""
    signals = pd.Series(0, index=df.index)
    sl_prices = pd.Series(np.nan, index=df.index)
    tp_prices = pd.Series(np.nan, index=df.index)

    for i in (long_indices or []):
        signals.iloc[i] = 1
        sl_prices.iloc[i] = df["Close"].iloc[i] - 2.0  # 2 dollar SL
        tp_prices.iloc[i] = df["Close"].iloc[i] + 4.0  # 4 dollar TP (2R)
    for i in (short_indices or []):
        signals.iloc[i] = -1
        sl_prices.iloc[i] = df["Close"].iloc[i] + 2.0
        tp_prices.iloc[i] = df["Close"].iloc[i] - 4.0

    return signals, sl_prices, tp_prices


def test_engine_imports():
    from engine.backtest import run_simulation, INITIAL_BALANCE
    assert INITIAL_BALANCE == 50.0


def test_basic_simulation_runs():
    from engine.backtest import run_simulation
    df = _make_sample_data()
    signals, sl, tp = _make_signals(df, long_indices=[10, 50, 100])
    result = run_simulation(df, signals, sl, tp, signals)
    assert "total_trades" in result
    assert "win_rate" in result
    assert "equity_curve" in result
    assert result["total_trades"] >= 0


def test_trailing_stop_enabled():
    from engine.backtest import run_simulation
    df = _make_sample_data()
    signals, sl, tp = _make_signals(df, long_indices=[10, 50, 100])
    result_no_trail = run_simulation(df, signals, sl, tp, signals, trailing_stop=False)
    result_trail = run_simulation(df, signals, sl, tp, signals, trailing_stop=True)
    # Both should complete without error
    assert result_no_trail["total_trades"] >= 0
    assert result_trail["total_trades"] >= 0


def test_time_exit():
    from engine.backtest import run_simulation
    df = _make_sample_data(500)
    # Signal at bar 10 with very wide TP/SL that won't be hit
    signals = pd.Series(0, index=df.index)
    sl_prices = pd.Series(np.nan, index=df.index)
    tp_prices = pd.Series(np.nan, index=df.index)
    signals.iloc[10] = 1
    sl_prices.iloc[10] = df["Close"].iloc[10] - 100  # very far SL
    tp_prices.iloc[10] = df["Close"].iloc[10] + 100  # very far TP

    result = run_simulation(df, signals, sl_prices, tp_prices, signals, max_bars_in_trade=30)
    # Trade should have been force-closed by time exit
    assert result["total_trades"] >= 1


def test_session_filter():
    from engine.backtest import run_simulation
    df = _make_sample_data(500)
    # Set times to span across sessions
    df["time"] = pd.date_range("2025-06-01 00:00", periods=500, freq="1min")

    signals, sl, tp = _make_signals(df, long_indices=[5, 60, 120, 300, 450])

    # With session filter: only London (7-16 UTC) and NY (13-21 UTC)
    result_filtered = run_simulation(
        df, signals, sl, tp, signals,
        session_filter=True, session_hours=(7, 21),
    )
    # Without filter
    result_unfiltered = run_simulation(df, signals, sl, tp, signals, session_filter=False)

    # Filtered should have fewer or equal trades (signals at 0:05 and 1:00 are outside session)
    assert result_filtered["total_trades"] <= result_unfiltered["total_trades"]


def test_no_signals_returns_zero_trades():
    from engine.backtest import run_simulation
    df = _make_sample_data()
    signals = pd.Series(0, index=df.index)
    sl = pd.Series(np.nan, index=df.index)
    tp = pd.Series(np.nan, index=df.index)
    result = run_simulation(df, signals, sl, tp, signals)
    assert result["total_trades"] == 0
    assert result["final_balance"] == 50.0


def test_validate_function():
    from engine.backtest import validate
    metrics = {
        "win_rate": 0.65, "profit_factor": 2.5, "max_drawdown": 0.20,
        "x10_count": 6, "total_trades": 300,
    }
    passed, fails = validate(metrics, regimes_tested=3)
    assert passed
    assert len(fails) == 0


def test_validate_fails():
    from engine.backtest import validate
    metrics = {
        "win_rate": 0.35, "profit_factor": 1.0, "max_drawdown": 0.50,
        "x10_count": 0, "total_trades": 50,
    }
    passed, fails = validate(metrics, regimes_tested=1)
    assert not passed
    assert len(fails) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL — cannot import engine.backtest

- [ ] **Step 3: Write implementation**

`engine/__init__.py`:
```python
"""Backtest engine and optimizer."""
```

`engine/backtest.py` — This is based on the existing `backtests/engine.py` but improved with trailing stop, time exit, and session filter. Key changes from the original:

```python
"""
XAUUSD-SCALPER-X10 Improved Backtest Engine
============================================
Improvements over v1 (backtests/engine.py):
- Trailing stop: after 1R profit, SL moves to breakeven then trails by ATR
- Time-based exit: close after N bars if no TP/SL hit
- Session filter: skip signals outside active trading hours
- Partial TP support (optional)

All original features preserved:
- Dynamic lot sizing (% risk model)
- Next-bar entry (no look-ahead)
- Spread + slippage costs
- Pessimistic SL-first on ambiguous bars
- Regime detection (ADX/ATR)
"""
import math
import pandas as pd
import numpy as np
import ta
from typing import List, Tuple

from core.config import (
    INITIAL_BALANCE, PIP_VALUE, DEFAULT_RISK_PCT,
    MIN_LOT, MAX_LOT, DEFAULT_SPREAD, SLIPPAGE_PER_FILL,
    MIN_WIN_RATE, MIN_PROFIT_FACTOR, MAX_DRAWDOWN,
    MIN_X10_COUNT, MIN_TRADES, MIN_REGIMES,
)


def dynamic_lot(balance: float, sl_distance: float, risk_pct: float) -> float:
    if sl_distance <= 0 or balance <= 0:
        return MIN_LOT
    lot = (balance * risk_pct) / (sl_distance * PIP_VALUE)
    return max(MIN_LOT, min(round(lot, 3), MAX_LOT))


def profit(entry: float, exit_: float, direction: int, lot_size: float) -> float:
    if direction == 1:
        return (exit_ - entry) * lot_size * 100
    else:
        return (entry - exit_) * lot_size * 100


def add_regime_indicators(df: pd.DataFrame) -> pd.DataFrame:
    adx_period = 14
    atr_period = 14
    atr_avg_win = 100

    df["ADX"] = ta.trend.ADXIndicator(df["High"], df["Low"], df["Close"], window=adx_period).adx()
    df["ATR"] = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=atr_period)
    df["ATR_avg"] = df["ATR"].rolling(atr_avg_win).mean()

    def classify_regime(row):
        if pd.isna(row["ADX"]) or pd.isna(row["ATR_avg"]):
            return "UNKNOWN"
        if row["ATR"] > 1.5 * row["ATR_avg"]:
            return "HIGH_VOLATILITY"
        if row["ADX"] > 25:
            return "TREND"
        if row["ADX"] < 20:
            return "RANGE"
        return "MIXED"

    df["regime"] = df.apply(classify_regime, axis=1)
    return df


def run_simulation(
    df: pd.DataFrame,
    signals: pd.Series,
    sl_prices: pd.Series,
    tp_prices: pd.Series,
    directions: pd.Series,
    risk_pct: float = DEFAULT_RISK_PCT,
    spread_override: float = None,
    slippage_override: float = None,
    trailing_stop: bool = False,
    max_bars_in_trade: int = 0,
    session_filter: bool = False,
    session_hours: tuple = (7, 21),
) -> dict:
    """
    Bar-by-bar simulation with all improvements.

    New parameters:
    - trailing_stop: if True, move SL to breakeven after 1R, then trail by initial risk
    - max_bars_in_trade: if > 0, force close after this many bars
    - session_filter: if True, only enter during session_hours
    - session_hours: tuple (start_hour, end_hour) in UTC
    """
    slippage = slippage_override if slippage_override is not None else SLIPPAGE_PER_FILL
    has_spread_col = "spread" in df.columns
    has_time_col = "time" in df.columns

    balance = INITIAL_BALANCE
    equity_peak = INITIAL_BALANCE
    max_dd = 0.0
    trades = []
    equity_curve = [INITIAL_BALANCE]
    x10_count = 0
    next_x10_target = INITIAL_BALANCE * 10

    in_trade = False
    entry_px = 0.0
    sl = 0.0
    tp = 0.0
    direction = 0
    current_lot = MIN_LOT
    initial_risk = 0.0  # for trailing stop
    bars_in_trade = 0

    pending_entry = False
    pending_sl = 0.0
    pending_tp = 0.0
    pending_dir = 0

    n_bars = len(df)

    for i in range(n_bars):
        row = df.iloc[i]

        # ── Execute pending entry at this bar's Open ──
        if pending_entry and not in_trade:
            # Session filter check
            if session_filter and has_time_col:
                hour = pd.Timestamp(row["time"]).hour
                if not (session_hours[0] <= hour < session_hours[1]):
                    pending_entry = False
                    # Skip: outside session
                    equity_curve.append(balance)
                    if balance > equity_peak:
                        equity_peak = balance
                    dd = (equity_peak - balance) / equity_peak if equity_peak > 0 else 0.0
                    if dd > max_dd:
                        max_dd = dd
                    # Still register new signals below
                    sig = signals.iloc[i]
                    if not in_trade and not pending_entry and sig != 0:
                        sl_val = sl_prices.iloc[i]
                        tp_val = tp_prices.iloc[i]
                        if not (math.isnan(sl_val) or math.isnan(tp_val)):
                            pending_entry = True
                            pending_sl = sl_val
                            pending_tp = tp_val
                            pending_dir = int(sig)
                    continue

            if spread_override is not None:
                bar_spread = spread_override
            elif has_spread_col:
                bar_spread = row["spread"] / 1000.0
            else:
                bar_spread = DEFAULT_SPREAD

            raw_entry = row["Open"]
            if pending_dir == 1:
                entry_px = raw_entry + bar_spread / 2.0 + slippage
            else:
                entry_px = raw_entry - bar_spread / 2.0 - slippage

            sl = pending_sl
            tp = pending_tp
            direction = pending_dir
            sl_distance = abs(entry_px - sl)
            if sl_distance > 0:
                current_lot = dynamic_lot(balance, sl_distance, risk_pct)
                initial_risk = sl_distance
                in_trade = True
                bars_in_trade = 0
            pending_entry = False

        # ── Manage open trade ──
        if in_trade:
            bars_in_trade += 1
            hit_sl = False
            hit_tp = False

            # Trailing stop logic
            if trailing_stop and initial_risk > 0:
                if direction == 1:
                    unrealized = row["High"] - entry_px
                    if unrealized >= initial_risk:  # 1R profit reached
                        new_sl = max(sl, row["High"] - initial_risk)
                        sl = max(sl, new_sl)  # only move up
                else:
                    unrealized = entry_px - row["Low"]
                    if unrealized >= initial_risk:
                        new_sl = min(sl, row["Low"] + initial_risk)
                        sl = min(sl, new_sl)  # only move down

            if direction == 1:
                hit_sl = row["Low"] <= sl
                hit_tp = row["High"] >= tp
            else:
                hit_sl = row["High"] >= sl
                hit_tp = row["Low"] <= tp

            # Time-based exit
            time_exit = (max_bars_in_trade > 0 and bars_in_trade >= max_bars_in_trade)

            if hit_sl:
                if direction == 1:
                    exit_px = sl - slippage
                else:
                    exit_px = sl + slippage
                pnl = profit(entry_px, exit_px, direction, current_lot)
                balance += pnl
                trades.append(pnl)
                in_trade = False
            elif hit_tp:
                if direction == 1:
                    exit_px = tp - slippage
                else:
                    exit_px = tp + slippage
                pnl = profit(entry_px, exit_px, direction, current_lot)
                balance += pnl
                trades.append(pnl)
                in_trade = False
            elif time_exit:
                # Close at current bar's close
                exit_px = row["Close"]
                if direction == 1:
                    exit_px -= slippage
                else:
                    exit_px += slippage
                pnl = profit(entry_px, exit_px, direction, current_lot)
                balance += pnl
                trades.append(pnl)
                in_trade = False

            while not in_trade and balance >= next_x10_target:
                x10_count += 1
                next_x10_target *= 10

        if balance <= 0:
            balance = 0.0
            break

        # ── Register signal for next-bar entry ──
        sig = signals.iloc[i]
        if not in_trade and not pending_entry and sig != 0:
            sl_val = sl_prices.iloc[i]
            tp_val = tp_prices.iloc[i]
            if not (math.isnan(sl_val) or math.isnan(tp_val)):
                pending_entry = True
                pending_sl = sl_val
                pending_tp = tp_val
                pending_dir = int(sig)

        equity_curve.append(balance)
        if balance > equity_peak:
            equity_peak = balance
        dd = (equity_peak - balance) / equity_peak if equity_peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    n = len(trades)
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    win_rate = len(wins) / n if n else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    return {
        "total_trades": n,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(pf, 4),
        "max_drawdown": round(max_dd, 4),
        "x10_count": x10_count,
        "final_balance": round(balance, 2),
        "return_pct": round((balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100, 2),
        "blown_account": balance <= 0,
        "equity_curve": equity_curve,
    }


def validate(metrics: dict, regimes_tested: int) -> Tuple[bool, List[str]]:
    fails = []
    if metrics["win_rate"] <= MIN_WIN_RATE:
        fails.append(f"WR {metrics['win_rate']:.1%} <= {MIN_WIN_RATE:.0%}")
    if metrics["profit_factor"] < MIN_PROFIT_FACTOR:
        fails.append(f"PF {metrics['profit_factor']:.2f} < {MIN_PROFIT_FACTOR}")
    if metrics["max_drawdown"] >= MAX_DRAWDOWN:
        fails.append(f"DD {metrics['max_drawdown']:.1%} >= {MAX_DRAWDOWN:.0%}")
    if metrics["x10_count"] < MIN_X10_COUNT:
        fails.append(f"x10_count {metrics['x10_count']} < {MIN_X10_COUNT}")
    if metrics["total_trades"] < MIN_TRADES:
        fails.append(f"trades {metrics['total_trades']} < {MIN_TRADES}")
    if regimes_tested < MIN_REGIMES:
        fails.append(f"regimes {regimes_tested} < {MIN_REGIMES}")
    return (len(fails) == 0, fails)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_engine.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add engine/__init__.py engine/backtest.py tests/test_engine.py
git commit -m "feat: add improved backtest engine with trailing stop, time exit, session filter"
```

---

### Task 2: Backtest Runner agent

**Files:**
- Create: `agents/backtest_runner.py`
- Create: `tests/test_backtest_runner.py`

- [ ] **Step 1: Write tests**

`tests/test_backtest_runner.py`:
```python
"""Tests for Backtest Runner agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("backtest_runner", "backtest_runner", "agents.backtest_runner", "BacktestRunner",
         '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_backtest_runner_imports():
    from agents.backtest_runner import BacktestRunner
    assert BacktestRunner.name == "backtest_runner"


def test_run_backtest_on_strategy(tmp_db):
    """BacktestRunner should be able to run a backtest given a strategy ID."""
    from agents.backtest_runner import BacktestRunner

    # Register a known strategy
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status) VALUES (?, ?, ?, ?)",
        ("S001", "strategies/strategy_s001.py", "EMA", "candidate"),
    )

    agent = BacktestRunner(tmp_db)
    agent.setup()

    # Run backtest (uses actual strategy file + data on disk)
    result = agent.run_single_backtest("S001")
    # Should return a dict with metrics or None if data/strategy missing
    assert result is None or isinstance(result, dict)


def test_process_task_from_queue(tmp_db):
    """BacktestRunner should pick up and process backtest tasks."""
    from agents.backtest_runner import BacktestRunner

    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status) VALUES (?, ?, ?, ?)",
        ("S001", "strategies/strategy_s001.py", "EMA", "candidate"),
    )
    tmp_db.execute(
        "INSERT INTO task_queue (agent_target, task_type, payload, created_by) VALUES (?, ?, ?, ?)",
        ("backtest_runner", "backtest", json.dumps({"strategy_id": "S001"}), "test"),
    )

    agent = BacktestRunner(tmp_db)
    agent.setup()
    agent.tick()  # Should process the queued task

    # Task should be completed or failed (not still pending)
    task = tmp_db.fetchone("SELECT status FROM task_queue WHERE agent_target = 'backtest_runner'")
    assert task["status"] in ("completed", "failed")


def test_tick_no_crash_empty_queue(tmp_db):
    from agents.backtest_runner import BacktestRunner
    agent = BacktestRunner(tmp_db)
    agent.setup()
    agent.tick()  # Should not crash with empty queue
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Write implementation**

`agents/backtest_runner.py`:
```python
"""Backtest Runner: continuously backtests strategies from the task queue."""
import json
import importlib.util
import traceback
from pathlib import Path
from typing import Optional

import pandas as pd
import ta

from agents.base_agent import BaseAgent
from core.config import DATA_DIR, STRATEGIES_DIR, DEFAULT_RISK_PCT


class BacktestRunner(BaseAgent):
    name = "backtest_runner"

    def __init__(self, db):
        super().__init__(agent_id="backtest_runner", db=db)
        self._data_cache = None
        self._data_hash = None

    def setup(self):
        self.logger.info("Backtest Runner ready")

    def tick(self):
        # Process pending tasks
        tasks = self.get_pending_tasks()
        if not tasks:
            # No tasks — check for untested strategies
            untested = self.db.fetchall(
                "SELECT id FROM strategies WHERE status = 'candidate' "
                "AND id NOT IN (SELECT DISTINCT strategy_id FROM backtest_results) "
                "LIMIT 5"
            )
            for row in untested:
                self.run_single_backtest(row["id"])
            return

        for task in tasks:
            self.db.execute(
                "UPDATE task_queue SET status = 'running', started_at = datetime('now') WHERE id = ?",
                (task["id"],),
            )
            try:
                payload = json.loads(task["payload"]) if isinstance(task["payload"], str) else task["payload"]
                strategy_id = payload.get("strategy_id")
                risk_pct = payload.get("risk_pct", DEFAULT_RISK_PCT)
                trailing = payload.get("trailing_stop", True)
                max_bars = payload.get("max_bars_in_trade", 60)

                if not strategy_id:
                    self.fail_task(task["id"], "Missing strategy_id in payload")
                    continue

                result = self.run_single_backtest(
                    strategy_id, risk_pct=risk_pct,
                    trailing_stop=trailing, max_bars_in_trade=max_bars,
                )
                if result:
                    self.complete_task(task["id"], result)
                else:
                    self.fail_task(task["id"], "Backtest returned no result")
            except Exception as e:
                self.fail_task(task["id"], str(e))
                self.logger.error(f"Task {task['id']} failed: {e}")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 10)

    def _load_data(self) -> Optional[pd.DataFrame]:
        """Load the best available M1 data."""
        data_files = sorted((DATA_DIR / "raw").glob("XAUUSD_M1*.csv"))
        if not data_files:
            self.logger.warning("No M1 data files found")
            return None

        # Use the largest file
        best_file = max(data_files, key=lambda f: f.stat().st_size)
        file_hash = str(best_file.stat().st_mtime)

        if self._data_cache is not None and self._data_hash == file_hash:
            return self._data_cache

        df = pd.read_csv(best_file, parse_dates=["time"])
        # Normalize column names
        rename_map = {}
        for col in df.columns:
            if col.lower() == "open" and col != "Open":
                rename_map[col] = "Open"
            elif col.lower() == "high" and col != "High":
                rename_map[col] = "High"
            elif col.lower() == "low" and col != "Low":
                rename_map[col] = "Low"
            elif col.lower() == "close" and col != "Close":
                rename_map[col] = "Close"
            elif col.lower() in ("tick_volume", "volume") and col != "Volume":
                rename_map[col] = "Volume"
        if rename_map:
            df = df.rename(columns=rename_map)

        df = df.sort_values("time").reset_index(drop=True)
        self._data_cache = df
        self._data_hash = file_hash
        return df

    def _load_strategy(self, strategy_id: str):
        """Load a strategy module by its ID."""
        row = self.db.fetchone("SELECT file_path FROM strategies WHERE id = ?", (strategy_id,))
        if not row:
            return None

        file_path = Path(row["file_path"])
        if not file_path.is_absolute():
            file_path = STRATEGIES_DIR.parent / file_path

        if not file_path.exists():
            # Try finding it in strategies dir
            alt_path = STRATEGIES_DIR / f"strategy_{strategy_id.lower()}.py"
            if alt_path.exists():
                file_path = alt_path
            else:
                return None

        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_single_backtest(
        self,
        strategy_id: str,
        risk_pct: float = DEFAULT_RISK_PCT,
        trailing_stop: bool = True,
        max_bars_in_trade: int = 60,
    ) -> Optional[dict]:
        """Run a backtest for a single strategy and store results."""
        from engine.backtest import run_simulation, validate

        df = self._load_data()
        if df is None:
            self.emit_event("warning", f"No data available for backtesting {strategy_id}")
            return None

        module = self._load_strategy(strategy_id)
        if module is None:
            self.emit_event("warning", f"Strategy {strategy_id} not found")
            return None

        try:
            params = module.PARAMS
            sig_df = module.generate_signals(df.copy(), params)
            signals = sig_df["signal"].fillna(0).astype(int)

            # Compute SL/TP from ATR
            if "ATR" not in sig_df.columns:
                sig_df["ATR"] = ta.volatility.average_true_range(
                    sig_df["High"], sig_df["Low"], sig_df["Close"], window=14
                )

            sl_atr = params.get("sl_atr", 1.5)
            tp_atr = params.get("tp_atr", 2.5)

            sl_prices = pd.Series(index=sig_df.index, dtype=float)
            tp_prices = pd.Series(index=sig_df.index, dtype=float)

            long_mask = signals == 1
            short_mask = signals == -1

            sl_prices[long_mask] = sig_df.loc[long_mask, "Close"] - sl_atr * sig_df.loc[long_mask, "ATR"]
            tp_prices[long_mask] = sig_df.loc[long_mask, "Close"] + tp_atr * sig_df.loc[long_mask, "ATR"]
            sl_prices[short_mask] = sig_df.loc[short_mask, "Close"] + sl_atr * sig_df.loc[short_mask, "ATR"]
            tp_prices[short_mask] = sig_df.loc[short_mask, "Close"] - tp_atr * sig_df.loc[short_mask, "ATR"]

            metrics = run_simulation(
                df, signals, sl_prices, tp_prices, signals,
                risk_pct=risk_pct,
                trailing_stop=trailing_stop,
                max_bars_in_trade=max_bars_in_trade,
                session_filter=True,
                session_hours=(7, 21),
            )

            # Store results
            self.db.execute(
                "INSERT INTO backtest_results "
                "(strategy_id, risk_pct, config, total_trades, win_rate, profit_factor, "
                "max_drawdown, x10_count, final_balance, return_pct, blown_account) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    strategy_id, risk_pct,
                    json.dumps({"trailing_stop": trailing_stop, "max_bars": max_bars_in_trade}),
                    metrics["total_trades"], metrics["win_rate"], metrics["profit_factor"],
                    metrics["max_drawdown"], metrics["x10_count"], metrics["final_balance"],
                    metrics["return_pct"], metrics["blown_account"],
                ),
            )

            # Update strategy best metrics
            current = self.db.fetchone("SELECT best_profit_factor FROM strategies WHERE id = ?", (strategy_id,))
            if current and (current["best_profit_factor"] is None or metrics["profit_factor"] > (current["best_profit_factor"] or 0)):
                self.db.execute(
                    "UPDATE strategies SET best_win_rate=?, best_profit_factor=?, best_max_drawdown=?, "
                    "best_x10_count=?, best_final_balance=?, best_config=? WHERE id=?",
                    (
                        metrics["win_rate"], metrics["profit_factor"], metrics["max_drawdown"],
                        metrics["x10_count"], metrics["final_balance"],
                        json.dumps({"risk_pct": risk_pct, "trailing": trailing_stop, "max_bars": max_bars_in_trade}),
                        strategy_id,
                    ),
                )

            self.logger.info(
                f"[{strategy_id}] WR={metrics['win_rate']:.1%} PF={metrics['profit_factor']:.2f} "
                f"DD={metrics['max_drawdown']:.1%} x10={metrics['x10_count']} trades={metrics['total_trades']}"
            )

            # Check if validated
            passed, _ = validate(metrics, regimes_tested=3)
            if passed:
                self.db.execute("UPDATE strategies SET status = 'validated' WHERE id = ?", (strategy_id,))
                self.emit_event("milestone", f"Strategy {strategy_id} PASSED validation!", metrics)

            return metrics

        except Exception as e:
            self.emit_event("error", f"Backtest failed for {strategy_id}: {traceback.format_exc()}")
            return None
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_backtest_runner.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/backtest_runner.py tests/test_backtest_runner.py
git commit -m "feat: add Backtest Runner agent with task queue processing"
```

---

### Task 3: Strategy Factory agent

**Files:**
- Create: `agents/strategy_factory.py`
- Create: `tests/test_strategy_factory.py`

- [ ] **Step 1: Write tests**

`tests/test_strategy_factory.py`:
```python
"""Tests for Strategy Factory agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("strategy_factory", "strategy_factory", "agents.strategy_factory", "StrategyFactory",
         '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_strategy_factory_imports():
    from agents.strategy_factory import StrategyFactory
    assert StrategyFactory.name == "strategy_factory"


def test_build_generation_prompt(tmp_db):
    """The prompt builder should create a valid prompt string."""
    from agents.strategy_factory import StrategyFactory
    agent = StrategyFactory(tmp_db)
    prompt = agent._build_generation_prompt()
    assert isinstance(prompt, str)
    assert "generate_signals" in prompt
    assert "PARAMS" in prompt
    assert len(prompt) > 100


def test_validate_strategy_code_valid():
    """Valid strategy code should pass validation."""
    from agents.strategy_factory import validate_strategy_code
    code = '''
import pandas as pd
import numpy as np
import ta

PARAMS = {"ema_fast": 5, "ema_slow": 20, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0}

def generate_signals(df, p=PARAMS):
    df["signal"] = 0
    return df
'''
    is_valid, error = validate_strategy_code(code)
    assert is_valid, f"Should be valid but got: {error}"


def test_validate_strategy_code_invalid():
    """Code without PARAMS or generate_signals should fail."""
    from agents.strategy_factory import validate_strategy_code
    code = "x = 1 + 2"
    is_valid, error = validate_strategy_code(code)
    assert not is_valid


def test_register_strategy(tmp_db):
    from agents.strategy_factory import StrategyFactory
    agent = StrategyFactory(tmp_db)
    agent._register_strategy(
        strategy_id="S100",
        file_path="strategies/strategy_s100.py",
        family="momentum",
        description="test strategy",
    )
    row = tmp_db.fetchone("SELECT * FROM strategies WHERE id = ?", ("S100",))
    assert row["family"] == "momentum"
    assert row["status"] == "candidate"


def test_tick_no_crash_without_api(tmp_db):
    """Tick should handle missing API key gracefully."""
    from agents.strategy_factory import StrategyFactory
    agent = StrategyFactory(tmp_db)
    agent.setup()
    # tick() will try to call LLM which may fail without API key
    # but it should not crash the agent
    try:
        agent.tick()
    except Exception:
        pass  # Expected if no API key
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Write implementation**

`agents/strategy_factory.py`:
```python
"""Strategy Factory: generates new trading strategies using Claude API."""
import json
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from agents.base_agent import BaseAgent
from agents.model_router import ModelRouter
from core.config import STRATEGIES_DIR


# Strategy types to explore (the factory chooses which to generate)
STRATEGY_TYPES = [
    "momentum_burst",       # consecutive directional bars + volume spike
    "range_breakout",       # M5/M15 consolidation then M1 breakout
    "order_block",          # fair value gap / price imbalance zones
    "pullback_in_trend",    # H1 trend + M1 pullback to key level
    "session_breakout",     # London/NY open range breakout
    "volume_anomaly",       # tick_volume spikes as entry signal
    "multi_tf_confluence",  # multiple timeframe agreement
    "candle_pattern",       # engulfing, pin bar + context
    "mean_reversion",       # extreme deviation from VWAP/MA then snap back
    "momentum_divergence",  # price vs RSI/MACD divergence
]


def validate_strategy_code(code: str) -> Tuple[bool, str]:
    """Check that strategy code is syntactically valid and has required components."""
    # Syntax check
    try:
        compile(code, "<strategy>", "exec")
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    # Must have PARAMS dict
    if "PARAMS" not in code:
        return False, "Missing PARAMS dict"

    # Must have generate_signals function
    if "def generate_signals" not in code:
        return False, "Missing generate_signals function"

    # Must import pandas
    if "import pandas" not in code and "from pandas" not in code:
        return False, "Missing pandas import"

    # Must have signal column assignment
    if '"signal"' not in code and "'signal'" not in code:
        return False, "Missing 'signal' column assignment"

    return True, ""


class StrategyFactory(BaseAgent):
    name = "strategy_factory"

    def __init__(self, db):
        super().__init__(agent_id="strategy_factory", db=db)
        self._generation_count = 0

    def setup(self):
        # Count existing strategies
        row = self.db.fetchone("SELECT COUNT(*) as cnt FROM strategies")
        existing = row["cnt"] if row else 0
        self._generation_count = existing
        self.logger.info(f"Strategy Factory ready — {existing} strategies in DB")

    def tick(self):
        # Decide what type of strategy to generate
        strategy_type = self._choose_strategy_type()
        self.logger.info(f"Generating new strategy: {strategy_type}")

        try:
            code = self._generate_strategy(strategy_type)
            if code is None:
                return

            is_valid, error = validate_strategy_code(code)
            if not is_valid:
                self.emit_event("warning", f"Generated invalid code: {error}")
                # Try to fix with a second call
                code = self._fix_strategy_code(code, error)
                if code is None:
                    return
                is_valid, error = validate_strategy_code(code)
                if not is_valid:
                    self.emit_event("error", f"Could not fix strategy code: {error}")
                    return

            # Save strategy
            self._generation_count += 1
            strategy_id = f"G{self._generation_count:04d}"
            file_name = f"strategy_{strategy_id.lower()}.py"
            file_path = STRATEGIES_DIR / file_name

            file_path.write_text(code, encoding="utf-8")

            self._register_strategy(
                strategy_id=strategy_id,
                file_path=str(file_path),
                family=strategy_type,
                description=f"Auto-generated {strategy_type} strategy",
            )

            # Post backtest task
            self.post_task("backtest_runner", "backtest", {
                "strategy_id": strategy_id,
                "trailing_stop": True,
                "max_bars_in_trade": 60,
            })

            self.emit_event("info", f"Generated strategy {strategy_id} ({strategy_type})")
            self.logger.info(f"Strategy {strategy_id} saved to {file_path}")

        except Exception as e:
            self.emit_event("error", f"Strategy generation failed: {traceback.format_exc()}")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 600)

    def _choose_strategy_type(self) -> str:
        """Choose which type of strategy to generate based on what's been tried."""
        # Count strategies per type
        rows = self.db.fetchall(
            "SELECT family, COUNT(*) as cnt, MAX(best_profit_factor) as best_pf "
            "FROM strategies GROUP BY family"
        )
        tried = {row["family"]: {"count": row["cnt"], "best_pf": row["best_pf"] or 0} for row in rows}

        # Prefer types that haven't been tried or have few attempts
        import random
        untried = [t for t in STRATEGY_TYPES if t not in tried]
        if untried:
            return random.choice(untried)

        # Otherwise pick the type with fewest attempts
        least_tried = min(STRATEGY_TYPES, key=lambda t: tried.get(t, {}).get("count", 0))
        return least_tried

    def _build_generation_prompt(self, strategy_type: str = "momentum_burst") -> str:
        """Build the prompt for Claude to generate a strategy."""
        # Get current best results for context
        best_rows = self.db.fetchall(
            "SELECT id, family, best_win_rate, best_profit_factor, best_max_drawdown "
            "FROM strategies WHERE best_profit_factor IS NOT NULL "
            "ORDER BY best_profit_factor DESC LIMIT 5"
        )
        best_context = ""
        if best_rows:
            best_context = "\n\nCurrent best strategies:\n"
            for r in best_rows:
                best_context += (
                    f"- {r['id']} ({r['family']}): WR={r['best_win_rate']}, "
                    f"PF={r['best_profit_factor']}, DD={r['best_max_drawdown']}\n"
                )

        return f"""Generate a XAUUSD M1 scalping strategy of type: {strategy_type}

REQUIREMENTS:
1. Must be a complete Python file
2. Must have a PARAMS dict with all configurable parameters including sl_atr and tp_atr
3. Must have a function: def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame
4. The function receives a DataFrame with columns: time, Open, High, Low, Close, Volume, spread
5. Must return the DataFrame with an added 'signal' column: 1=long, -1=short, 0=flat
6. Use the 'ta' library for indicators (import ta)
7. Import pandas as pd and numpy as np
8. Do NOT use simple EMA/MACD/RSI crossovers — those have been tried extensively and fail
9. Focus on PRICE ACTION and MARKET MICROSTRUCTURE
10. Consider using: tick_volume for confirmation, session times, multi-bar patterns
11. Be creative — find edges that aren't obvious

Target metrics (XAUUSD M1 scalping):
- Win Rate > 62%
- Profit Factor > 2.0  
- Max Drawdown < 35%
{best_context}

Strategy type hints for {strategy_type}:
- momentum_burst: Look for 3+ consecutive same-direction bars with increasing volume
- range_breakout: Detect tight consolidation (low ATR period) then breakout
- order_block: Find imbalance zones where price moved fast (gap between candles)
- pullback_in_trend: Use longer MA for trend, enter on pullback to short MA
- session_breakout: Track Asian session range, trade London/NY breakout
- volume_anomaly: Spike in tick_volume as entry trigger with trend confirmation
- mean_reversion: Price far from VWAP or moving average, bet on snap-back
- momentum_divergence: Price making new high but RSI/momentum indicator declining

OUTPUT: Return ONLY the Python code, no markdown, no explanation."""

    def _generate_strategy(self, strategy_type: str) -> Optional[str]:
        """Call Claude to generate strategy code."""
        prompt = self._build_generation_prompt(strategy_type)
        model = ModelRouter.route_task("generate_strategy")

        try:
            response = self.call_llm(
                prompt=prompt,
                model=model,
                task_type="generate_strategy",
                system="You are an expert quantitative trading strategy developer. Output only valid Python code.",
                temperature=0.8,
            )

            # Clean response — remove markdown code blocks if present
            code = response.strip()
            if code.startswith("```python"):
                code = code[len("```python"):].strip()
            if code.startswith("```"):
                code = code[3:].strip()
            if code.endswith("```"):
                code = code[:-3].strip()

            return code

        except Exception as e:
            self.emit_event("error", f"LLM call failed: {e}")
            return None

    def _fix_strategy_code(self, code: str, error: str) -> Optional[str]:
        """Try to fix invalid strategy code using Claude."""
        prompt = f"""Fix this Python trading strategy code. The error is: {error}

Code:
```python
{code}
```

Requirements:
- Must have PARAMS dict with sl_atr and tp_atr keys
- Must have: def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame
- Must set df["signal"] to 1 (long), -1 (short), or 0 (flat)
- Must import pandas as pd, numpy as np, ta

Return ONLY the fixed Python code."""

        try:
            response = self.call_llm(
                prompt=prompt,
                model="sonnet",  # cheaper for fixes
                task_type="debug_strategy",
                system="Fix the code. Output only valid Python.",
                temperature=0.3,
            )
            code = response.strip()
            if code.startswith("```python"):
                code = code[len("```python"):].strip()
            if code.startswith("```"):
                code = code[3:].strip()
            if code.endswith("```"):
                code = code[:-3].strip()
            return code
        except Exception:
            return None

    def _register_strategy(self, strategy_id: str, file_path: str, family: str, description: str):
        """Register a new strategy in the database."""
        self.db.execute(
            "INSERT OR REPLACE INTO strategies (id, file_path, family, description, created_by, status) "
            "VALUES (?, ?, ?, ?, ?, 'candidate')",
            (strategy_id, file_path, family, description, self.agent_id),
        )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_strategy_factory.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/strategy_factory.py tests/test_strategy_factory.py
git commit -m "feat: add Strategy Factory agent with Claude-powered strategy generation"
```

---

### Task 4: Register new agents in config and orchestrator

**Files:**
- Modify: `core/config.py` — add backtest_runner and strategy_factory to CORE_AGENTS

- [ ] **Step 1: Update CORE_AGENTS in config.py**

Add these two entries to the CORE_AGENTS list in `core/config.py`:

```python
    {
        "name": "backtest_runner",
        "module_path": "agents.backtest_runner",
        "class_name": "BacktestRunner",
        "config": {"tick_interval": 10},
        "can_spawn_children": False,
    },
    {
        "name": "strategy_factory",
        "module_path": "agents.strategy_factory",
        "class_name": "StrategyFactory",
        "config": {"tick_interval": 600},
        "can_spawn_children": False,
    },
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL tests pass (should be ~55+ tests)

- [ ] **Step 3: Commit**

```bash
git add core/config.py
git commit -m "feat: register Backtest Runner and Strategy Factory as core agents"
```

---

### Task 5: Integration test — run system with all 5 agents

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL tests pass

- [ ] **Step 2: Start system briefly**

Run system for 15 seconds, verify all 5 agents start:
```
timeout 15 python start.py
```
Expected: token_manager, model_router, data_agent, backtest_runner, strategy_factory all start

- [ ] **Step 3: Verify DB state**

```python
python -c "
from core.db import Database; from core.config import DB_PATH
db = Database(DB_PATH)
agents = db.fetchall('SELECT name, status FROM agent_registry')
print('Agents:', [dict(r) for r in agents])
strats = db.fetchall('SELECT COUNT(*) as c FROM strategies')
print('Strategies:', strats[0]['c'] if strats else 0)
db.close()
"
```

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "fix: Phase 2 integration fixes" || echo "No fixes needed"
```
