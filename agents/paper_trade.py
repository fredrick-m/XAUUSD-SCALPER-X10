"""Paper Trade Agent: connects to MT5 demo account for live strategy validation."""
import json
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional

from agents.base_agent import BaseAgent
from agents.risk_manager import is_trading_allowed, get_position_scaling, get_max_open_trades

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


SYMBOL = "XAUUSD"
TIMEFRAME_M1 = 1  # mt5.TIMEFRAME_M1
MAGIC_NUMBER = 424242
MAX_BARS_LOOKBACK = 500


class PaperTradeAgent(BaseAgent):
    """
    Executes validated strategies on MT5 demo account for live validation.

    Compares live results against backtest expectations to detect drift.
    Requires MetaTrader5 Python package and a running MT5 terminal.
    """

    name = "paper_trade"

    def __init__(self, db):
        super().__init__(agent_id="paper_trade", db=db)
        self._mt5_connected = False
        self._active_strategies: list = []
        self._open_positions: dict = {}  # strategy_id -> position info
        self._trade_log: list = []

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        if not MT5_AVAILABLE:
            self.logger.warning(
                "MetaTrader5 package not installed. "
                "Install with: pip install MetaTrader5. "
                "Agent will run in simulation-only mode."
            )
            self.emit_event("warning", "MT5 not installed — paper trade agent in dry-run mode")
        else:
            self._connect_mt5()

        # Load validated strategies for paper trading
        self._load_active_strategies()
        self.logger.info(
            f"Paper Trade Agent ready — {len(self._active_strategies)} strategies, "
            f"MT5 {'connected' if self._mt5_connected else 'disconnected'}"
        )

    def tick(self):
        """Main tick: check signals, manage positions, log results."""
        if not self._active_strategies:
            self._load_active_strategies()
            if not self._active_strategies:
                return

        # Check risk manager
        if not is_trading_allowed(self.db):
            self.logger.info("Trading paused by risk manager — skipping tick")
            return

        if self._mt5_connected:
            self._tick_live()
        else:
            self._tick_dry_run()

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 60)

    def cleanup(self):
        if self._mt5_connected and MT5_AVAILABLE:
            mt5.shutdown()
            self.logger.info("MT5 disconnected")

    # ──────────────────────────────────────────────────
    # MT5 connection
    # ──────────────────────────────────────────────────

    def _connect_mt5(self):
        if not MT5_AVAILABLE:
            return
        try:
            if not mt5.initialize():
                self.logger.error(f"MT5 init failed: {mt5.last_error()}")
                self.emit_event("error", f"MT5 init failed: {mt5.last_error()}")
                return

            account_info = mt5.account_info()
            if account_info is None:
                self.logger.error("No MT5 account info available")
                return

            # Verify it's a demo account
            if account_info.trade_mode != 0:  # 0 = demo
                self.logger.warning(
                    f"MT5 account is NOT demo (mode={account_info.trade_mode}). "
                    "Refusing to paper trade on a live account."
                )
                self.emit_event(
                    "error",
                    "MT5 account is LIVE, not demo. Paper trade agent will NOT place orders."
                )
                return

            self._mt5_connected = True
            self.emit_event(
                "info",
                f"MT5 connected: account #{account_info.login}, "
                f"balance={account_info.balance:.2f}, "
                f"server={account_info.server}",
            )
            self.logger.info(f"MT5 connected: #{account_info.login} on {account_info.server}")
        except Exception as exc:
            self.logger.error(f"MT5 connection failed: {exc}")

    # ──────────────────────────────────────────────────
    # Strategy loading
    # ──────────────────────────────────────────────────

    def _load_active_strategies(self):
        """Load validated strategies that passed walk-forward and are not fragile."""
        rows = self.db.fetchall(
            "SELECT id, file_path, best_config, best_profit_factor, best_win_rate "
            "FROM strategies "
            "WHERE status = 'validated' AND walk_forward_passed = 1 "
            "ORDER BY best_profit_factor DESC "
            "LIMIT 10"
        )
        self._active_strategies = []
        for row in rows:
            config = {}
            if row["best_config"]:
                config = (
                    json.loads(row["best_config"])
                    if isinstance(row["best_config"], str)
                    else row["best_config"]
                )
            # Skip fragile strategies
            if config.get("monte_carlo", {}).get("p_ruin", 0) > 0.10:
                continue
            if config.get("sensitivity", {}).get("is_fragile", False):
                continue

            self._active_strategies.append(dict(row))

        if self._active_strategies:
            ids = [s["id"] for s in self._active_strategies]
            self.logger.info(f"Active strategies for paper trading: {ids}")

    # ──────────────────────────────────────────────────
    # Live tick (MT5 connected)
    # ──────────────────────────────────────────────────

    def _tick_live(self):
        """Execute signals on MT5 demo account."""
        import importlib.util
        import pandas as pd
        import numpy as np
        from pathlib import Path
        from core.config import STRATEGIES_DIR

        # Get M1 bars and resample to M5 (all validated strategies are M5)
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, MAX_BARS_LOOKBACK)
        if rates is None or len(rates) < 100:
            self.logger.warning("Could not fetch M1 bars from MT5")
            return

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume",
        })

        # Resample to M5 — all validated strategies are M5-optimized
        df = df.set_index("time")
        df = df.resample("5min").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }).dropna().reset_index()

        scaling = get_position_scaling(self.db)
        max_trades = get_max_open_trades(self.db)
        current_open = len(self._open_positions)

        for strat in self._active_strategies:
            strategy_id = strat["id"]

            # Skip if already has an open position
            if strategy_id in self._open_positions:
                self._check_exit(strategy_id, df)
                continue

            # Skip if at max trades
            if current_open >= max_trades:
                continue

            # Load strategy and generate signal
            module = self._load_strategy_module(strategy_id)
            if module is None:
                continue

            try:
                params = getattr(module, "PARAMS", {})
                result_df = module.generate_signals(df.copy(), params)
                if "signal" not in result_df.columns:
                    continue

                last_signal = result_df["signal"].iloc[-1]
                if last_signal == 0:
                    continue

                # Place order on MT5
                self._place_order(strategy_id, last_signal, df, params, scaling)
                current_open += 1

            except Exception as exc:
                self.logger.error(f"Signal gen failed for {strategy_id}: {exc}")

    def _place_order(self, strategy_id: str, signal: int, df, params: dict, scaling: float):
        """Place a market order on MT5 demo."""
        import ta
        from core.config import DEFAULT_RISK_PCT, PIP_VALUE, MIN_LOT, MAX_LOT

        sl_atr = params.get("sl_atr", 1.5)
        tp_atr = params.get("tp_atr", 2.5)

        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None:
            return

        # Proper ATR calculation
        atr_series = ta.volatility.average_true_range(
            df["High"], df["Low"], df["Close"], window=14
        )
        atr_val = atr_series.iloc[-1]
        if atr_val <= 0 or atr_val != atr_val:  # NaN check
            return

        if signal == 1:
            price = tick.ask
            sl = price - sl_atr * atr_val
            tp = price + tp_atr * atr_val
            order_type = mt5.ORDER_TYPE_BUY
        else:
            price = tick.bid
            sl = price + sl_atr * atr_val
            tp = price - tp_atr * atr_val
            order_type = mt5.ORDER_TYPE_SELL

        # Dynamic lot sizing: risk % of account balance
        account = mt5.account_info()
        balance = account.balance if account else 50.0
        sl_distance = abs(price - sl)
        if sl_distance <= 0:
            return
        lot = (balance * DEFAULT_RISK_PCT) / (sl_distance * PIP_VALUE) * scaling
        lot = max(MIN_LOT, min(MAX_LOT, round(lot, 2)))

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": f"PT_{strategy_id}",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self._open_positions[strategy_id] = {
                "ticket": result.order,
                "type": "buy" if signal == 1 else "sell",
                "price": price,
                "sl": sl,
                "tp": tp,
                "lot": lot,
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }
            self.emit_event(
                "trade_open",
                f"Paper trade opened: {strategy_id} {'BUY' if signal == 1 else 'SELL'} "
                f"@ {price:.2f}, SL={sl:.2f}, TP={tp:.2f}",
                metadata={
                    "strategy_id": strategy_id,
                    "direction": "buy" if signal == 1 else "sell",
                    "price": price, "sl": sl, "tp": tp, "lot": lot,
                },
            )
        else:
            error = result.comment if result else "unknown"
            self.logger.error(f"Order failed for {strategy_id}: {error}")

    def _check_exit(self, strategy_id: str, df):
        """Check if an open position has been closed by MT5."""
        pos_info = self._open_positions.get(strategy_id)
        if not pos_info:
            return

        # Check if position still exists
        positions = mt5.positions_get(ticket=pos_info["ticket"])
        if not positions:
            # Position closed (by SL/TP or manually)
            # Get deal history for P&L
            deals = mt5.history_deals_get(
                position=pos_info["ticket"]
            )
            pnl = 0.0
            if deals:
                pnl = sum(d.profit for d in deals)

            self._log_trade_result(strategy_id, pos_info, pnl)
            del self._open_positions[strategy_id]

    def _log_trade_result(self, strategy_id: str, pos_info: dict, pnl: float):
        """Log a completed trade."""
        self.emit_event(
            "trade_close",
            f"Paper trade closed: {strategy_id} P&L={pnl:.2f}",
            metadata={
                "strategy_id": strategy_id,
                "pnl": pnl,
                "pnl_pct": pnl / 50.0,  # approximate % of initial balance
                "direction": pos_info.get("type"),
                "entry_price": pos_info.get("price"),
                "opened_at": pos_info.get("opened_at"),
                "closed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # ──────────────────────────────────────────────────
    # Dry-run tick (no MT5)
    # ──────────────────────────────────────────────────

    def _tick_dry_run(self):
        """Log what would happen without actually placing trades."""
        # Just report status
        strat_count = len(self._active_strategies)
        if strat_count > 0:
            ids = [s["id"] for s in self._active_strategies[:5]]
            self.logger.debug(
                f"Dry-run: {strat_count} strategies ready, "
                f"MT5 not connected. Top: {ids}"
            )

    # ──────────────────────────────────────────────────
    # Strategy module loading
    # ──────────────────────────────────────────────────

    def _load_strategy_module(self, strategy_id: str):
        import importlib.util
        from pathlib import Path
        from core.config import STRATEGIES_DIR

        row = self.db.fetchone("SELECT file_path FROM strategies WHERE id = ?", (strategy_id,))
        candidate_paths = []
        if row and row["file_path"]:
            db_path = Path(row["file_path"])
            candidate_paths.append(db_path)
            from core.config import DATA_DIR
            candidate_paths.append(DATA_DIR.parent / db_path)
        candidate_paths.append(STRATEGIES_DIR / f"strategy_{strategy_id.lower()}.py")

        for p in candidate_paths:
            if p.exists():
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"strategy_{strategy_id.lower()}", str(p),
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    return module
                except Exception:
                    return None
        return None
