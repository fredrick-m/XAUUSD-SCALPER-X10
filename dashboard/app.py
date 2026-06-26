"""
XAUUSD-SCALPER-X10 Dashboard — Flask + SSE real-time UI.
Redesigned in CLAUDE × QUANT style.
"""
import json
import queue
import threading
import time
from pathlib import Path
from flask import Flask, jsonify, render_template, Response

from core.config import DB_PATH
from core.db import Database

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)

_db_instance = None


def _get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(DB_PATH)
    return _db_instance


def _rows_to_list(rows) -> list:
    return [dict(r) for r in rows]


# ── Page routes ──────────────────────────────────────────────────────────────

@app.route("/")
def overview():
    return render_template("overview.html")


@app.route("/strategies")
def strategies():
    return render_template("strategies.html")


@app.route("/tokens")
def tokens():
    return render_template("tokens.html")


@app.route("/events")
def events():
    return render_template("events.html")


# ── JSON API routes ──────────────────────────────────────────────────────────

@app.route("/api/agents")
def api_agents():
    db = _get_db()
    rows = db.fetchall("SELECT * FROM agent_registry ORDER BY name")
    return jsonify(_rows_to_list(rows))


@app.route("/api/strategies")
def api_strategies():
    db = _get_db()
    rows = db.fetchall(
        "SELECT * FROM strategies ORDER BY best_profit_factor DESC LIMIT 100"
    )
    return jsonify(_rows_to_list(rows))


@app.route("/api/tokens")
def api_tokens():
    db = _get_db()
    total_row = db.fetchone("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM token_usage")
    total_cost = float(total_row["total"]) if total_row else 0.0
    by_agent_rows = db.fetchall(
        "SELECT agent_id, COALESCE(SUM(cost_usd),0) AS cost, "
        "COALESCE(SUM(tokens_in),0) AS tokens_in, COALESCE(SUM(tokens_out),0) AS tokens_out "
        "FROM token_usage GROUP BY agent_id ORDER BY cost DESC"
    )
    by_model_rows = db.fetchall(
        "SELECT model, COALESCE(SUM(cost_usd),0) AS cost, "
        "COALESCE(SUM(tokens_in),0) AS tokens_in, COALESCE(SUM(tokens_out),0) AS tokens_out "
        "FROM token_usage GROUP BY model ORDER BY cost DESC"
    )
    return jsonify({
        "total_cost": total_cost,
        "by_agent": _rows_to_list(by_agent_rows),
        "by_model": _rows_to_list(by_model_rows),
    })


@app.route("/api/events")
def api_events():
    db = _get_db()
    rows = db.fetchall("SELECT * FROM events ORDER BY timestamp DESC LIMIT 100")
    return jsonify(_rows_to_list(rows))


@app.route("/api/summary")
def api_summary():
    db = _get_db()
    agents_running = db.fetchone(
        "SELECT COUNT(*) AS c FROM agent_registry WHERE status='running'"
    )["c"] or 0
    agents_total = db.fetchone("SELECT COUNT(*) AS c FROM agent_registry")["c"] or 0
    total_strategies = db.fetchone("SELECT COUNT(*) AS c FROM strategies")["c"] or 0
    validated = db.fetchone(
        "SELECT COUNT(*) AS c FROM strategies WHERE status='validated'"
    )["c"] or 0
    rejected = db.fetchone(
        "SELECT COUNT(*) AS c FROM strategies WHERE status='rejected'"
    )["c"] or 0
    fragile = db.fetchone(
        "SELECT COUNT(*) AS c FROM strategies WHERE status='fragile'"
    )["c"] or 0
    candidate = db.fetchone(
        "SELECT COUNT(*) AS c FROM strategies WHERE status='candidate'"
    )["c"] or 0
    bt_count = db.fetchone("SELECT COUNT(*) AS c FROM backtest_results")["c"] or 0
    total_cost_row = db.fetchone("SELECT COALESCE(SUM(cost_usd),0) AS c FROM token_usage")
    total_cost = float(total_cost_row["c"]) if total_cost_row else 0.0
    pending = db.fetchone(
        "SELECT COUNT(*) AS c FROM task_queue WHERE status='pending'"
    )["c"] or 0

    # Aggregate backtest stats (exclude infinite PF outliers)
    agg = db.fetchone(
        "SELECT AVG(win_rate) as avg_wr, AVG(CASE WHEN profit_factor < 100 THEN profit_factor END) as avg_pf, "
        "MAX(CASE WHEN profit_factor < 100 THEN profit_factor END) as max_pf, AVG(max_drawdown) as avg_dd, "
        "SUM(total_trades) as total_trades, COUNT(*) as run_count "
        "FROM backtest_results WHERE walk_forward=0"
    )

    best = db.fetchone(
        "SELECT s.id, s.best_profit_factor, s.best_win_rate, s.best_max_drawdown, "
        "s.best_x10_count, s.best_final_balance, s.best_config, s.family, s.status "
        "FROM strategies s "
        "JOIN backtest_results br ON br.strategy_id = s.id "
        "WHERE s.best_profit_factor < 100 AND br.total_trades >= 50 "
        "GROUP BY s.id "
        "ORDER BY s.best_final_balance DESC LIMIT 1"
    )

    # Risk state
    risk_row = db.fetchone("SELECT config FROM agent_registry WHERE id='risk_manager'")
    risk_state = {}
    if risk_row and risk_row["config"]:
        cfg = json.loads(risk_row["config"]) if isinstance(risk_row["config"], str) else risk_row["config"]
        risk_state = cfg.get("risk_state", {})

    # Production stats: ONLY validated strategies (what actually trades)
    prod_agg = db.fetchone(
        "SELECT AVG(br.win_rate) as avg_wr, "
        "AVG(CASE WHEN br.profit_factor < 100 THEN br.profit_factor END) as avg_pf, "
        "MAX(CASE WHEN br.profit_factor < 100 THEN br.profit_factor END) as max_pf, "
        "AVG(br.max_drawdown) as avg_dd, "
        "SUM(br.total_trades) as total_trades, COUNT(*) as run_count "
        "FROM backtest_results br JOIN strategies s ON br.strategy_id = s.id "
        "WHERE s.status = 'validated' AND br.walk_forward = 0 AND br.profit_factor < 100"
    )

    # Validated strategy details
    prod_strategies = db.fetchall(
        "SELECT s.id, s.best_profit_factor, s.best_win_rate, s.best_max_drawdown, "
        "s.best_final_balance, s.best_config, s.walk_forward_passed "
        "FROM strategies s WHERE s.status = 'validated' "
        "ORDER BY s.best_profit_factor DESC"
    )
    prod_list = []
    for ps in prod_strategies:
        d_ps = dict(ps)
        cfg = {}
        if d_ps.get("best_config"):
            try:
                cfg = json.loads(d_ps["best_config"]) if isinstance(d_ps["best_config"], str) else d_ps["best_config"]
            except (json.JSONDecodeError, TypeError):
                pass
        d_ps["mc_p_ruin"] = cfg.get("monte_carlo", {}).get("p_ruin")
        d_ps["risk_pct"] = cfg.get("risk_pct", 0.04)
        del d_ps["best_config"]
        prod_list.append(d_ps)

    # M5 strategies count (c/d/f/g series are M5)
    m5_total = db.fetchone(
        "SELECT COUNT(*) AS c FROM strategies WHERE "
        "(id LIKE 'c%' OR id LIKE 'd%' OR id LIKE 'f%' OR id LIKE 'g%')"
    )["c"] or 0
    m5_profitable = db.fetchone(
        "SELECT COUNT(*) AS c FROM strategies WHERE "
        "(id LIKE 'c%' OR id LIKE 'd%' OR id LIKE 'f%' OR id LIKE 'g%') "
        "AND best_profit_factor > 1.0"
    )["c"] or 0

    # M5-specific aggregates (the timeframe that matters)
    m5_agg = db.fetchone(
        "SELECT AVG(br.profit_factor) as avg_pf, AVG(br.win_rate) as avg_wr, "
        "MAX(CASE WHEN br.profit_factor < 100 THEN br.profit_factor END) as max_pf, "
        "COUNT(*) as bt_count "
        "FROM backtest_results br JOIN strategies s ON br.strategy_id = s.id "
        "WHERE (s.id LIKE 'c%' OR s.id LIKE 'd%' OR s.id LIKE 'f%' OR s.id LIKE 'g%') "
        "AND br.profit_factor < 100"
    )

    return jsonify({
        "agents_running": agents_running,
        "agents_total": agents_total,
        "total_strategies": total_strategies,
        "validated": validated,
        "rejected": rejected,
        "fragile": fragile,
        "candidate": candidate,
        "backtest_runs": bt_count,
        "total_cost_usd": total_cost,
        "pending_tasks": pending,
        "avg_wr": (agg["avg_wr"] or 0) if agg else 0,
        "avg_pf": (agg["avg_pf"] or 0) if agg else 0,
        "max_pf": (agg["max_pf"] or 0) if agg else 0,
        "avg_dd": (agg["avg_dd"] or 0) if agg else 0,
        "total_trades": int(agg["total_trades"] or 0) if agg else 0,
        "best_strategy": dict(best) if best else None,
        "risk_state": risk_state,
        "m5_strategies": m5_total,
        "m5_profitable": m5_profitable,
        "m5_avg_pf": (m5_agg["avg_pf"] or 0) if m5_agg else 0,
        "m5_max_pf": (m5_agg["max_pf"] or 0) if m5_agg else 0,
        "m5_avg_wr": (m5_agg["avg_wr"] or 0) if m5_agg else 0,
        "m5_bt_count": (m5_agg["bt_count"] or 0) if m5_agg else 0,
        # Production stats (validated only)
        "prod_avg_wr": (prod_agg["avg_wr"] or 0) if prod_agg else 0,
        "prod_avg_pf": (prod_agg["avg_pf"] or 0) if prod_agg else 0,
        "prod_max_pf": (prod_agg["max_pf"] or 0) if prod_agg else 0,
        "prod_avg_dd": (prod_agg["avg_dd"] or 0) if prod_agg else 0,
        "prod_total_trades": int(prod_agg["total_trades"] or 0) if prod_agg else 0,
        "prod_strategies": prod_list,
    })


@app.route("/api/pipeline")
def api_pipeline():
    """Execution pipeline counts per stage."""
    db = _get_db()
    candidate = db.fetchone("SELECT COUNT(*) AS c FROM strategies WHERE status='candidate'")["c"] or 0
    validated = db.fetchone("SELECT COUNT(*) AS c FROM strategies WHERE status='validated'")["c"] or 0
    fragile = db.fetchone("SELECT COUNT(*) AS c FROM strategies WHERE status='fragile'")["c"] or 0
    backtested = db.fetchone("SELECT COUNT(DISTINCT strategy_id) AS c FROM backtest_results")["c"] or 0
    wf_passed = db.fetchone("SELECT COUNT(*) AS c FROM strategies WHERE walk_forward_passed=1")["c"] or 0
    regime_passed = db.fetchone("SELECT COUNT(*) AS c FROM strategies WHERE regimes_passed>=3")["c"] or 0

    # MC tested
    mc_tested = 0
    sens_tested = 0
    mtf_tested = 0
    rows = db.fetchall("SELECT best_config FROM strategies WHERE status='validated'")
    for r in rows:
        if r["best_config"]:
            cfg = json.loads(r["best_config"]) if isinstance(r["best_config"], str) else r["best_config"]
            if cfg.get("monte_carlo_tested"): mc_tested += 1
            if cfg.get("sensitivity_tested"): sens_tested += 1
            if cfg.get("mtf_tested"): mtf_tested += 1

    return jsonify({
        "candidate": candidate,
        "backtested": backtested,
        "wf_passed": wf_passed,
        "validated": validated,
        "regime_passed": regime_passed,
        "mc_tested": mc_tested,
        "sensitivity_tested": sens_tested,
        "mtf_tested": mtf_tested,
        "fragile": fragile,
    })


@app.route("/api/top")
def api_top():
    """Top 20 strategies with full details."""
    db = _get_db()
    rows = db.fetchall(
        "SELECT id, family, status, best_win_rate, best_profit_factor, "
        "best_max_drawdown, best_x10_count, best_final_balance, "
        "regimes_passed, walk_forward_passed, best_config, generation, created_by "
        "FROM strategies WHERE best_profit_factor > 0 "
        "ORDER BY best_profit_factor DESC LIMIT 20"
    )
    result = []
    for r in rows:
        d = dict(r)
        cfg = {}
        if d.get("best_config"):
            try:
                cfg = json.loads(d["best_config"]) if isinstance(d["best_config"], str) else d["best_config"]
            except (json.JSONDecodeError, TypeError):
                pass
        d["mc_p_ruin"] = cfg.get("monte_carlo", {}).get("p_ruin")
        d["mc_p_x10"] = cfg.get("monte_carlo", {}).get("p_x10")
        d["robustness"] = cfg.get("sensitivity", {}).get("robustness_score")
        d["best_htf"] = cfg.get("multi_timeframe", {}).get("best_htf")
        del d["best_config"]
        result.append(d)
    return jsonify(result)


@app.route("/api/feed")
def api_feed():
    """Last 30 events for live feed, excluding risk_status spam."""
    db = _get_db()
    rows = db.fetchall(
        "SELECT agent_id, event_type, event_message, timestamp FROM events "
        "WHERE event_type != 'risk_status' "
        "ORDER BY id DESC LIMIT 30"
    )
    return jsonify(_rows_to_list(rows))


@app.route("/api/pf-distribution")
def api_pf_distribution():
    """Profit factor distribution for histogram."""
    db = _get_db()
    rows = db.fetchall(
        "SELECT best_profit_factor FROM strategies "
        "WHERE best_profit_factor > 0 ORDER BY best_profit_factor"
    )
    values = [r["best_profit_factor"] for r in rows]
    # Build histogram buckets
    buckets = {}
    for v in values:
        b = round(v * 10) / 10  # bucket by 0.1
        buckets[b] = buckets.get(b, 0) + 1
    labels = sorted(buckets.keys())
    counts = [buckets[l] for l in labels]
    return jsonify({"labels": labels, "counts": counts, "total": len(values)})


@app.route("/api/trades")
def api_trades():
    """Live MT5 positions and recent trade history."""
    db = _get_db()
    result = {"positions": [], "history": [], "account": None, "mt5_connected": False}

    # Try to get live MT5 positions
    try:
        import MetaTrader5 as mt5
        # Don't call shutdown — keep MT5 alive for paper_trade agent
        if not mt5.symbol_info("XAUUSD"):
            mt5.initialize()

        account = mt5.account_info()
        if account:
            result["mt5_connected"] = True
            result["account"] = {
                "login": account.login,
                "balance": account.balance,
                "equity": account.equity,
                "margin_free": account.margin_free,
                "profit": account.profit,
            }

        positions = mt5.positions_get(symbol="XAUUSD")
        if positions:
            for p in positions:
                result["positions"].append({
                    "ticket": p.ticket,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "price_current": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "comment": p.comment,
                    "time": str(p.time),
                    "magic": p.magic,
                })
    except ImportError:
        pass
    except Exception:
        pass

    # Recent trade events from DB
    rows = db.fetchall(
        "SELECT event_message, metadata, timestamp FROM events "
        "WHERE agent_id = 'paper_trade' AND event_type IN ('trade_open', 'trade_close') "
        "ORDER BY id DESC LIMIT 20"
    )
    result["history"] = _rows_to_list(rows)

    return jsonify(result)


@app.route("/api/timing")
def api_timing():
    """System activity timing: backtests/events over time, throughput rates."""
    db = _get_db()
    import datetime as _dt

    now_str = _dt.datetime.now().isoformat()

    # ── Backtest throughput ──
    bt_total = db.fetchone("SELECT COUNT(*) AS c FROM backtest_results")["c"] or 0

    # First and last backtest timestamps
    first_bt = db.fetchone("SELECT MIN(run_at) AS t FROM backtest_results")
    last_bt = db.fetchone("SELECT MAX(run_at) AS t FROM backtest_results")

    bt_first_ts = first_bt["t"] if first_bt else None
    bt_last_ts = last_bt["t"] if last_bt else None

    # Time windows
    windows = {}
    for label, minutes in [("1h", 60), ("6h", 360), ("24h", 1440), ("7d", 10080)]:
        cutoff = (_dt.datetime.now() - _dt.timedelta(minutes=minutes)).isoformat()
        row = db.fetchone(
            "SELECT COUNT(*) AS c FROM backtest_results WHERE run_at >= ?", (cutoff,)
        )
        windows[label] = row["c"] if row else 0

    # ── Event throughput ──
    ev_total = db.fetchone("SELECT COUNT(*) AS c FROM events")["c"] or 0
    ev_windows = {}
    for label, minutes in [("1h", 60), ("6h", 360), ("24h", 1440), ("7d", 10080)]:
        cutoff = (_dt.datetime.now() - _dt.timedelta(minutes=minutes)).isoformat()
        row = db.fetchone(
            "SELECT COUNT(*) AS c FROM events WHERE timestamp >= ?", (cutoff,)
        )
        ev_windows[label] = row["c"] if row else 0

    # ── Strategy creation throughput ──
    strat_total = db.fetchone("SELECT COUNT(*) AS c FROM strategies")["c"] or 0
    strat_windows = {}
    for label, minutes in [("1h", 60), ("6h", 360), ("24h", 1440), ("7d", 10080)]:
        cutoff = (_dt.datetime.now() - _dt.timedelta(minutes=minutes)).isoformat()
        row = db.fetchone(
            "SELECT COUNT(*) AS c FROM strategies WHERE created_at >= ?", (cutoff,)
        )
        strat_windows[label] = row["c"] if row else 0

    # ── Elapsed since first activity ──
    elapsed_str = ""
    rate_per_hour = 0
    if bt_first_ts:
        try:
            first = _dt.datetime.fromisoformat(str(bt_first_ts).replace("Z", ""))
            elapsed = _dt.datetime.now() - first
            days = elapsed.days
            hours = elapsed.seconds // 3600
            mins = (elapsed.seconds % 3600) // 60
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            if mins > 0:
                parts.append(f"{mins}m")
            elapsed_str = " ".join(parts) if parts else "< 1m"

            total_hours = elapsed.total_seconds() / 3600
            if total_hours > 0:
                rate_per_hour = round(bt_total / total_hours, 1)
        except (ValueError, TypeError):
            elapsed_str = "?"

    # ── Backtests per hour (last 24h, bucketed) ──
    hourly_buckets = []
    for h in range(24, 0, -1):
        start = (_dt.datetime.now() - _dt.timedelta(hours=h)).isoformat()
        end = (_dt.datetime.now() - _dt.timedelta(hours=h - 1)).isoformat()
        row = db.fetchone(
            "SELECT COUNT(*) AS c FROM backtest_results WHERE run_at >= ? AND run_at < ?",
            (start, end),
        )
        hourly_buckets.append({
            "hour": h,
            "label": f"-{h}h",
            "count": row["c"] if row else 0,
        })

    return jsonify({
        "backtests_total": bt_total,
        "backtests_1h": windows.get("1h", 0),
        "backtests_6h": windows.get("6h", 0),
        "backtests_24h": windows.get("24h", 0),
        "backtests_7d": windows.get("7d", 0),
        "events_total": ev_total,
        "events_1h": ev_windows.get("1h", 0),
        "events_6h": ev_windows.get("6h", 0),
        "events_24h": ev_windows.get("24h", 0),
        "strategies_total": strat_total,
        "strategies_1h": strat_windows.get("1h", 0),
        "strategies_6h": strat_windows.get("6h", 0),
        "strategies_24h": strat_windows.get("24h", 0),
        "strategies_7d": strat_windows.get("7d", 0),
        "elapsed": elapsed_str,
        "rate_per_hour": rate_per_hour,
        "first_activity": bt_first_ts,
        "last_activity": bt_last_ts,
        "hourly_buckets": hourly_buckets,
    })


# ── SSE: Server-Sent Events for real-time push ─────────────────────────────

_sse_clients = []
_sse_lock = threading.Lock()
_last_event_id = 0
_last_bt_count = 0
_last_strat_count = 0


def _sse_watcher():
    """Background thread: polls DB for changes and pushes SSE to all clients."""
    global _last_event_id, _last_bt_count, _last_strat_count
    db = Database(DB_PATH)

    # Initialize counters
    row = db.fetchone("SELECT MAX(id) AS m FROM events")
    _last_event_id = (row["m"] or 0) if row else 0
    row = db.fetchone("SELECT COUNT(*) AS c FROM backtest_results")
    _last_bt_count = (row["c"] or 0) if row else 0
    row = db.fetchone("SELECT COUNT(*) AS c FROM strategies")
    _last_strat_count = (row["c"] or 0) if row else 0

    while True:
        try:
            # Check for new events
            rows = db.fetchall(
                "SELECT id, agent_id, event_type, event_message, timestamp "
                "FROM events WHERE id > ? ORDER BY id ASC LIMIT 20",
                (_last_event_id,),
            )
            for r in rows:
                _last_event_id = r["id"]
                payload = json.dumps({
                    "type": "event",
                    "agent_id": r["agent_id"],
                    "event_type": r["event_type"],
                    "message": r["event_message"],
                    "timestamp": r["timestamp"],
                })
                _broadcast_sse(payload)

            # Check for new backtests
            row = db.fetchone("SELECT COUNT(*) AS c FROM backtest_results")
            bt_count = (row["c"] or 0) if row else 0
            if bt_count != _last_bt_count:
                diff = bt_count - _last_bt_count
                _last_bt_count = bt_count
                _broadcast_sse(json.dumps({
                    "type": "backtest",
                    "total": bt_count,
                    "new": diff,
                }))

            # Check for new/changed strategies
            row = db.fetchone("SELECT COUNT(*) AS c FROM strategies")
            st_count = (row["c"] or 0) if row else 0
            if st_count != _last_strat_count:
                _last_strat_count = st_count
                _broadcast_sse(json.dumps({
                    "type": "strategy",
                    "total": st_count,
                }))

            # Heartbeat every cycle so client knows connection is alive
            _broadcast_sse(json.dumps({"type": "heartbeat", "t": int(time.time())}))

        except Exception:
            pass

        time.sleep(2)  # Poll DB every 2 seconds


def _broadcast_sse(data: str):
    """Send data to all connected SSE clients."""
    dead = []
    with _sse_lock:
        for q in _sse_clients:
            try:
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


@app.route("/api/stream")
def api_stream():
    """SSE endpoint: real-time event stream."""
    def generate():
        q = queue.Queue(maxsize=100)
        with _sse_lock:
            _sse_clients.append(q)
        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    # Send keepalive comment to prevent timeout
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# Start SSE watcher thread
_watcher_thread = threading.Thread(target=_sse_watcher, daemon=True)
_watcher_thread.start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False, threaded=True)
