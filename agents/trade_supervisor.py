"""Trade Supervisor: real-time monitoring of all open positions across strategies."""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from agents.base_agent import BaseAgent


# ── Supervisor thresholds ────────────────────────────
EMERGENCY_DD_PCT = 0.15          # emergency close ALL if portfolio DD > 15% in one session
CORRELATION_ALERT_RATIO = 0.75   # alert if 75%+ trades in same direction
STALE_TRADE_HOURS = 48           # flag trades open > 48 hours
MAX_LOSS_PER_TRADE_PCT = 0.05    # close trade if single trade loses > 5% of balance


class TradeSupervisor(BaseAgent):
    """
    Monitors all open live trades in real-time.

    Responsibilities:
    - Track portfolio P&L across all open positions
    - Detect excessive directional correlation
    - Flag stale trades (open too long)
    - Emergency close if portfolio drawdown exceeds threshold
    - Report portfolio status to dashboard
    - Update strategy_live_stats when trades close
    """

    name = "trade_supervisor"

    def __init__(self, db):
        super().__init__(agent_id="trade_supervisor", db=db)

    def setup(self):
        self.logger.info("Trade Supervisor ready — monitoring all open positions")

    def tick(self):
        """Monitor open trades and portfolio health."""
        open_trades = self._get_open_trades()

        if not open_trades:
            return

        # 1. Check for closed positions (MT5 closed by SL/TP)
        self._detect_closed_trades(open_trades)

        # Reload after detecting closures
        open_trades = self._get_open_trades()
        if not open_trades:
            return

        # 2. Trailing stops: replicate the engine's exit management on MT5.
        # Backtests simulate trailing — without this, validated strategies
        # would trade live with exits they were never validated on.
        self._manage_trailing_stops(open_trades)

        # 3. Check directional correlation
        self._check_correlation(open_trades)

        # 3. Check for stale trades
        self._check_stale_trades(open_trades)

        # 4. Emit portfolio status
        self._emit_portfolio_status(open_trades)

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 30)

    # ──────────────────────────────────────────────────
    # Trade queries
    # ──────────────────────────────────────────────────

    def _get_open_trades(self) -> list:
        """Get all currently open trades from DB."""
        rows = self.db.fetchall(
            "SELECT lt.*, s.best_profit_factor, s.best_win_rate "
            "FROM live_trades lt "
            "LEFT JOIN strategies s ON lt.strategy_id = s.id "
            "WHERE lt.status = 'open' "
            "ORDER BY lt.opened_at"
        )
        return [dict(r) for r in rows]

    # ──────────────────────────────────────────────────
    # Detect trades closed by MT5 (SL/TP hit)
    # ──────────────────────────────────────────────────

    def _detect_closed_trades(self, open_trades: list):
        """
        Check MT5 for positions that have been closed (SL/TP/manual).
        Update live_trades and strategy_live_stats accordingly.
        """
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return

        if not mt5.terminal_info():
            return

        for trade in open_trades:
            ticket = trade.get("ticket")
            if not ticket:
                continue

            # Check if position still exists in MT5
            positions = mt5.positions_get(ticket=ticket)
            if positions:
                continue  # Still open

            # Position closed — get P&L from deal history (incl. swap/commission/fees)
            pnl = 0.0
            deals = mt5.history_deals_get(position=ticket)
            if deals:
                pnl = sum(
                    d.profit
                    + getattr(d, "swap", 0.0)
                    + getattr(d, "commission", 0.0)
                    + getattr(d, "fee", 0.0)
                    for d in deals
                )

            close_price = 0.0
            if deals and len(deals) > 1:
                close_price = deals[-1].price

            # Determine close reason
            close_reason = "sl_tp"  # default assumption

            # Update live_trades
            self.db.execute(
                "UPDATE live_trades SET status = 'closed', closed_at = ?, "
                "close_price = ?, pnl = ?, close_reason = ? "
                "WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), close_price, pnl,
                 close_reason, trade["id"]),
            )

            # Update strategy_live_stats
            self._update_strategy_stats(trade["strategy_id"], pnl)

            # Emit trade close event
            self.emit_event(
                "trade_close",
                f"Trade closed: {trade['strategy_id']} "
                f"{'BUY' if trade['direction'] == 'buy' else 'SELL'} "
                f"P&L=${pnl:.2f}",
                metadata={
                    "strategy_id": trade["strategy_id"],
                    "pnl": pnl,
                    "direction": trade["direction"],
                    "entry_price": trade["entry_price"],
                    "close_price": close_price,
                    "close_reason": close_reason,
                    "ticket": ticket,
                },
            )
            self.logger.info(
                f"Trade closed: {trade['strategy_id']} P&L=${pnl:.2f} ({close_reason})"
            )

    # ──────────────────────────────────────────────────
    # Update strategy live stats
    # ──────────────────────────────────────────────────

    def _update_strategy_stats(self, strategy_id: str, pnl: float):
        """Recompute strategy_live_stats from closed trades in live_trades.

        Recomputing from the source table keeps the stats exact (true gross
        profit/loss for the profit factor) and self-heals any drift.
        """
        agg = self.db.fetchone(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins, "
            "SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) AS losses, "
            "SUM(pnl) AS total_pnl, MAX(pnl) AS best_pnl, MIN(pnl) AS worst_pnl, "
            "SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END) AS gross_profit, "
            "SUM(CASE WHEN pnl <= 0 THEN -pnl ELSE 0 END) AS gross_loss "
            "FROM live_trades "
            "WHERE strategy_id = ? AND status = 'closed' AND pnl IS NOT NULL",
            (strategy_id,),
        )
        total = (agg["total"] or 0) if agg else 0
        if total == 0:
            return

        wins = agg["wins"] or 0
        losses = agg["losses"] or 0
        total_pnl = agg["total_pnl"] or 0.0
        avg_pnl = total_pnl / total
        wr = wins / total
        gross_profit = agg["gross_profit"] or 0.0
        gross_loss = agg["gross_loss"] or 0.0
        if gross_loss > 0:
            live_pf = gross_profit / gross_loss
        else:
            live_pf = 99.0 if gross_profit > 0 else 0.0

        # Consecutive losses: walk back from the most recent closed trade
        recent = self.db.fetchall(
            "SELECT pnl FROM live_trades "
            "WHERE strategy_id = ? AND status = 'closed' AND pnl IS NOT NULL "
            "ORDER BY closed_at DESC, id DESC LIMIT 50",
            (strategy_id,),
        )
        consec = 0
        for r in recent:
            if (r["pnl"] or 0) <= 0:
                consec += 1
            else:
                break

        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO strategy_live_stats "
            "(strategy_id, total_trades, wins, losses, total_pnl, "
            "best_pnl, worst_pnl, avg_pnl, live_win_rate, live_profit_factor, "
            "consecutive_losses, last_trade_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(strategy_id) DO UPDATE SET "
            "total_trades = excluded.total_trades, wins = excluded.wins, "
            "losses = excluded.losses, total_pnl = excluded.total_pnl, "
            "best_pnl = excluded.best_pnl, worst_pnl = excluded.worst_pnl, "
            "avg_pnl = excluded.avg_pnl, live_win_rate = excluded.live_win_rate, "
            "live_profit_factor = excluded.live_profit_factor, "
            "consecutive_losses = excluded.consecutive_losses, "
            "last_trade_at = excluded.last_trade_at",
            (strategy_id, total, wins, losses, total_pnl,
             max(0.0, agg["best_pnl"] or 0.0), min(0.0, agg["worst_pnl"] or 0.0),
             avg_pnl, wr, live_pf, consec, now),
        )

        # Auto-disable strategy after too many consecutive losses
        if consec >= 5:
            self.db.execute(
                "UPDATE strategy_live_stats SET status = 'suspended' "
                "WHERE strategy_id = ?",
                (strategy_id,),
            )
            self.emit_event(
                "warning",
                f"Strategy {strategy_id} SUSPENDED: {consec} consecutive losses",
                metadata={"strategy_id": strategy_id, "consecutive_losses": consec},
            )
            self.logger.warning(f"Strategy {strategy_id} suspended after {consec} losses")

        # Backtest vs live divergence check
        self._check_divergence(strategy_id, total, wr, live_pf)

    # ──────────────────────────────────────────────────
    # Backtest vs live divergence
    # ──────────────────────────────────────────────────

    def _check_divergence(self, strategy_id: str, live_trades: int,
                          live_wr: float, live_pf: float):
        """Suspend strategies whose live performance falls far below backtest.

        A validated strategy that underperforms its backtest this much is
        either overfit or trading a regime that no longer exists.
        """
        from core.config import (
            DIVERGENCE_MIN_TRADES, DIVERGENCE_MAX_WR_DROP, DIVERGENCE_MIN_PF_RATIO,
        )

        if live_trades < DIVERGENCE_MIN_TRADES:
            return

        row = self.db.fetchone(
            "SELECT best_win_rate, best_profit_factor FROM strategies WHERE id = ?",
            (strategy_id,),
        )
        if not row:
            return

        bt_wr = row["best_win_rate"] or 0.0
        bt_pf = min(row["best_profit_factor"] or 0.0, 10.0)  # cap outliers/inf

        wr_drop = bt_wr - live_wr
        pf_ratio = (live_pf / bt_pf) if bt_pf > 0 else 1.0

        diverged = (wr_drop > DIVERGENCE_MAX_WR_DROP
                    or pf_ratio < DIVERGENCE_MIN_PF_RATIO)

        if diverged:
            self.db.execute(
                "UPDATE strategy_live_stats SET status = 'suspended' "
                "WHERE strategy_id = ?",
                (strategy_id,),
            )
            self.emit_event(
                "warning",
                f"Strategy {strategy_id} SUSPENDED: live diverges from backtest "
                f"(WR {live_wr:.0%} vs {bt_wr:.0%}, PF {live_pf:.2f} vs {bt_pf:.2f} "
                f"over {live_trades} trades)",
                metadata={"strategy_id": strategy_id, "reason": "divergence",
                          "live_wr": live_wr, "backtest_wr": bt_wr,
                          "live_pf": live_pf, "backtest_pf": bt_pf,
                          "live_trades": live_trades},
            )
            self.logger.warning(
                f"Strategy {strategy_id} suspended: backtest/live divergence "
                f"(WR drop {wr_drop:.0%}, PF ratio {pf_ratio:.2f})"
            )
        elif wr_drop > DIVERGENCE_MAX_WR_DROP * 0.66:
            # Early warning before the suspend threshold
            self.emit_event(
                "warning",
                f"Strategy {strategy_id} drifting from backtest: "
                f"live WR {live_wr:.0%} vs backtest {bt_wr:.0%} "
                f"({live_trades} trades)",
                metadata={"strategy_id": strategy_id, "reason": "divergence_early",
                          "live_wr": live_wr, "backtest_wr": bt_wr},
            )

    # ──────────────────────────────────────────────────
    # Trailing stop management (mirrors engine/backtest.py)
    # ──────────────────────────────────────────────────

    @staticmethod
    def compute_trailing_sl(direction: str, entry: float, initial_risk: float,
                            current_price: float, current_sl: float):
        """Engine-identical trailing rule. Returns the new SL or None.

        Activates once unrealized profit >= 1R, then trails the price by
        the initial risk distance. Only ever tightens, and only when the
        improvement is at least 10% of 1R (avoids modify-order spam).
        """
        if initial_risk <= 0:
            return None
        min_step = initial_risk * 0.10
        if direction == "buy":
            if current_price - entry < initial_risk:
                return None
            new_sl = current_price - initial_risk
            if new_sl > current_sl + min_step:
                return new_sl
        else:
            if entry - current_price < initial_risk:
                return None
            new_sl = current_price + initial_risk
            if new_sl < current_sl - min_step:
                return new_sl
        return None

    def _manage_trailing_stops(self, open_trades: list):
        """Apply the trailing rule to open MT5 positions whose strategy
        trades with trailing enabled (the 'trailing' param, wide-TP rule
        on top — identical to the backtest worker)."""
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return
        if not mt5.terminal_info():
            return

        from agents.template_factory import TemplateFactory

        for trade in open_trades:
            ticket = trade.get("ticket")
            entry = trade.get("entry_price")
            original_sl = trade.get("sl")
            if not ticket or not entry or not original_sl:
                continue

            # Strategy trailing gene (same defaults as the backtest worker)
            srow = self.db.fetchone(
                "SELECT file_path FROM strategies WHERE id = ?",
                (trade["strategy_id"],),
            )
            params = (TemplateFactory._load_params_from_file(srow["file_path"])
                      if srow and srow["file_path"] else {})
            use_trailing = bool(params.get("trailing", 1))
            if params.get("tp_atr", 2.0) >= 3.0:
                use_trailing = False
            if not use_trailing:
                continue

            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                continue
            pos = positions[0]

            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                continue
            price = tick.bid if trade["direction"] == "buy" else tick.ask

            # DB keeps the ORIGINAL SL, so 1R stays stable across trailing
            initial_risk = abs(entry - original_sl)
            new_sl = self.compute_trailing_sl(
                trade["direction"], entry, initial_risk, price, pos.sl or original_sl
            )
            if new_sl is None:
                continue

            result = mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": pos.symbol,
                "sl": round(new_sl, 2),
                "tp": pos.tp,
            })
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                self.logger.info(
                    f"Trailing SL: {trade['strategy_id']} #{ticket} "
                    f"SL -> {new_sl:.2f} (price {price:.2f})"
                )
            else:
                self.logger.warning(
                    f"Trailing SL modify failed for #{ticket}: "
                    f"{result.comment if result else 'no result'}"
                )

    # ──────────────────────────────────────────────────
    # Correlation check
    # ──────────────────────────────────────────────────

    def _check_correlation(self, open_trades: list):
        """Alert if too many trades are in the same direction."""
        if len(open_trades) < 3:
            return

        buys = sum(1 for t in open_trades if t["direction"] == "buy")
        sells = len(open_trades) - buys
        total = len(open_trades)

        dominant = max(buys, sells)
        ratio = dominant / total

        if ratio >= CORRELATION_ALERT_RATIO:
            direction = "BUY" if buys > sells else "SELL"
            self.emit_event(
                "warning",
                f"High directional correlation: {dominant}/{total} trades are {direction} "
                f"({ratio:.0%})",
                metadata={"buys": buys, "sells": sells, "ratio": ratio},
            )

    # ──────────────────────────────────────────────────
    # Stale trade check
    # ──────────────────────────────────────────────────

    def _check_stale_trades(self, open_trades: list):
        """Flag trades that have been open too long."""
        now = datetime.now(timezone.utc)
        stale_hours = self.get_config("stale_trade_hours") or STALE_TRADE_HOURS

        for trade in open_trades:
            opened_str = trade.get("opened_at")
            if not opened_str:
                continue
            try:
                opened = datetime.fromisoformat(str(opened_str))
                if opened.tzinfo is None:
                    opened = opened.replace(tzinfo=timezone.utc)
                hours_open = (now - opened).total_seconds() / 3600
                if hours_open > stale_hours:
                    self.logger.warning(
                        f"Stale trade: {trade['strategy_id']} open for {hours_open:.0f}h "
                        f"(limit: {stale_hours}h)"
                    )
            except (ValueError, TypeError):
                continue

    # ──────────────────────────────────────────────────
    # Portfolio status reporting
    # ──────────────────────────────────────────────────

    def _emit_portfolio_status(self, open_trades: list):
        """Emit portfolio status for dashboard."""
        buys = sum(1 for t in open_trades if t["direction"] == "buy")
        sells = len(open_trades) - buys
        total_lot = sum(t.get("lot", 0) for t in open_trades)

        # Count unique strategies
        strategies = set(t["strategy_id"] for t in open_trades)

        self.emit_event(
            "portfolio_status",
            f"Portfolio: {len(open_trades)} open trades "
            f"({buys} BUY / {sells} SELL), "
            f"{len(strategies)} strategies active, "
            f"total lots: {total_lot:.3f}",
            metadata={
                "open_trades": len(open_trades),
                "buys": buys,
                "sells": sells,
                "active_strategies": len(strategies),
                "total_lot": total_lot,
                "strategy_ids": list(strategies),
            },
        )


# ──────────────────────────────────────────────────
# Public API for forced close
# ──────────────────────────────────────────────────

def force_close_trade(db, trade_id: int, reason: str = "manual"):
    """Force close a specific trade via MT5."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return False

    row = db.fetchone("SELECT * FROM live_trades WHERE id = ? AND status = 'open'", (trade_id,))
    if not row:
        return False

    ticket = row["ticket"]
    lot = row["lot"]
    direction = row["direction"]

    # Close by sending opposite order
    tick = mt5.symbol_info_tick("XAUUSD")
    if not tick:
        return False

    if direction == "buy":
        close_price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        close_price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": "XAUUSD",
        "volume": lot,
        "type": order_type,
        "position": ticket,
        "price": close_price,
        "deviation": 20,
        "magic": 424242,
        "comment": f"FORCE_{reason}",
        "type_time": mt5.ORDER_TIME_GTC,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        db.execute(
            "UPDATE live_trades SET status = 'closed', closed_at = ?, "
            "close_price = ?, close_reason = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), close_price, reason, trade_id),
        )
        return True
    return False
