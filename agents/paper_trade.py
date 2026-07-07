"""Paper Trade Agent: deploys ALL validated strategies on MT5 demo account."""
import json
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from agents.signal_gatekeeper import gate_check, get_confidence_scaling

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


SYMBOL = "XAUUSD"
MAGIC_NUMBER = 424242
M5_BARS_LOOKBACK = 5000


class PaperTradeAgent(BaseAgent):
    """
    Deploys ALL validated+WF strategies on MT5 demo.

    Each strategy runs independently, watching for its own signals.
    The Signal Gatekeeper enforces strict pre-trade filters.
    All positions are persisted to live_trades table (survives restarts).
    """

    name = "paper_trade"

    def __init__(self, db):
        super().__init__(agent_id="paper_trade", db=db)
        self._mt5_connected = False
        self._active_strategies: list = []
        self._reload_counter = 0
        self._last_m5_bar_time = None  # avoid re-processing same bar
        self._module_cache: dict = {}  # strategy_id -> (module, load_time)

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
            if self._mt5_connected:
                self._reconcile_positions()

        self._load_active_strategies()
        self.logger.info(
            f"Paper Trade Agent ready — {len(self._active_strategies)} strategies, "
            f"MT5 {'connected' if self._mt5_connected else 'disconnected'}"
        )

    def tick(self):
        """Main tick: reload strategies, check signals, manage positions."""
        # Reload strategies every 10 ticks to pick up newly validated ones
        self._reload_counter += 1
        if not self._active_strategies or self._reload_counter >= 10:
            self._reload_counter = 0
            old_ids = {s["id"] for s in self._active_strategies}
            self._load_active_strategies()
            new_ids = {s["id"] for s in self._active_strategies}
            added = new_ids - old_ids
            if added:
                self.emit_event("milestone", f"New strategies deployed: {added}")
                self._register_new_strategies(added)
            if not self._active_strategies:
                return

        if self._mt5_connected:
            self._tick_live()
        else:
            if MT5_AVAILABLE:
                self._connect_mt5()
                if self._mt5_connected:
                    self._reconcile_positions()
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

            # SAFETY: refuse to trade on live accounts
            if account_info.trade_mode != 0:  # 0 = demo
                self.logger.warning(
                    f"MT5 account is NOT demo (mode={account_info.trade_mode}). "
                    "Refusing to trade on a live account."
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
    # Position reconciliation on startup
    # ──────────────────────────────────────────────────

    def _reconcile_positions(self):
        """
        On startup, sync DB live_trades with actual MT5 positions.
        Handles trades opened before restart.
        """
        if not MT5_AVAILABLE or not self._mt5_connected:
            return

        # Get MT5 positions with our magic number
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions is None:
            # MT5 call FAILED (None != empty). Do not touch the DB based on
            # an error — a transient failure here used to mark every open
            # trade as closed with no P&L.
            self.logger.warning(f"positions_get failed during reconcile: {mt5.last_error()}")
            return

        mt5_tickets = set()
        for pos in positions:
            if pos.magic != MAGIC_NUMBER:
                continue
            mt5_tickets.add(pos.ticket)

            # Check if this position exists in our DB
            row = self.db.fetchone(
                "SELECT id FROM live_trades WHERE ticket = ? AND status = 'open'",
                (pos.ticket,),
            )
            if not row:
                # MT5 has a position we don't know about — record it
                strategy_id = pos.comment.replace("PT_", "") if pos.comment else "UNKNOWN"
                direction = "buy" if pos.type == 0 else "sell"
                self.db.execute(
                    "INSERT INTO live_trades "
                    "(strategy_id, ticket, direction, entry_price, sl, tp, lot, "
                    "opened_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                    (strategy_id, pos.ticket, direction, pos.price_open,
                     pos.sl, pos.tp, pos.volume,
                     datetime.now(timezone.utc).isoformat()),
                )
                self.logger.info(f"Reconciled orphan position: ticket={pos.ticket}")

        # Close DB trades that no longer exist in MT5, backfilling the real
        # P&L from deal history so live stats stay accurate.
        db_open = self.db.fetchall(
            "SELECT id, ticket FROM live_trades WHERE status = 'open'"
        )
        for row in db_open:
            if row["ticket"] and row["ticket"] not in mt5_tickets:
                pnl = None
                close_price = None
                deals = mt5.history_deals_get(position=row["ticket"])
                if deals:
                    pnl = sum(
                        d.profit
                        + getattr(d, "swap", 0.0)
                        + getattr(d, "commission", 0.0)
                        + getattr(d, "fee", 0.0)
                        for d in deals
                    )
                    if len(deals) > 1:
                        close_price = deals[-1].price
                self.db.execute(
                    "UPDATE live_trades SET status = 'closed', "
                    "close_reason = 'reconcile_mt5_closed', "
                    "closed_at = ?, pnl = ?, close_price = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), pnl, close_price,
                     row["id"]),
                )

        self.logger.info(
            f"Position reconciliation: {len(mt5_tickets)} MT5 positions, "
            f"{len(db_open)} DB open trades"
        )

    # ──────────────────────────────────────────────────
    # Strategy loading — ALL validated+WF, no limit
    # ──────────────────────────────────────────────────

    def _bad_families(self) -> set:
        """Families with enough tested variants and a poor success ratio.

        One variant passing thresholds means little when thousands are
        generated (multiple-testing bias). If a family has FAMILY_MIN_TESTED+
        variants with real samples and fewer than FAMILY_MIN_GOOD_RATIO of
        them show PF >= 1.1, its 'winners' are treated as lucky noise.
        """
        from core.config import FAMILY_MIN_TESTED, FAMILY_MIN_GOOD_RATIO

        rows = self.db.fetchall(
            "SELECT s.family, COUNT(*) AS n_tested, "
            "SUM(CASE WHEN v.best_pf >= 1.1 THEN 1 ELSE 0 END) AS n_good "
            "FROM (SELECT strategy_id, MAX(profit_factor) AS best_pf "
            "      FROM backtest_results WHERE total_trades >= 100 "
            "      GROUP BY strategy_id) v "
            "JOIN strategies s ON s.id = v.strategy_id "
            "WHERE s.family IS NOT NULL "
            "GROUP BY s.family"
        )
        bad = set()
        for r in rows:
            n_tested = r["n_tested"] or 0
            n_good = r["n_good"] or 0
            if n_tested >= FAMILY_MIN_TESTED and (n_good / n_tested) < FAMILY_MIN_GOOD_RATIO:
                bad.add(r["family"])
        return bad

    def _load_active_strategies(self):
        """Load ALL validated strategies that passed walk-forward + holdout."""
        rows = self.db.fetchall(
            "SELECT s.id, s.file_path, s.family, s.best_config, s.best_profit_factor, "
            "s.best_win_rate, s.best_max_drawdown "
            "FROM strategies s "
            "WHERE s.status = 'validated' AND s.walk_forward_passed = 1 "
            "ORDER BY s.best_profit_factor DESC"
        )
        bad_families = self._bad_families() if rows else set()
        skipped_family = 0
        self._active_strategies = []
        for row in rows:
            config = {}
            if row["best_config"]:
                try:
                    config = (
                        json.loads(row["best_config"])
                        if isinstance(row["best_config"], str)
                        else row["best_config"]
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

            # Family robustness gate — EXCEPT probation strategies: they
            # carry individual proof (stricter bars + holdout) and already
            # trade at quarter size with live graduation/suspension. The
            # gate exists to block ordinary passers from noisy families,
            # not the system's designated controlled experiments.
            if (row["family"] and row["family"] in bad_families
                    and not config.get("probation")):
                skipped_family += 1
                continue

            # Skip fragile strategies (Monte Carlo ruin > 10%)
            if config.get("monte_carlo", {}).get("p_ruin", 0) > 0.10:
                continue
            # Skip sensitivity-fragile strategies
            if config.get("sensitivity", {}).get("is_fragile", False):
                continue

            # Check if strategy is suspended by trade_supervisor
            live_stat = self.db.fetchone(
                "SELECT status FROM strategy_live_stats WHERE strategy_id = ?",
                (row["id"],),
            )
            if live_stat and live_stat["status"] == "suspended":
                continue

            self._active_strategies.append(dict(row))

        # NO deployment cap: everything deployable deploys (owner's call).
        # Deployment only decides who WATCHES the market; live exposure is
        # throttled downstream by the gatekeeper funnel — 1 position per
        # strategy, entry-burst window (2/direction/15min), portfolio heat
        # capped at 25% of the CURRENT balance, directional bias, margin,
        # news blackout and the circuit breaker. Each agent does its job.

        if self._active_strategies or skipped_family:
            ids = [s["id"] for s in self._active_strategies]
            self.logger.info(
                f"Active strategies: {len(ids)} deployed "
                f"(top 5: {ids[:5]}), {skipped_family} skipped by family gate"
            )

    def _register_new_strategies(self, new_ids: set):
        """Register new strategies in strategy_live_stats."""
        for sid in new_ids:
            self.db.execute(
                "INSERT OR IGNORE INTO strategy_live_stats "
                "(strategy_id, confidence_score, deployed_at) "
                "VALUES (?, 50.0, ?)",
                (sid, datetime.now(timezone.utc).isoformat()),
            )

    # ──────────────────────────────────────────────────
    # Live tick — all strategies check signals
    # ──────────────────────────────────────────────────

    def _tick_live(self):
        """Execute signals on MT5 demo — all strategies in parallel."""
        import importlib.util
        import pandas as pd
        import numpy as np

        # Get M5 bars from MT5. Start at position 1 to EXCLUDE the currently
        # forming bar: signals must only be computed on closed bars, exactly
        # like the backtest (otherwise signals repaint mid-bar).
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 1, M5_BARS_LOOKBACK)
        if rates is None or len(rates) < 100:
            self.logger.warning("Could not fetch M5 bars from MT5")
            return

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume",
        })

        # Skip if same last-closed M5 bar as last tick (avoid duplicate signals)
        last_bar_time = df["time"].iloc[-1]
        if self._last_m5_bar_time == last_bar_time:
            return
        self._last_m5_bar_time = last_bar_time

        # Current market regime — strategies with proven losses in this
        # regime sit this scan out (regime_perf measured at validation).
        current_regime = None
        try:
            from engine.backtest import add_regime_indicators
            reg_df = add_regime_indicators(df.tail(300).copy())
            current_regime = str(reg_df["regime"].iloc[-1])
        except Exception:
            pass

        self.logger.info(
            f"Scanning {len(df)} closed M5 bars, "
            f"last={df['time'].iloc[-1]}, close={df['Close'].iloc[-1]:.2f}, "
            f"regime={current_regime}"
        )

        # Get account info for gatekeeper
        account = mt5.account_info()
        if not account:
            return

        # Pre-fetch open trades in one query (avoid per-strategy DB calls)
        open_trades_rows = self.db.fetchall(
            "SELECT strategy_id FROM live_trades WHERE status = 'open'"
        )
        open_trade_ids = {r["strategy_id"] for r in open_trades_rows}

        signals_found = 0
        for strat in self._active_strategies:
            strategy_id = strat["id"]

            # Check if strategy already has an open trade (from pre-fetched set)
            if strategy_id in open_trade_ids:
                continue

            # Regime bench: skip strategies that demonstrably LOSE in the
            # current regime (evidence required: PF < 1.0 over 10+ trades).
            # No data for this regime -> allowed (innocent until proven).
            if current_regime and current_regime in ("TREND", "RANGE", "HIGH_VOLATILITY"):
                try:
                    cfg = strat.get("best_config")
                    cfg = json.loads(cfg) if isinstance(cfg, str) else (cfg or {})
                    perf = (cfg.get("regime_perf") or {}).get(current_regime)
                    if perf and perf.get("trades", 0) >= 10 and perf.get("pf", 99) < 1.0:
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass

            # Load strategy module and generate signal
            module = self._load_strategy_module(strategy_id, strat.get("file_path"))
            if module is None:
                continue

            try:
                params = getattr(module, "PARAMS", {})
                result_df = module.generate_signals(df.copy(), params)
                if "signal" not in result_df.columns:
                    continue

                # Only act on a signal from the LAST closed bar. A signal from
                # an older bar is stale: the backtest enters at the open of the
                # bar right after the signal, so executing hours later at
                # market price would trade something never backtested.
                last_signal = int(result_df["signal"].iloc[-1])
                if last_signal == 0:
                    continue

                # Session guard: the backtest only enters inside the
                # strategy's session — live must do the same or it trades
                # hours that were never validated.
                sess_start = int(params.get("session_start", 7))
                sess_end = int(params.get("session_end", 21))
                bar_hour = int(df["time"].iloc[-1].hour)
                if not (sess_start <= bar_hour < sess_end):
                    continue

                signals_found += 1

                # Calculate order parameters
                direction = "buy" if last_signal == 1 else "sell"
                order_params = self._calculate_order_params(
                    direction, df, params, account
                )
                if order_params is None:
                    continue

                # ── GATEKEEPER CHECK ──
                allowed, reason = gate_check(
                    self.db,
                    strategy_id=strategy_id,
                    direction=direction,
                    lot=order_params["lot"],
                    sl_distance=order_params["sl_distance"],
                    account_balance=account.balance,
                    account_equity=account.equity,
                    free_margin=account.margin_free,
                )

                if not allowed:
                    self.logger.info(f"Signal {strategy_id} {direction} BLOCKED by gatekeeper: {reason}")
                    continue

                # ── PLACE ORDER ──
                self._place_order(strategy_id, direction, order_params)

            except Exception as exc:
                self.logger.error(
                    f"Signal gen failed for {strategy_id}: {exc}\n"
                    f"{traceback.format_exc()}"
                )

        if signals_found > 0:
            self.logger.info(f"SIGNALS FOUND: {signals_found} on this scan")
        else:
            self.logger.info(
                f"Scan complete: {len(self._active_strategies)} strategies, 0 signals"
            )

    def _calculate_order_params(self, direction: str, df, params: dict,
                                account) -> Optional[dict]:
        """Calculate SL, TP, lot size for an order."""
        import ta
        from core.config import DEFAULT_RISK_PCT, PIP_VALUE, MIN_LOT, MAX_LOT

        sl_atr = params.get("sl_atr", 1.5)
        tp_atr = params.get("tp_atr", 2.5)

        tick = mt5.symbol_info_tick(SYMBOL)
        if tick is None:
            return None

        # Spread guard: never enter when the instantaneous spread blows past
        # what the backtest assumed (rollover, pre-news, Friday close). The
        # ceiling adapts to the recent norm: max(2x median, $0.20).
        current_spread = tick.ask - tick.bid
        if "spread" in df.columns:
            typical = float(df["spread"].tail(500).median()) * 0.01
        else:
            typical = 0.10
        max_spread = max(2.0 * typical, 0.20)
        if current_spread > max_spread:
            self.logger.info(
                f"Entry blocked: spread {current_spread:.2f} > ceiling {max_spread:.2f}"
            )
            return None

        # ATR calculation
        atr_series = ta.volatility.average_true_range(
            df["High"], df["Low"], df["Close"], window=14
        )
        atr_val = atr_series.iloc[-1]
        if atr_val <= 0 or atr_val != atr_val:  # NaN check
            return None

        if direction == "buy":
            price = tick.ask
            sl = price - sl_atr * atr_val
            tp = price + tp_atr * atr_val
        else:
            price = tick.bid
            sl = price + sl_atr * atr_val
            tp = price - tp_atr * atr_val

        sl_distance = abs(price - sl)
        if sl_distance <= 0:
            return None

        # Dynamic lot sizing (confidence scaling is applied in _place_order)
        base_lot = (account.balance * DEFAULT_RISK_PCT) / (sl_distance * PIP_VALUE)

        # Get risk manager scaling (loss streak reduction)
        from agents.risk_manager import get_position_scaling
        risk_scaling = get_position_scaling(self.db)

        lot = base_lot * risk_scaling
        lot = max(MIN_LOT, min(MAX_LOT, round(lot, 2)))

        return {
            "price": price,
            "sl": sl,
            "tp": tp,
            "sl_distance": sl_distance,
            "lot": lot,
            "atr": atr_val,
            "order_type": mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL,
        }

    def _place_order(self, strategy_id: str, direction: str, params: dict):
        """Place a market order on MT5 and persist to live_trades."""
        # Apply confidence scaling to lot (never below broker minimum)
        from core.config import MIN_LOT
        conf_scale = get_confidence_scaling(self.db, strategy_id)
        lot = max(MIN_LOT, round(params["lot"] * conf_scale, 2))

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": lot,
            "type": params["order_type"],
            "price": params["price"],
            "sl": params["sl"],
            "tp": params["tp"],
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": f"PT_{strategy_id}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            now = datetime.now(timezone.utc).isoformat()

            # Measured slippage: |requested - filled|. Once 20+ samples
            # exist, backtests use the measured median instead of the
            # theoretical constant — the engine converges to THIS broker.
            fill_price = result.price or params["price"]
            slippage = abs(fill_price - params["price"])

            # Persist to live_trades table (entry at the real fill)
            self.db.execute(
                "INSERT INTO live_trades "
                "(strategy_id, ticket, direction, entry_price, sl, tp, lot, "
                "opened_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                (strategy_id, result.order, direction, fill_price,
                 params["sl"], params["tp"], lot, now),
            )

            self.emit_event(
                "trade_open",
                f"TRADE OPENED: {strategy_id} {direction.upper()} "
                f"@ {params['price']:.2f}, SL={params['sl']:.2f}, "
                f"TP={params['tp']:.2f}, lot={lot}",
                metadata={
                    "strategy_id": strategy_id,
                    "direction": direction,
                    "price": params["price"],
                    "fill_price": fill_price,
                    "slippage": slippage,
                    "sl": params["sl"],
                    "tp": params["tp"],
                    "lot": lot,
                    "ticket": result.order,
                    "confidence_scaling": conf_scale,
                },
            )
            self.logger.info(
                f"Trade opened: {strategy_id} {direction.upper()} "
                f"@ {params['price']:.2f} lot={lot} (conf={conf_scale:.0%})"
            )
        else:
            error = result.comment if result else "unknown"
            self.logger.error(f"Order failed for {strategy_id}: {error}")

    # ──────────────────────────────────────────────────
    # Dry-run tick (no MT5)
    # ──────────────────────────────────────────────────

    def _tick_dry_run(self):
        """Log what would happen without actually placing trades."""
        strat_count = len(self._active_strategies)
        if strat_count > 0:
            ids = [s["id"] for s in self._active_strategies[:5]]
            self.logger.debug(
                f"Dry-run: {strat_count} strategies ready, "
                f"MT5 not connected. Top: {ids}"
            )

    # ──────────────────────────────────────────────────
    # Strategy module loading (with caching)
    # ──────────────────────────────────────────────────

    def _load_strategy_module(self, strategy_id: str, file_path: str = None):
        """Load a strategy module with caching (reload every 100 ticks)."""
        import importlib.util
        from core.config import STRATEGIES_DIR, DATA_DIR

        # Check cache
        cached = self._module_cache.get(strategy_id)
        if cached:
            module, load_count = cached
            if load_count < 100:
                self._module_cache[strategy_id] = (module, load_count + 1)
                return module

        # Use provided file_path to avoid DB query
        candidate_paths = []
        if file_path:
            db_path = Path(file_path)
            candidate_paths.append(db_path)
            candidate_paths.append(DATA_DIR.parent / db_path)
        else:
            row = self.db.fetchone(
                "SELECT file_path FROM strategies WHERE id = ?", (strategy_id,)
            )
            if row and row["file_path"]:
                db_path = Path(row["file_path"])
                candidate_paths.append(db_path)
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
                    self._module_cache[strategy_id] = (module, 0)
                    return module
                except Exception:
                    return None
        return None
