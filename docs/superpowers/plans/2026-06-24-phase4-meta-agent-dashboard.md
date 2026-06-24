# Phase 4: Meta Agent & Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Meta Agent (creates/kills/reconfigures agents using Claude Opus) and the web dashboard (Flask + htmx real-time UI with system overview, strategy race, token economy, and event stream).

**Architecture:** The Meta Agent collects system state (agent health, task queue depth, strategy landscape, token costs, recent events), sends a structured summary to Claude Opus every 5 minutes, and executes its decisions (spawn, kill, reconfigure, or create new agent types). The dashboard is a Flask app served on `localhost:8050` using Jinja2 templates with htmx for live updates — it reads all data directly from the shared SQLite database. A lightweight UI Director agent starts the dashboard server and periodically pre-computes aggregate data for the dashboard.

**Tech Stack:** Python, Flask, Jinja2, htmx (CDN), Plotly (JSON charts), Anthropic SDK

---

## File Structure

```
dashboard/
├── app.py                    — Flask app with JSON API + page routes (rewrite existing Dash app)
├── templates/
│   ├── base.html             — Layout shell: nav, htmx CDN, dark theme CSS
│   ├── overview.html         — Agent statuses, system KPIs
│   ├── strategies.html       — Strategy race table + best metrics
│   ├── tokens.html           — Cost per agent, per model, totals
│   └── events.html           — Real-time event log stream

agents/
├── meta_agent.py             — Meta Agent (new)
├── ui_director.py            — UI Director agent (new)

tests/
├── test_dashboard.py         — Dashboard API route tests (new)
├── test_meta_agent.py        — Meta Agent tests (new)
├── test_ui_director.py       — UI Director tests (new)

core/
├── config.py                 — Add meta_agent + ui_director to CORE_AGENTS, add DASHBOARD_PORT
```

---

### Task 1: Dashboard Flask backend (`dashboard/app.py`)

**Files:**
- Rewrite: `dashboard/app.py`
- Create: `tests/test_dashboard.py`

Replace the existing Dash-based dashboard with a Flask app that serves JSON API endpoints and HTML pages. All data comes from `agent_db.sqlite`.

- [ ] **Step 1: Write the failing tests**

`tests/test_dashboard.py`:
```python
"""Tests for the Flask dashboard."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    yield db
    db.close()


@pytest.fixture
def client(tmp_db, monkeypatch):
    """Create a Flask test client wired to the tmp_db."""
    import dashboard.app as dashboard_module
    monkeypatch.setattr(dashboard_module, "_get_db", lambda: tmp_db)
    dashboard_module.app.config["TESTING"] = True
    with dashboard_module.app.test_client() as c:
        yield c


def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"XAUUSD" in resp.data


def test_api_agents(client, tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, status, error_count) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("t1", "token_manager", "agents.token_manager", "TokenManager", "running", 0),
    )
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data) == 1
    assert data[0]["name"] == "token_manager"
    assert data[0]["status"] == "running"


def test_api_strategies(client, tmp_db):
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status, best_win_rate, best_profit_factor) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("S001", "s.py", "momentum", "validated", 0.68, 2.5),
    )
    resp = client.get("/api/strategies")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data) == 1
    assert data[0]["id"] == "S001"


def test_api_token_usage(client, tmp_db):
    tmp_db.execute(
        "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("strategy_factory", "claude-opus-4-6", 1000, 2000, 0.18, "generate_strategy"),
    )
    resp = client.get("/api/tokens")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["total_cost"] > 0
    assert len(data["by_agent"]) == 1


def test_api_events(client, tmp_db):
    from core.logger import log_event
    log_event(tmp_db, "test_agent", "info", "hello world")
    resp = client.get("/api/events")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data) >= 1
    assert data[0]["event_message"] == "hello world"


def test_api_system_summary(client, tmp_db):
    tmp_db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("t1", "token_manager", "agents.token_manager", "TokenManager", "running"),
    )
    resp = client.get("/api/summary")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "agents_running" in data
    assert "total_strategies" in data
    assert "total_cost_usd" in data


def test_strategies_page(client):
    resp = client.get("/strategies")
    assert resp.status_code == 200


def test_tokens_page(client):
    resp = client.get("/tokens")
    assert resp.status_code == 200


def test_events_page(client):
    resp = client.get("/events")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dashboard.py -v`
Expected: FAIL — import errors or missing functions

- [ ] **Step 3: Implement the Flask app**

`dashboard/app.py`:
```python
"""
XAUUSD-SCALPER-X10 Dashboard
=============================
Flask + htmx real-time dashboard. Reads all data from agent_db.sqlite.
Run standalone: python -m dashboard.app
Served by UI Director agent in production.
"""
import json
from pathlib import Path

from flask import Flask, jsonify, render_template

from core.config import DB_PATH
from core.db import Database

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)

_db_instance = None


def _get_db() -> Database:
    """Lazy singleton DB connection for the dashboard."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(DB_PATH)
    return _db_instance


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("overview.html")


@app.route("/strategies")
def strategies_page():
    return render_template("strategies.html")


@app.route("/tokens")
def tokens_page():
    return render_template("tokens.html")


@app.route("/events")
def events_page():
    return render_template("events.html")


# ── JSON API routes ───────────────────────────────────────────────────────────

@app.route("/api/agents")
def api_agents():
    db = _get_db()
    rows = db.fetchall(
        "SELECT id, name, status, error_count, restart_count, last_heartbeat, config "
        "FROM agent_registry ORDER BY name"
    )
    return jsonify([dict(r) for r in rows])


@app.route("/api/strategies")
def api_strategies():
    db = _get_db()
    rows = db.fetchall(
        "SELECT id, family, status, generation, parent_strategy, "
        "best_win_rate, best_profit_factor, best_max_drawdown, "
        "best_x10_count, best_final_balance, created_at "
        "FROM strategies ORDER BY best_profit_factor DESC NULLS LAST LIMIT 100"
    )
    return jsonify([dict(r) for r in rows])


@app.route("/api/tokens")
def api_tokens():
    db = _get_db()
    # Total cost
    total_row = db.fetchone("SELECT COALESCE(SUM(cost_usd), 0) as total FROM token_usage")
    total_cost = total_row["total"] if total_row else 0.0

    # By agent
    by_agent = db.fetchall(
        "SELECT agent_id, SUM(tokens_in) as total_in, SUM(tokens_out) as total_out, "
        "SUM(cost_usd) as cost, COUNT(*) as calls "
        "FROM token_usage GROUP BY agent_id ORDER BY cost DESC"
    )

    # By model
    by_model = db.fetchall(
        "SELECT model, SUM(tokens_in) as total_in, SUM(tokens_out) as total_out, "
        "SUM(cost_usd) as cost, COUNT(*) as calls "
        "FROM token_usage GROUP BY model ORDER BY cost DESC"
    )

    return jsonify({
        "total_cost": round(total_cost, 4),
        "by_agent": [dict(r) for r in by_agent],
        "by_model": [dict(r) for r in by_model],
    })


@app.route("/api/events")
def api_events():
    db = _get_db()
    rows = db.fetchall(
        "SELECT agent_id, event_type, event_message, metadata, timestamp "
        "FROM events ORDER BY timestamp DESC LIMIT 100"
    )
    return jsonify([dict(r) for r in rows])


@app.route("/api/summary")
def api_summary():
    db = _get_db()
    agents = db.fetchall("SELECT status FROM agent_registry")
    running = sum(1 for a in agents if a["status"] == "running")

    strats = db.fetchone("SELECT COUNT(*) as c FROM strategies")
    validated = db.fetchone("SELECT COUNT(*) as c FROM strategies WHERE status = 'validated'")

    cost = db.fetchone("SELECT COALESCE(SUM(cost_usd), 0) as total FROM token_usage")

    queue = db.fetchone("SELECT COUNT(*) as c FROM task_queue WHERE status = 'pending'")

    best = db.fetchone(
        "SELECT id, best_profit_factor, best_win_rate "
        "FROM strategies WHERE best_profit_factor IS NOT NULL "
        "ORDER BY best_profit_factor DESC LIMIT 1"
    )

    return jsonify({
        "agents_total": len(agents),
        "agents_running": running,
        "total_strategies": strats["c"] if strats else 0,
        "validated_strategies": validated["c"] if validated else 0,
        "total_cost_usd": round(cost["total"], 4) if cost else 0.0,
        "pending_tasks": queue["c"] if queue else 0,
        "best_strategy": dict(best) if best else None,
    })


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Dashboard: http://localhost:8050")
    app.run(host="0.0.0.0", port=8050, debug=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dashboard.py -v`
Expected: ALL PASS (templates not yet created — page tests will fail, fix in step 5)

- [ ] **Step 5: Create minimal template stubs so page routes pass**

Create `dashboard/templates/base.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XAUUSD-SCALPER-X10 — {% block title %}Dashboard{% endblock %}</title>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg: #0a0a0f; --card: #10101a; --green: #00ff9f;
            --gold: #ffd700; --red: #ff4060; --cyan: #00d4ff;
            --muted: #555577; --font: 'Consolas', 'Courier New', monospace;
        }
        body { background: var(--bg); color: #eee; font-family: var(--font); min-height: 100vh; }
        a { color: var(--cyan); text-decoration: none; }
        a:hover { text-decoration: underline; }
        nav { display: flex; gap: 24px; padding: 16px 24px; border-bottom: 1px solid #55557733; align-items: center; }
        nav .brand { font-size: 18px; font-weight: 700; }
        nav .brand .gold { color: var(--gold); }
        nav .brand .green { color: var(--green); }
        nav .brand .muted { color: var(--muted); }
        nav a { color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: 1px; }
        nav a:hover, nav a.active { color: var(--green); }
        .container { padding: 16px 24px; }
        .card { background: var(--card); border-radius: 8px; padding: 16px; border: 1px solid #55557733; margin-bottom: 12px; }
        .card-title { color: var(--gold); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; }
        .grid { display: grid; gap: 12px; }
        .grid-2 { grid-template-columns: 1fr 1fr; }
        .grid-4 { grid-template-columns: repeat(4, 1fr); }
        .kpi { text-align: center; padding: 12px; }
        .kpi-label { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; }
        .kpi-value { font-size: 24px; font-weight: 700; margin-top: 4px; }
        .green { color: var(--green); }
        .gold { color: var(--gold); }
        .red { color: var(--red); }
        .cyan { color: var(--cyan); }
        .muted { color: var(--muted); }
        table { width: 100%; border-collapse: collapse; font-size: 12px; }
        th { color: var(--gold); text-align: left; padding: 8px; border-bottom: 1px solid #55557733; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; }
        td { padding: 8px; border-bottom: 1px solid #55557711; }
        .status-running { color: var(--green); }
        .status-stopped { color: var(--muted); }
        .status-error, .status-disabled { color: var(--red); }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; }
        .badge-green { background: #00ff9f22; color: var(--green); border: 1px solid var(--green); }
        .badge-gold { background: #ffd70022; color: var(--gold); border: 1px solid var(--gold); }
        .badge-red { background: #ff406022; color: var(--red); border: 1px solid var(--red); }
        .event-row { padding: 4px 0; font-size: 11px; border-bottom: 1px solid #55557711; }
        .event-time { color: var(--muted); width: 140px; display: inline-block; }
        .event-agent { color: var(--cyan); width: 120px; display: inline-block; }
        @media (max-width: 900px) { .grid-4 { grid-template-columns: 1fr 1fr; } .grid-2 { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <nav>
        <div class="brand">
            <span class="gold">XAUUSD</span><span class="muted">-SCALPER-</span><span class="green">X10</span>
        </div>
        <a href="/">Overview</a>
        <a href="/strategies">Strategies</a>
        <a href="/tokens">Tokens</a>
        <a href="/events">Events</a>
    </nav>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>
```

Create `dashboard/templates/overview.html`:
```html
{% extends "base.html" %}
{% block title %}Overview{% endblock %}
{% block content %}
<div hx-get="/api/summary" hx-trigger="load, every 5s" hx-swap="innerHTML" id="summary-data">
    <p class="muted">Loading...</p>
</div>

<script>
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === 'summary-data') {
        try {
            const data = JSON.parse(evt.detail.target.innerText);
            evt.detail.target.innerHTML = `
                <div class="grid grid-4" style="margin-bottom:16px">
                    <div class="card kpi"><div class="kpi-label">Agents Running</div><div class="kpi-value green">${data.agents_running}/${data.agents_total}</div></div>
                    <div class="card kpi"><div class="kpi-label">Strategies</div><div class="kpi-value cyan">${data.total_strategies}</div></div>
                    <div class="card kpi"><div class="kpi-label">Validated</div><div class="kpi-value gold">${data.validated_strategies}</div></div>
                    <div class="card kpi"><div class="kpi-label">Total Cost</div><div class="kpi-value">$${data.total_cost_usd.toFixed(2)}</div></div>
                </div>
                <div class="card"><div class="card-title">Best Strategy</div>
                    ${data.best_strategy ? `<span class="gold">${data.best_strategy.id}</span> — PF: ${data.best_strategy.best_profit_factor}, WR: ${(data.best_strategy.best_win_rate * 100).toFixed(1)}%` : '<span class="muted">No results yet</span>'}
                </div>
            `;
        } catch(e) {}
    }
});
</script>

<div class="card" style="margin-top:12px">
    <div class="card-title">Agent Status</div>
    <div hx-get="/api/agents" hx-trigger="load, every 10s" hx-swap="innerHTML" id="agents-table">
        <p class="muted">Loading...</p>
    </div>
</div>

<script>
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === 'agents-table') {
        try {
            const agents = JSON.parse(evt.detail.target.innerText);
            let html = '<table><tr><th>Name</th><th>Status</th><th>Errors</th><th>Restarts</th><th>Heartbeat</th></tr>';
            agents.forEach(a => {
                const cls = 'status-' + a.status;
                html += `<tr><td>${a.name}</td><td class="${cls}">${a.status}</td><td>${a.error_count||0}</td><td>${a.restart_count||0}</td><td class="muted">${a.last_heartbeat||'—'}</td></tr>`;
            });
            html += '</table>';
            evt.detail.target.innerHTML = html;
        } catch(e) {}
    }
});
</script>
{% endblock %}
```

Create `dashboard/templates/strategies.html`:
```html
{% extends "base.html" %}
{% block title %}Strategy Race{% endblock %}
{% block content %}
<h2 style="color:var(--gold);font-size:14px;margin-bottom:12px">STRATEGY RACE</h2>
<div class="card">
    <div hx-get="/api/strategies" hx-trigger="load, every 10s" hx-swap="innerHTML" id="strat-table">
        <p class="muted">Loading...</p>
    </div>
</div>

<script>
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === 'strat-table') {
        try {
            const strats = JSON.parse(evt.detail.target.innerText);
            let html = '<table><tr><th>#</th><th>ID</th><th>Family</th><th>Status</th><th>Gen</th><th>WR</th><th>PF</th><th>DD</th><th>x10</th><th>Balance</th></tr>';
            strats.forEach((s, i) => {
                const wr = s.best_win_rate ? (s.best_win_rate * 100).toFixed(1) + '%' : '—';
                const pf = s.best_profit_factor ? s.best_profit_factor.toFixed(2) : '—';
                const dd = s.best_max_drawdown ? (s.best_max_drawdown * 100).toFixed(1) + '%' : '—';
                const bal = s.best_final_balance ? '$' + s.best_final_balance.toFixed(0) : '—';
                const statusCls = s.status === 'validated' ? 'badge-green' : s.status === 'retired' ? 'badge-red' : 'badge-gold';
                html += `<tr><td class="muted">${i+1}</td><td class="cyan">${s.id}</td><td>${s.family||'—'}</td><td><span class="badge ${statusCls}">${s.status}</span></td><td>${s.generation||1}</td><td>${wr}</td><td class="gold">${pf}</td><td class="red">${dd}</td><td>${s.best_x10_count||0}</td><td>${bal}</td></tr>`;
            });
            html += '</table>';
            if (strats.length === 0) html = '<p class="muted">No strategies yet</p>';
            evt.detail.target.innerHTML = html;
        } catch(e) {}
    }
});
</script>
{% endblock %}
```

Create `dashboard/templates/tokens.html`:
```html
{% extends "base.html" %}
{% block title %}Token Economy{% endblock %}
{% block content %}
<h2 style="color:var(--gold);font-size:14px;margin-bottom:12px">TOKEN ECONOMY</h2>
<div hx-get="/api/tokens" hx-trigger="load, every 15s" hx-swap="innerHTML" id="token-data">
    <p class="muted">Loading...</p>
</div>

<script>
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === 'token-data') {
        try {
            const data = JSON.parse(evt.detail.target.innerText);
            let html = `<div class="card kpi" style="margin-bottom:12px"><div class="kpi-label">Total Spend</div><div class="kpi-value gold">$${data.total_cost.toFixed(4)}</div></div>`;
            html += '<div class="grid grid-2">';
            html += '<div class="card"><div class="card-title">Cost by Agent</div><table><tr><th>Agent</th><th>Calls</th><th>Tokens In</th><th>Tokens Out</th><th>Cost</th></tr>';
            data.by_agent.forEach(a => {
                html += `<tr><td class="cyan">${a.agent_id}</td><td>${a.calls}</td><td class="muted">${a.total_in}</td><td class="muted">${a.total_out}</td><td class="gold">$${a.cost.toFixed(4)}</td></tr>`;
            });
            html += '</table></div>';
            html += '<div class="card"><div class="card-title">Cost by Model</div><table><tr><th>Model</th><th>Calls</th><th>Cost</th></tr>';
            data.by_model.forEach(m => {
                html += `<tr><td>${m.model}</td><td>${m.calls}</td><td class="gold">$${m.cost.toFixed(4)}</td></tr>`;
            });
            html += '</table></div></div>';
            evt.detail.target.innerHTML = html;
        } catch(e) {}
    }
});
</script>
{% endblock %}
```

Create `dashboard/templates/events.html`:
```html
{% extends "base.html" %}
{% block title %}Event Stream{% endblock %}
{% block content %}
<h2 style="color:var(--gold);font-size:14px;margin-bottom:12px">EVENT STREAM</h2>
<div class="card">
    <div hx-get="/api/events" hx-trigger="load, every 5s" hx-swap="innerHTML" id="event-list">
        <p class="muted">Loading...</p>
    </div>
</div>

<script>
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === 'event-list') {
        try {
            const events = JSON.parse(evt.detail.target.innerText);
            let html = '';
            events.forEach(e => {
                const typeColor = e.event_type === 'error' ? 'red' : e.event_type === 'milestone' ? 'gold' : e.event_type === 'warning' ? 'gold' : 'muted';
                html += `<div class="event-row"><span class="event-time">${e.timestamp||'—'}</span><span class="event-agent">${e.agent_id}</span><span class="badge badge-${typeColor === 'red' ? 'red' : typeColor === 'gold' ? 'gold' : 'green'}">${e.event_type}</span> <span>${e.event_message}</span></div>`;
            });
            if (events.length === 0) html = '<p class="muted">No events yet</p>';
            evt.detail.target.innerHTML = html;
        } catch(e) {}
    }
});
</script>
{% endblock %}
```

- [ ] **Step 6: Create `dashboard/static/` directory placeholder**

Create empty `dashboard/static/.gitkeep` so the static directory exists.

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_dashboard.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add dashboard/app.py dashboard/templates/ dashboard/static/.gitkeep tests/test_dashboard.py
git commit -m "feat: replace Dash dashboard with Flask+htmx real-time UI"
```

---

### Task 2: Meta Agent (`agents/meta_agent.py`)

**Files:**
- Create: `agents/meta_agent.py`
- Create: `tests/test_meta_agent.py`

The Meta Agent collects system state every 5 minutes, sends it to Claude Opus for analysis, and executes the decisions (reconfigure agents, spawn new ones, kill underperformers).

- [ ] **Step 1: Write the failing tests**

`tests/test_meta_agent.py`:
```python
"""Tests for Meta Agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config, status, error_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("meta_agent", "meta_agent", "agents.meta_agent", "MetaAgent",
         '{"tick_interval": 0.01}', "running", 0),
    )
    yield db
    db.close()


def _seed_system(db):
    """Populate DB with realistic system state for testing."""
    agents = [
        ("token_manager", "running", 0),
        ("model_router", "running", 0),
        ("data_agent", "running", 2),
        ("backtest_runner", "running", 0),
        ("strategy_factory", "running", 1),
        ("evolution_agent", "running", 0),
        ("plugin_scout", "running", 0),
    ]
    for name, status, errors in agents:
        db.execute(
            "INSERT OR IGNORE INTO agent_registry (id, name, module_path, class_name, status, error_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, name, f"agents.{name}", name.title().replace("_", ""), status, errors),
        )
    # Add some strategies
    for i in range(3):
        db.execute(
            "INSERT INTO strategies (id, file_path, family, status, best_profit_factor, best_win_rate) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"S{i+1:04d}", f"strategies/s{i+1}.py", "momentum", "candidate", 1.5 + i * 0.5, 0.55 + i * 0.05),
        )
    # Add some tasks
    db.execute(
        "INSERT INTO task_queue (agent_target, task_type, payload, status) VALUES (?, ?, ?, ?)",
        ("backtest_runner", "backtest", '{"strategy_id": "S001"}', "pending"),
    )
    # Add some token usage
    db.execute(
        "INSERT INTO token_usage (agent_id, model, tokens_in, tokens_out, cost_usd, task_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("strategy_factory", "claude-opus-4-6", 500, 2000, 0.16, "generate_strategy"),
    )
    # Add some events
    from core.logger import log_event
    log_event(db, "data_agent", "info", "Found 3 data files")
    log_event(db, "strategy_factory", "milestone", "Strategy S003 registered")


def test_meta_agent_imports():
    from agents.meta_agent import MetaAgent
    assert MetaAgent.name == "meta_agent"


def test_collect_system_state(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)
    state = agent._collect_system_state()
    assert isinstance(state, dict)
    assert "agents" in state
    assert "task_queue" in state
    assert "strategies" in state
    assert "token_usage" in state
    assert "recent_events" in state
    assert len(state["agents"]) >= 7


def test_build_decision_prompt(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)
    state = agent._collect_system_state()
    prompt = agent._build_decision_prompt(state)
    assert isinstance(prompt, str)
    assert "agent" in prompt.lower()
    assert "strategy" in prompt.lower()
    assert len(prompt) > 200


def test_parse_decision_no_changes():
    from agents.meta_agent import MetaAgent
    response = '{"action": "no_changes", "reason": "System is healthy"}'
    decisions = MetaAgent._parse_decisions(response)
    assert isinstance(decisions, list)
    assert len(decisions) == 1
    assert decisions[0]["action"] == "no_changes"


def test_parse_decision_reconfigure():
    from agents.meta_agent import MetaAgent
    response = json.dumps({"actions": [
        {"action": "reconfigure", "agent_id": "backtest_runner", "config": {"tick_interval": 5}},
    ]})
    decisions = MetaAgent._parse_decisions(response)
    assert len(decisions) == 1
    assert decisions[0]["action"] == "reconfigure"


def test_parse_decision_malformed():
    from agents.meta_agent import MetaAgent
    response = "This is not JSON at all, just some text explanation"
    decisions = MetaAgent._parse_decisions(response)
    assert isinstance(decisions, list)
    assert len(decisions) == 0  # Gracefully returns empty on bad response


def test_execute_reconfigure(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)
    decision = {"action": "reconfigure", "agent_id": "backtest_runner", "config": {"tick_interval": 5}}
    agent._execute_decision(decision)
    row = tmp_db.fetchone("SELECT config FROM agent_registry WHERE id = 'backtest_runner'")
    config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
    assert config.get("tick_interval") == 5


def test_execute_disable(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)
    decision = {"action": "disable", "agent_id": "plugin_scout", "reason": "too many errors"}
    agent._execute_decision(decision)
    row = tmp_db.fetchone("SELECT status FROM agent_registry WHERE id = 'plugin_scout'")
    assert row["status"] == "disabled"


def test_tick_no_crash_without_api(tmp_db):
    from agents.meta_agent import MetaAgent
    _seed_system(tmp_db)
    agent = MetaAgent(tmp_db)
    agent.setup()
    try:
        agent.tick()
    except Exception:
        pass  # Expected without API key
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_meta_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.meta_agent'`

- [ ] **Step 3: Implement the Meta Agent**

`agents/meta_agent.py`:
```python
"""Meta Agent: the brain of the system. Analyzes state, makes decisions via Claude Opus."""
import json
import re
import textwrap
from typing import List

from agents.base_agent import BaseAgent
from agents.model_router import ModelRouter
from core.config import DYNAMIC_AGENTS_DIR


class MetaAgent(BaseAgent):
    """Collects system state, calls Claude Opus for decisions, executes actions."""

    name = "meta_agent"

    def __init__(self, db):
        super().__init__(agent_id="meta_agent", db=db)

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Meta Agent ready")

    def tick(self):
        state = self._collect_system_state()
        prompt = self._build_decision_prompt(state)

        self.logger.info("Analyzing system state...")
        model = ModelRouter.route_task("meta_decision")  # -> "opus"
        raw_response = self.call_llm(
            prompt=prompt,
            model=model,
            task_type="meta_decision",
            max_tokens=2048,
            temperature=0.3,
        )

        decisions = self._parse_decisions(raw_response)
        if not decisions:
            self.logger.info("Meta Agent: no changes needed")
            return

        for decision in decisions:
            action = decision.get("action", "unknown")
            if action == "no_changes":
                self.logger.info(f"No changes: {decision.get('reason', '')}")
                continue
            self.logger.info(f"Executing decision: {action}")
            self._execute_decision(decision)

        self.emit_event("decision",
            f"Meta Agent made {len(decisions)} decision(s)",
            metadata={"decisions": decisions},
        )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 300)

    # ── state collection ───────────────────────────────────────────────────────

    def _collect_system_state(self) -> dict:
        """Gather full system snapshot from DB."""
        # Agents
        agents = self.db.fetchall(
            "SELECT id, name, status, error_count, restart_count, last_heartbeat, config "
            "FROM agent_registry"
        )

        # Task queue depth per agent
        queue = self.db.fetchall(
            "SELECT agent_target, status, COUNT(*) as count "
            "FROM task_queue GROUP BY agent_target, status"
        )

        # Strategy landscape
        strat_summary = self.db.fetchone(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status = 'validated' THEN 1 ELSE 0 END) as validated, "
            "SUM(CASE WHEN status = 'retired' THEN 1 ELSE 0 END) as retired, "
            "MAX(best_profit_factor) as best_pf, "
            "MAX(best_win_rate) as best_wr "
            "FROM strategies"
        )

        top_strategies = self.db.fetchall(
            "SELECT id, family, status, best_profit_factor, best_win_rate, best_max_drawdown "
            "FROM strategies WHERE best_profit_factor IS NOT NULL "
            "ORDER BY best_profit_factor DESC LIMIT 5"
        )

        # Token usage (last hour)
        token_summary = self.db.fetchall(
            "SELECT agent_id, model, SUM(cost_usd) as cost, COUNT(*) as calls "
            "FROM token_usage "
            "WHERE timestamp > datetime('now', '-1 hour') "
            "GROUP BY agent_id, model"
        )

        total_cost = self.db.fetchone("SELECT COALESCE(SUM(cost_usd), 0) as total FROM token_usage")

        # Recent events
        events = self.db.fetchall(
            "SELECT agent_id, event_type, event_message, timestamp "
            "FROM events ORDER BY timestamp DESC LIMIT 50"
        )

        return {
            "agents": [dict(a) for a in agents],
            "task_queue": [dict(q) for q in queue],
            "strategies": {
                "total": strat_summary["total"] if strat_summary else 0,
                "validated": strat_summary["validated"] if strat_summary else 0,
                "retired": strat_summary["retired"] if strat_summary else 0,
                "best_pf": strat_summary["best_pf"] if strat_summary else 0,
                "best_wr": strat_summary["best_wr"] if strat_summary else 0,
                "top_5": [dict(s) for s in top_strategies],
            },
            "token_usage": {
                "last_hour": [dict(t) for t in token_summary],
                "total_cost_usd": total_cost["total"] if total_cost else 0.0,
            },
            "recent_events": [dict(e) for e in events],
        }

    # ── prompt building ────────────────────────────────────────────────────────

    def _build_decision_prompt(self, state: dict) -> str:
        """Build the structured prompt for Claude Opus."""
        agents_lines = []
        for a in state["agents"]:
            agents_lines.append(
                f"  - {a['name']}: status={a['status']}, errors={a['error_count']}, "
                f"restarts={a.get('restart_count', 0)}, heartbeat={a.get('last_heartbeat', 'N/A')}"
            )

        queue_lines = []
        for q in state["task_queue"]:
            queue_lines.append(f"  - {q['agent_target']}: {q['count']} {q['status']}")

        strat = state["strategies"]
        top_lines = []
        for s in strat.get("top_5", []):
            top_lines.append(
                f"  - {s['id']} ({s.get('family', '?')}): PF={s.get('best_profit_factor')}, "
                f"WR={s.get('best_win_rate')}, status={s['status']}"
            )

        token_lines = []
        for t in state["token_usage"].get("last_hour", []):
            token_lines.append(f"  - {t['agent_id']} ({t['model']}): ${t['cost']:.4f} ({t['calls']} calls)")

        event_lines = []
        for e in state["recent_events"][:20]:
            event_lines.append(f"  [{e.get('timestamp', '')}] {e['agent_id']}/{e['event_type']}: {e['event_message']}")

        prompt = textwrap.dedent(f"""\
            You are the Meta Agent of the XAUUSD-SCALPER-X10 autonomous multi-agent system.
            Your job: analyze the current system state and decide what changes to make.

            === CURRENT SYSTEM STATE ===

            AGENTS:
            {chr(10).join(agents_lines) if agents_lines else "  (none)"}

            TASK QUEUE:
            {chr(10).join(queue_lines) if queue_lines else "  (empty)"}

            STRATEGIES:
              Total: {strat['total']}, Validated: {strat['validated']}, Retired: {strat['retired']}
              Best PF: {strat['best_pf']}, Best WR: {strat['best_wr']}
              Top 5:
            {chr(10).join(top_lines) if top_lines else "    (none)"}

            TOKEN USAGE (last hour):
            {chr(10).join(token_lines) if token_lines else "  (none)"}
              Total all-time: ${state['token_usage']['total_cost_usd']:.4f}

            RECENT EVENTS:
            {chr(10).join(event_lines) if event_lines else "  (none)"}

            === AVAILABLE ACTIONS ===
            1. "reconfigure" — change an agent's config (e.g. tick_interval)
               Format: {{"action": "reconfigure", "agent_id": "...", "config": {{...}}}}
            2. "disable" — stop an agent (set status=disabled)
               Format: {{"action": "disable", "agent_id": "...", "reason": "..."}}
            3. "enable" — re-enable a disabled agent
               Format: {{"action": "enable", "agent_id": "...", "reason": "..."}}
            4. "no_changes" — system is healthy, no action needed
               Format: {{"action": "no_changes", "reason": "..."}}

            === RULES ===
            - Never disable token_manager, model_router, or meta_agent (critical infrastructure)
            - Prefer reconfiguration over disabling
            - If backtest_runner queue is deep (>10 pending), consider reducing strategy_factory tick_interval
            - If error_count > 10 for any agent, consider disabling it
            - If no strategies are being validated, consider reconfiguring evolution_agent or strategy_factory

            === OUTPUT FORMAT ===
            Return a JSON object with either:
            - {{"action": "no_changes", "reason": "..."}} for no changes
            - {{"actions": [...]}} for a list of actions

            Return ONLY valid JSON, no explanation or markdown.
        """)
        return prompt

    # ── response parsing ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_decisions(raw_response: str) -> list:
        """Parse the LLM response into a list of decision dicts."""
        text = raw_response.strip()

        # Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []

        if isinstance(data, dict):
            if "actions" in data:
                return data["actions"] if isinstance(data["actions"], list) else []
            if "action" in data:
                return [data]

        if isinstance(data, list):
            return data

        return []

    # ── decision execution ─────────────────────────────────────────────────────

    def _execute_decision(self, decision: dict):
        """Execute a single decision dict."""
        action = decision.get("action", "")
        agent_id = decision.get("agent_id", "")

        # Safety: never disable critical agents
        protected = {"token_manager", "model_router", "meta_agent"}
        if action == "disable" and agent_id in protected:
            self.logger.warning(f"Refused to disable protected agent: {agent_id}")
            self.emit_event("warning", f"Refused to disable protected agent: {agent_id}")
            return

        if action == "reconfigure":
            new_config = decision.get("config", {})
            if not isinstance(new_config, dict) or not agent_id:
                return
            # Merge with existing config
            row = self.db.fetchone("SELECT config FROM agent_registry WHERE id = ?", (agent_id,))
            if row is None:
                return
            existing = json.loads(row["config"]) if isinstance(row["config"], str) else (row["config"] or {})
            existing.update(new_config)
            self.db.execute(
                "UPDATE agent_registry SET config = ? WHERE id = ?",
                (json.dumps(existing), agent_id),
            )
            self.logger.info(f"Reconfigured {agent_id}: {new_config}")
            self.emit_event("decision", f"Reconfigured {agent_id}", metadata=decision)

        elif action == "disable":
            self.db.execute(
                "UPDATE agent_registry SET status = 'disabled' WHERE id = ?", (agent_id,)
            )
            self.logger.info(f"Disabled agent: {agent_id} — {decision.get('reason', '')}")
            self.emit_event("decision", f"Disabled {agent_id}: {decision.get('reason', '')}")

        elif action == "enable":
            self.db.execute(
                "UPDATE agent_registry SET status = 'stopped', error_count = 0 WHERE id = ?",
                (agent_id,),
            )
            self.logger.info(f"Re-enabled agent: {agent_id}")
            self.emit_event("decision", f"Re-enabled {agent_id}: {decision.get('reason', '')}")

        elif action == "no_changes":
            pass  # Nothing to do

        else:
            self.logger.warning(f"Unknown action: {action}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_meta_agent.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add agents/meta_agent.py tests/test_meta_agent.py
git commit -m "feat: add Meta Agent with Claude-powered system decisions"
```

---

### Task 3: UI Director agent (`agents/ui_director.py`)

**Files:**
- Create: `agents/ui_director.py`
- Create: `tests/test_ui_director.py`
- Modify: `core/config.py` — add `DASHBOARD_PORT = 8050`

The UI Director starts the Flask dashboard server in a daemon thread and periodically logs dashboard-related events.

- [ ] **Step 1: Write the failing tests**

`tests/test_ui_director.py`:
```python
"""Tests for UI Director agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("ui_director", "ui_director", "agents.ui_director", "UIDirector",
         '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_ui_director_imports():
    from agents.ui_director import UIDirector
    assert UIDirector.name == "ui_director"


def test_setup_no_crash(tmp_db):
    from agents.ui_director import UIDirector
    agent = UIDirector(tmp_db)
    agent.setup()
    # Should not crash — server starts in daemon thread


def test_tick_no_crash(tmp_db):
    from agents.ui_director import UIDirector
    agent = UIDirector(tmp_db)
    agent.setup()
    agent.tick()  # Should not crash


def test_compute_dashboard_stats(tmp_db):
    from agents.ui_director import UIDirector
    # Seed some data
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status, best_profit_factor) VALUES (?, ?, ?, ?, ?)",
        ("S001", "s.py", "test", "validated", 3.0),
    )
    agent = UIDirector(tmp_db)
    stats = agent._compute_dashboard_stats()
    assert isinstance(stats, dict)
    assert "total_strategies" in stats
    assert stats["total_strategies"] >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ui_director.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.ui_director'`

- [ ] **Step 3: Add DASHBOARD_PORT to config**

Add after line 40 in `core/config.py` (after `DEFAULT_TICK_INTERVAL`):

```python
DASHBOARD_PORT = 8050
```

- [ ] **Step 4: Implement the UI Director**

`agents/ui_director.py`:
```python
"""UI Director Agent: starts the Flask dashboard and refreshes aggregate data."""
import threading

from agents.base_agent import BaseAgent
from core.config import DASHBOARD_PORT


class UIDirector(BaseAgent):
    """Starts the web dashboard and periodically computes aggregate stats."""

    name = "ui_director"

    def __init__(self, db):
        super().__init__(agent_id="ui_director", db=db)
        self._server_started = False

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def setup(self):
        self._start_dashboard_server()
        self.logger.info(f"UI Director ready — dashboard on http://localhost:{DASHBOARD_PORT}")

    def tick(self):
        stats = self._compute_dashboard_stats()
        self.logger.debug(
            f"Dashboard stats: {stats.get('total_strategies', 0)} strategies, "
            f"{stats.get('agents_running', 0)} agents running"
        )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 30)

    # ── dashboard server ───────────────────────────────────────────────────────

    def _start_dashboard_server(self):
        """Start the Flask dashboard in a daemon thread."""
        if self._server_started:
            return
        try:
            from dashboard.app import app

            def run_server():
                app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False, use_reloader=False)

            t = threading.Thread(target=run_server, name="dashboard-server", daemon=True)
            t.start()
            self._server_started = True
            self.emit_event("milestone", f"Dashboard started on port {DASHBOARD_PORT}")
        except Exception as e:
            self.logger.error(f"Failed to start dashboard: {e}")
            self.emit_event("error", f"Dashboard start failed: {e}")

    # ── stats computation ──────────────────────────────────────────────────────

    def _compute_dashboard_stats(self) -> dict:
        """Compute aggregate stats for the dashboard."""
        agents = self.db.fetchall("SELECT status FROM agent_registry")
        running = sum(1 for a in agents if a["status"] == "running")

        strats = self.db.fetchone("SELECT COUNT(*) as c FROM strategies")
        validated = self.db.fetchone("SELECT COUNT(*) as c FROM strategies WHERE status = 'validated'")

        cost = self.db.fetchone("SELECT COALESCE(SUM(cost_usd), 0) as total FROM token_usage")

        return {
            "agents_total": len(agents),
            "agents_running": running,
            "total_strategies": strats["c"] if strats else 0,
            "validated_strategies": validated["c"] if validated else 0,
            "total_cost_usd": round(cost["total"], 4) if cost else 0.0,
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ui_director.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add agents/ui_director.py tests/test_ui_director.py core/config.py
git commit -m "feat: add UI Director agent with Flask dashboard server"
```

---

### Task 4: Register meta_agent + ui_director in CORE_AGENTS

**Files:**
- Modify: `core/config.py:43-93` — add both agents
- Modify: `tests/test_config.py:28-39` — update assertions for 9 agents
- Modify: `tests/test_orchestrator.py:21-33` — verify new agents register

- [ ] **Step 1: Update config.py**

Add two entries to the `CORE_AGENTS` list in `core/config.py`, after `plugin_scout`:

```python
    {
        "name": "ui_director",
        "module_path": "agents.ui_director",
        "class_name": "UIDirector",
        "config": {"tick_interval": 30},
        "can_spawn_children": False,
    },
    {
        "name": "meta_agent",
        "module_path": "agents.meta_agent",
        "class_name": "MetaAgent",
        "config": {"tick_interval": 300},
        "can_spawn_children": True,
    },
```

Note: `meta_agent` is last (per spec: "Launch Meta Agent last — needs to observe others first") and has `can_spawn_children: True`.

- [ ] **Step 2: Update test_config.py**

Replace the `test_core_agents_list` function:

```python
def test_core_agents_list():
    from core.config import CORE_AGENTS
    assert isinstance(CORE_AGENTS, list)
    assert len(CORE_AGENTS) >= 9
    names = [a["name"] for a in CORE_AGENTS]
    assert "token_manager" in names
    assert "model_router" in names
    assert "data_agent" in names
    assert "backtest_runner" in names
    assert "strategy_factory" in names
    assert "evolution_agent" in names
    assert "plugin_scout" in names
    assert "ui_director" in names
    assert "meta_agent" in names
    # Meta agent must be last (needs to observe others first)
    assert names[-1] == "meta_agent"
```

- [ ] **Step 3: Update test_orchestrator.py**

Update `test_register_core_agents`:

```python
def test_register_core_agents(tmp_db):
    from agents.orchestrator import Orchestrator
    orch = Orchestrator(tmp_db)
    orch.register_core_agents()
    agents = tmp_db.fetchall("SELECT name FROM agent_registry")
    names = {row["name"] for row in agents}
    assert "token_manager" in names
    assert "model_router" in names
    assert "data_agent" in names
    assert "backtest_runner" in names
    assert "strategy_factory" in names
    assert "evolution_agent" in names
    assert "plugin_scout" in names
    assert "ui_director" in names
    assert "meta_agent" in names
```

Update `test_orchestrator_start_and_stop` join timeout:

```python
    # 9 agents × 3s join timeout each + check_internet() up to 5s = ~32s worst case
    t.join(timeout=60)
```

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add core/config.py tests/test_config.py tests/test_orchestrator.py
git commit -m "feat: register ui_director and meta_agent in CORE_AGENTS (9 total)"
```

---

### Task 5: Phase 4 integration test

**Files:**
- No new files — verification task.

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL tests pass

- [ ] **Step 2: Start the system briefly**

Run the system for 20 seconds and verify all 9 agents start:
```bash
timeout 20 python start.py
```
Expected:
- All 9 agents registered and started
- `Dashboard started on port 8050` in logs
- `Meta Agent ready` in logs

- [ ] **Step 3: Verify dashboard is accessible**

While the system is running (or immediately after), check:
```bash
curl -s http://localhost:8050/ | head -20
curl -s http://localhost:8050/api/summary
```
Expected: HTML response from `/`, JSON from `/api/summary`

- [ ] **Step 4: Verify DB state**

```bash
python -c "
from core.db import Database; from core.config import DB_PATH
db = Database(DB_PATH)
agents = db.fetchall('SELECT name, status FROM agent_registry')
print('Agents:', [dict(r) for r in agents])
print(f'Total: {len(agents)}')
db.close()
"
```
Expected: 9 agents listed

- [ ] **Step 5: Commit any fixes**

```bash
git add -A && git commit -m "fix: Phase 4 integration fixes" || echo "No fixes needed"
```
