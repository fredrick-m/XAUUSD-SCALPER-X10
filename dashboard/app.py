"""
XAUUSD-SCALPER-X10 Dashboard — Flask + htmx real-time UI.
Reads from the shared SQLite database via the project's Database class.
Run: python -m dashboard.app  (or python dashboard/app.py)
"""

from pathlib import Path
from flask import Flask, jsonify, render_template

from core.config import DB_PATH
from core.db import Database

# ── App factory ──────────────────────────────────────────────────────────────

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)

# ── Lazy singleton DB ─────────────────────────────────────────────────────────

_db_instance = None


def _get_db() -> Database:
    """Return the shared Database singleton (lazy init). Monkeypatchable in tests."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(DB_PATH)
    return _db_instance


# ── Helper: sqlite3.Row → dict ────────────────────────────────────────────────

def _rows_to_list(rows) -> list:
    return [dict(r) for r in rows]


# ── Page routes ───────────────────────────────────────────────────────────────

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


# ── JSON API routes ───────────────────────────────────────────────────────────

@app.route("/api/agents")
def api_agents():
    """All agents from agent_registry."""
    db = _get_db()
    rows = db.fetchall("SELECT * FROM agent_registry ORDER BY name")
    return jsonify(_rows_to_list(rows))


@app.route("/api/strategies")
def api_strategies():
    """Top 100 strategies by best_profit_factor DESC."""
    db = _get_db()
    rows = db.fetchall(
        "SELECT * FROM strategies ORDER BY best_profit_factor DESC LIMIT 100"
    )
    return jsonify(_rows_to_list(rows))


@app.route("/api/tokens")
def api_tokens():
    """Token usage aggregations: total_cost, by_agent, by_model."""
    db = _get_db()

    total_row = db.fetchone("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM token_usage")
    total_cost = float(total_row["total"]) if total_row else 0.0

    by_agent_rows = db.fetchall(
        """SELECT agent_id,
                  COALESCE(SUM(cost_usd), 0)   AS cost,
                  COALESCE(SUM(tokens_in), 0)  AS tokens_in,
                  COALESCE(SUM(tokens_out), 0) AS tokens_out
           FROM token_usage
           GROUP BY agent_id
           ORDER BY cost DESC"""
    )

    by_model_rows = db.fetchall(
        """SELECT model,
                  COALESCE(SUM(cost_usd), 0)   AS cost,
                  COALESCE(SUM(tokens_in), 0)  AS tokens_in,
                  COALESCE(SUM(tokens_out), 0) AS tokens_out
           FROM token_usage
           GROUP BY model
           ORDER BY cost DESC"""
    )

    return jsonify({
        "total_cost": total_cost,
        "by_agent": _rows_to_list(by_agent_rows),
        "by_model": _rows_to_list(by_model_rows),
    })


@app.route("/api/events")
def api_events():
    """Last 100 events, newest first."""
    db = _get_db()
    rows = db.fetchall(
        "SELECT * FROM events ORDER BY timestamp DESC LIMIT 100"
    )
    return jsonify(_rows_to_list(rows))


@app.route("/api/summary")
def api_summary():
    """System KPIs."""
    db = _get_db()

    agents_running = (
        db.fetchone(
            "SELECT COUNT(*) AS c FROM agent_registry WHERE status = 'running'"
        )["c"]
        or 0
    )
    agents_total = (
        db.fetchone("SELECT COUNT(*) AS c FROM agent_registry")["c"] or 0
    )
    total_strategies = (
        db.fetchone("SELECT COUNT(*) AS c FROM strategies")["c"] or 0
    )
    validated_strategies = (
        db.fetchone(
            "SELECT COUNT(*) AS c FROM strategies WHERE status = 'validated'"
        )["c"]
        or 0
    )
    total_cost_row = db.fetchone(
        "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM token_usage"
    )
    total_cost_usd = float(total_cost_row["c"]) if total_cost_row else 0.0

    pending_tasks = (
        db.fetchone(
            "SELECT COUNT(*) AS c FROM task_queue WHERE status = 'pending'"
        )["c"]
        or 0
    )

    best_row = db.fetchone(
        """SELECT id, best_profit_factor, best_win_rate
           FROM strategies
           ORDER BY best_profit_factor DESC
           LIMIT 1"""
    )
    best_strategy = dict(best_row) if best_row else None

    return jsonify({
        "agents_running": agents_running,
        "agents_total": agents_total,
        "total_strategies": total_strategies,
        "validated_strategies": validated_strategies,
        "total_cost_usd": total_cost_usd,
        "pending_tasks": pending_tasks,
        "best_strategy": best_strategy,
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
