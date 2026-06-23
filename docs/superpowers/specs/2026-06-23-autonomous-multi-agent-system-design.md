# SPEC: XAUUSD-SCALPER-X10 Autonomous Multi-Agent System

**Date:** 2026-06-23
**Status:** Approved
**Goal:** Build a fully autonomous, continuously running multi-agent system that discovers, backtests, optimizes, and evolves XAUUSD M1 scalping strategies — indefinitely, without human intervention.

---

## 1. Principles

1. **Full autonomy** — Agents decide everything: data sources, models, strategies, UI layout, what to install, what to kill. No human approval gates.
2. **Never stops** — The system runs as long as power + internet are available. No success condition halts the loop. Today's best strategy is tomorrow's baseline.
3. **Self-expanding** — The Meta Agent can create new agents that don't exist yet. The system grows its own capabilities.
4. **Cost-aware but not cost-limited** — Token Manager optimizes spend, but never halts the system for budget reasons.
5. **Observable** — The UI Director provides real-time visibility into everything via a web dashboard. The user never has to ask what's happening.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    META AGENT                            │
│         (creates, kills, reconfigures agents)            │
├─────────────────────────────────────────────────────────┤
│                    ORCHESTRATOR                          │
│         (Python daemon — heartbeat, restart, dispatch)   │
├─────────────────────────────────────────────────────────┤
│                 AGENT LAYER (dynamic)                    │
│                                                         │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ Data    │ │ Strategy │ │ Backtest │ │ Evolution │  │
│  │ Agent   │ │ Factory  │ │ Runner   │ │ Agent     │  │
│  └─────────┘ └──────────┘ └──────────┘ └───────────┘  │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ Token   │ │ Model    │ │ Plugin   │ │ UI        │  │
│  │ Manager │ │ Router   │ │ Scout    │ │ Director  │  │
│  └─────────┘ └──────────┘ └──────────┘ └───────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │ ... agents created dynamically by Meta Agent     │  │
│  └──────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│                    SHARED STATE                          │
│        SQLite DB  │  File System  │  Event Log          │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Shared State: SQLite Database

All agents communicate through a single SQLite database (`agent_db.sqlite`). No external message broker needed.

### Schema

```sql
-- Agent registry (managed by Meta Agent)
CREATE TABLE agent_registry (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    module_path TEXT NOT NULL,       -- e.g. "agents.data_agent"
    class_name TEXT NOT NULL,        -- e.g. "DataAgent"
    status TEXT DEFAULT 'stopped',   -- stopped | running | error | disabled
    parent_agent TEXT,               -- hierarchy: sub-agent of whom
    created_by TEXT,                 -- which agent spawned this one
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config JSON DEFAULT '{}',        -- agent-specific params
    can_spawn_children BOOLEAN DEFAULT FALSE,
    last_heartbeat TIMESTAMP,
    error_count INTEGER DEFAULT 0,
    restart_count INTEGER DEFAULT 0
);

-- Task queue (agents post and consume tasks)
CREATE TABLE task_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_target TEXT NOT NULL,      -- which agent should handle this
    task_type TEXT NOT NULL,         -- e.g. "backtest", "generate_strategy"
    payload JSON NOT NULL,
    status TEXT DEFAULT 'pending',   -- pending | running | completed | failed
    priority INTEGER DEFAULT 5,     -- 1=highest, 10=lowest
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result JSON
);

-- Strategy registry
CREATE TABLE strategies (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    family TEXT,
    description TEXT,
    generation INTEGER DEFAULT 1,    -- evolution generation
    parent_strategy TEXT,            -- evolved from which strategy
    created_by TEXT,                 -- which agent created it
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'candidate', -- candidate | testing | validated | hall_of_fame | retired | deleted
    -- Best known metrics
    best_win_rate REAL,
    best_profit_factor REAL,
    best_max_drawdown REAL,
    best_x10_count INTEGER DEFAULT 0,
    best_final_balance REAL,
    regimes_passed INTEGER DEFAULT 0,
    walk_forward_passed BOOLEAN DEFAULT FALSE,
    -- Config that produced best results
    best_config JSON
);

-- Backtest results (append-only log)
CREATE TABLE backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    risk_pct REAL,
    config JSON,
    total_trades INTEGER,
    win_rate REAL,
    profit_factor REAL,
    max_drawdown REAL,
    x10_count INTEGER,
    final_balance REAL,
    return_pct REAL,
    blown_account BOOLEAN,
    regime_results JSON,            -- per-regime breakdown
    walk_forward BOOLEAN DEFAULT FALSE,
    data_hash TEXT,                  -- hash of data used (detect stale results)
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Token usage tracking
CREATE TABLE token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    model TEXT NOT NULL,             -- claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-6
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    task_type TEXT,                  -- what was this call for
    cached_tokens INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Event log (system-wide audit trail)
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT,
    event_type TEXT NOT NULL,        -- info | warning | error | decision | milestone
    message TEXT NOT NULL,
    metadata JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Data registry (tracks available datasets)
CREATE TABLE data_registry (
    id TEXT PRIMARY KEY,
    instrument TEXT DEFAULT 'XAUUSD',
    timeframe TEXT NOT NULL,         -- M1, M5, H1
    source TEXT,                     -- MT5, Dukascopy, FXCM
    file_path TEXT NOT NULL,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    bar_count INTEGER,
    quality_score REAL,              -- 0-1, computed by Data Agent
    regime_labeled BOOLEAN DEFAULT FALSE,
    hash TEXT,                       -- file content hash
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Plugin registry (managed by Plugin Scout)
CREATE TABLE plugins (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_url TEXT,
    install_type TEXT,               -- pip | npm | git_clone | skill
    status TEXT DEFAULT 'installed', -- installed | active | disabled | failed
    installed_by TEXT,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    used_by JSON DEFAULT '[]'        -- which agents use this plugin
);
```

---

## 4. Agent Specifications

### 4.0 Orchestrator (`agents/orchestrator.py`)

Not an agent — the daemon process that manages all agents.

**Responsibilities:**
- Start the system: initialize DB, register core agents, launch them
- Heartbeat loop (every 10s): check each agent is alive, restart if dead
- Internet connectivity check: pause agents gracefully if offline, resume when back
- Graceful shutdown on SIGINT/SIGTERM
- Log rotation and DB maintenance

**Implementation:**
- Python `multiprocessing` — each agent runs in its own process
- Agents inherit from `BaseAgent` which handles heartbeat, DB access, event logging
- Orchestrator reads `agent_registry` to know what to run

```python
# Lifecycle
def main():
    init_database()
    register_core_agents()
    while True:
        if not check_internet():
            pause_all_agents()
            wait_for_internet()
            resume_all_agents()
        
        for agent in get_registered_agents():
            if agent.status == 'running' and agent.heartbeat_stale():
                restart_agent(agent)
            if agent.status == 'stopped' and agent.should_be_running():
                start_agent(agent)
        
        process_meta_agent_decisions()  # spawn/kill per Meta Agent orders
        sleep(10)
```

### 4.1 Base Agent (`agents/base_agent.py`)

Abstract class all agents inherit from.

```python
class BaseAgent:
    name: str
    agent_id: str
    db: Database
    logger: Logger
    
    def setup(self)          # called once at start
    def tick(self)           # called in loop — main work
    def tick_interval(self)  # seconds between ticks (agent decides)
    def cleanup(self)        # called on shutdown
    
    # Built-in capabilities
    def emit_event(self, type, message, metadata=None)
    def post_task(self, target_agent, task_type, payload, priority=5)
    def get_tasks(self, status='pending')
    def update_heartbeat(self)
    def call_llm(self, prompt, model=None)  # routes through Model Router
    def get_config(self, key, default=None)
    def set_config(self, key, value)
```

Each agent's `run()` loop:
```python
def run(self):
    self.setup()
    while not self.shutdown_requested:
        self.update_heartbeat()
        try:
            self.tick()
        except Exception as e:
            self.emit_event('error', str(e))
            self.error_count += 1
        sleep(self.tick_interval())
    self.cleanup()
```

### 4.2 Data Agent (`agents/data_agent.py`)

**Role:** Acquire, maintain, and quality-check market data.

**Tick cycle:**
1. Check what data we have (query `data_registry`)
2. If < 1 year M1 data: download more from MT5 or fallback sources
3. If data is stale (last bar > 1 hour ago for M1): update
4. Run quality check: gaps, spikes, timezone alignment
5. Label regimes (ADX/ATR-based) on new data
6. Emit event when new data is available

**Data sources (priority order):**
1. MetaTrader 5 via `MetaTrader5` Python package (IC Markets account on local PC)
2. Dukascopy historical tick data (free, converted to M1)
3. FXCM REST API (free tier)

**Multi-timeframe:**
- Downloads M1 (primary), M5, M15, H1 (for context)
- Strategy Factory can use higher TFs for trend filters

**Quality scoring:**
```
quality_score = 1.0
  - 0.1 per % of missing bars (gaps)
  - 0.2 if timezone inconsistency detected
  - 0.1 per anomalous spike (> 5 ATR single bar)
```

**Tick interval:** 300s (check every 5 min)

### 4.3 Strategy Factory (`agents/strategy_factory.py`)

**Role:** Generate new trading strategies using Claude API.

**Tick cycle:**
1. Review current strategy landscape (what families exist, what's been tried)
2. Review backtest results (what works, what doesn't, what's unexplored)
3. Decide what type of strategy to generate next (the agent decides, not hardcoded)
4. Call Claude API (via Model Router — typically Opus for this) with context:
   - Current best strategies and their metrics
   - What has failed and why
   - Available indicators and data
   - Constraint: must output a valid Python file with `PARAMS` dict and `generate_signals(df, p)` function
5. Validate generated code: syntax check, dry-run on small data sample
6. Register strategy in DB, post task to Backtest Runner

**Strategy types to explore (initial seed, agent expands this):**
- Momentum bursts (consecutive directional bars + volume spike)
- Range breakout (M5/M15 consolidation → M1 breakout)
- Order block / Fair Value Gap (price imbalance zones)
- Pullback in trend (H1 trend + M1 pullback to key level)
- Session-based (London open, NY open, Asian range breakout)
- Volume profile (tick_volume anomalies)
- Multi-timeframe confluence
- Candlestick pattern + context

**Output format:** Each strategy is a standalone `.py` file in `strategies/` following the existing convention:
```python
PARAMS = { ... }
def generate_signals(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    # Must return df with 'signal' column: 1=long, -1=short, 0=flat
```

**Tick interval:** 600s (generate a new strategy every ~10 min, adaptive)

### 4.4 Backtest Runner (`agents/backtest_runner.py`)

**Role:** Run backtests continuously on all pending strategies.

**Tick cycle:**
1. Check for strategies with status='candidate' or 'testing' that need backtesting
2. Check if data has been updated (compare hash) — re-run stale results
3. Run backtest using improved engine (see Engine Improvements below)
4. Store results in `backtest_results` table
5. Update strategy metrics in `strategies` table
6. If strategy passes validation → status='validated', emit milestone event
7. Run walk-forward on validated strategies

**Engine improvements over current `engine.py`:**
- **Trailing stop:** Move SL to breakeven after 1R profit, then trail by ATR
- **Time-based exit:** Close trade if no TP/SL hit after N bars (configurable, default 60)
- **Partial TP:** Take 50% at TP1 (1.5R), let rest run to TP2 (3R) with trailing
- **Session filter:** Skip signals outside active sessions (configurable per strategy)
- **Multi-risk sweep:** Test each strategy at risk_pct = [0.02, 0.05, 0.10, 0.15, 0.20]

**Parallelization:** Use `multiprocessing.Pool` to run multiple backtests simultaneously (1 per CPU core).

**Tick interval:** 10s (always working if there's a queue)

### 4.5 Evolution Agent (`agents/evolution_agent.py`)

**Role:** Optimize parameters and evolve strategies using genetic algorithms.

**Tick cycle:**
1. Select top-performing strategies (top 10 by composite score)
2. For each: run parameter optimization via Optuna
   - Optimize: sl_atr, tp_atr, indicator periods, thresholds
   - Objective: maximize composite score (WR * 0.3 + PF * 0.3 + (1-DD) * 0.2 + x10_count * 0.2)
   - In-sample / out-of-sample split: 70/30
3. Crossover: combine signal logic from two good strategies
4. Mutation: randomly tweak parameters of copies
5. Register new variants as generation N+1, post to Backtest Runner
6. Retire strategies that fail consistently across 3+ generations
7. Maintain Hall of Fame: strategies that passed all validation criteria

**Selection pressure:**
```
composite_score = (
    win_rate * 0.25 +
    min(profit_factor / 4.0, 1.0) * 0.30 +
    (1 - max_drawdown) * 0.20 +
    min(x10_count / 5, 1.0) * 0.25
)
```

**Tick interval:** 120s

### 4.6 Token Manager (`agents/token_manager.py`)

**Role:** Track and optimize API token consumption.

**Tick cycle:**
1. Aggregate token_usage from last period
2. Compute cost per agent, per model, per task type
3. Identify waste: repeated similar prompts, cache misses, oversized contexts
4. Emit optimization suggestions as events (Model Router reads these)
5. Update dashboard data

**Optimizations applied automatically:**
- Prompt caching (detect identical/similar prompts, serve cached results)
- Batch requests where possible
- Suggest model downgrades for low-value tasks

**Tick interval:** 60s

### 4.7 Model Router (`agents/model_router.py`)

**Role:** Route LLM calls to the optimal model.

**Routing rules (initial, self-evolving):**

| Task Type | Default Model | Escalation |
|---|---|---|
| Code syntax check | Haiku | — |
| Parse/format data | Haiku | — |
| Classify strategy type | Haiku | Sonnet if uncertain |
| Analyze backtest results | Sonnet | — |
| Generate new strategy | Opus | — |
| Debug failing strategy | Sonnet | Opus if first attempt fails |
| Meta Agent decisions | Opus | — |
| Plugin evaluation | Sonnet | — |

**Self-learning:** Tracks success rate per model per task. If Haiku handles a task well 95% of the time, keeps using Haiku. If it fails often, escalates default to Sonnet.

**Interface:**
```python
def route(self, prompt: str, task_type: str, 
          min_model: str = "haiku", max_model: str = "opus") -> LLMResponse:
```

**Tick interval:** 30s (mostly reactive — responds to routing requests)

### 4.8 Plugin Scout (`agents/plugin_scout.py`)

**Role:** Find, evaluate, install, and integrate external tools.

**Tick cycle:**
1. Search GitHub for relevant repositories (trading indicators, data sources, optimization tools)
2. Evaluate candidates: stars, recent activity, relevance, license
3. Install promising ones (`pip install`, `git clone`, `npx skills add`)
4. Test that they work (import check, basic smoke test)
5. Register in `plugins` table
6. Emit event so other agents know new tools are available

**Search domains:**
- Python packages: TA-Lib, vectorbt, backtesting.py, freqtrade indicators
- Claude Code skills: trading-related skills on GitHub
- Data connectors: new broker APIs, free data sources
- Optimization: evolutionary algorithms, bayesian optimization

**Safety:**
- Only install from sources with >50 GitHub stars or known package registries
- Run in isolated subprocess first to detect crashes
- Rollback if a plugin causes errors in other agents

**Tick interval:** 3600s (hourly — no rush)

### 4.9 Meta Agent (`agents/meta_agent.py`)

**Role:** The brain of the system. Creates, kills, reconfigures agents.

**Capabilities:**
- **Spawn new agents:** Writes Python code for a new agent, registers it, orchestrator starts it
- **Kill agents:** Sets status='disabled', orchestrator stops the process
- **Scale agents:** Spawn duplicate agents for parallelism (e.g., 3 Backtest Runners)
- **Reconfigure:** Change agent tick intervals, priorities, config
- **Create agent types that don't exist yet:** If the system needs a capability (e.g., news analysis, sentiment, live paper trading), Meta Agent designs and codes it

**Decision inputs:**
- Agent heartbeats and error rates
- Task queue depth (bottleneck detection)
- Backtest result trends (stagnation detection)
- Token usage patterns
- Events from all agents

**Decision logic (uses Claude Opus):**
Every N ticks, Meta Agent calls Opus with a system summary:
```
Here is the current state of the multi-agent system:
- Agents: [list with status, error rates, throughput]
- Task queue: [depth per agent]
- Strategy landscape: [best scores, trend, stagnation?]
- Token usage: [cost trend]
- Recent events: [last 50 events]

What changes should be made? Options:
1. Spawn/kill/scale agents
2. Create a new agent type
3. Change agent configurations
4. No changes needed
```

**Tick interval:** 300s (evaluate system every 5 min)

### 4.10 UI Director (`agents/ui_director.py`)

**Role:** Manage all visual output — dashboard, reports, charts.

**Dashboard (Flask + htmx for real-time updates):**

**Pages (dynamically managed):**
- **System Overview:** Agent statuses, heartbeats, error counts, uptime
- **Strategy Race:** All strategies ranked by composite score, live-updating
- **Hall of Fame:** Validated strategies with full equity curves
- **Strategy Deep Dive:** Per-strategy page (auto-created when a strategy shows promise)
- **Token Economy:** Cost per agent, per model, trends, projections
- **Data Health:** Dataset coverage, quality scores, gaps
- **Event Stream:** Real-time log of all system events
- **Agent Graph:** Visual hierarchy of agents and sub-agents

**Sub-agents:**
- **Chart Renderer:** Generates equity curves, drawdown charts (matplotlib/plotly → static files)
- **Report Writer:** Generates markdown/PDF reports for milestone events
- **Notification Agent:** (future) Telegram/email alerts

**Tick interval:** 30s (refresh dashboard data)

**Tech stack:**
- Flask backend serving JSON APIs
- htmx for real-time DOM updates (lightweight, no React/Vue needed)
- Plotly for interactive charts
- Served on `http://localhost:8050`

---

## 5. File Structure

```
XAUUSD-SCALPER-X10/
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py          # Main daemon
│   ├── base_agent.py            # BaseAgent abstract class
│   ├── data_agent.py            # 4.2 Data Agent
│   ├── strategy_factory.py      # 4.3 Strategy Factory
│   ├── backtest_runner.py       # 4.4 Backtest Runner
│   ├── evolution_agent.py       # 4.5 Evolution Agent
│   ├── token_manager.py         # 4.6 Token Manager
│   ├── model_router.py          # 4.7 Model Router
│   ├── plugin_scout.py          # 4.8 Plugin Scout
│   ├── meta_agent.py            # 4.9 Meta Agent
│   ├── ui_director.py           # 4.10 UI Director
│   └── dynamic/                 # Agents created by Meta Agent at runtime
│       └── (generated .py files)
├── core/
│   ├── __init__.py
│   ├── db.py                    # SQLite wrapper (thread-safe)
│   ├── config.py                # System-wide config
│   ├── logger.py                # Structured logging
│   └── api_client.py            # Anthropic API client with token tracking
├── engine/
│   ├── __init__.py
│   ├── backtest.py              # Improved backtest engine
│   └── optimizer.py             # Optuna-based parameter optimizer
├── dashboard/
│   ├── app.py                   # Flask app
│   ├── templates/               # Jinja2 + htmx templates
│   │   ├── base.html
│   │   ├── overview.html
│   │   ├── strategy_race.html
│   │   ├── hall_of_fame.html
│   │   ├── token_economy.html
│   │   ├── data_health.html
│   │   ├── events.html
│   │   └── agent_graph.html
│   └── static/
│       ├── css/
│       └── js/
├── strategies/                  # Existing + generated by Strategy Factory
├── data/                        # Existing + maintained by Data Agent
├── plugins/                     # Installed by Plugin Scout
├── docs/superpowers/specs/      # This spec
├── agent_db.sqlite              # Shared state (auto-created)
├── requirements.txt             # Python dependencies
└── start.py                     # Entry point: python start.py
```

---

## 6. Dependencies

```
# requirements.txt
anthropic>=0.40.0        # Claude API
MetaTrader5>=5.0.45      # MT5 connection (Windows only)
pandas>=2.0
numpy>=1.24
ta>=0.11.0               # Technical analysis indicators
optuna>=3.6              # Hyperparameter optimization
flask>=3.0
plotly>=5.18
htmx                     # (served via CDN, no pip)
sqlite3                  # (stdlib)
requests>=2.31           # HTTP for Plugin Scout
```

---

## 7. Startup Sequence

```
python start.py
│
├── 1. Initialize SQLite database (create tables if not exist)
├── 2. Register core agents in agent_registry
├── 3. Start Orchestrator main loop
│   ├── Launch Token Manager (must be first — others depend on it)
│   ├── Launch Model Router
│   ├── Launch Data Agent
│   ├── Wait for Data Agent to report data available
│   ├── Launch Backtest Runner
│   ├── Launch Strategy Factory
│   ├── Launch Evolution Agent
│   ├── Launch Plugin Scout
│   ├── Launch UI Director (dashboard starts serving)
│   ├── Launch Meta Agent (last — needs to observe others first)
│   └── Enter heartbeat loop
│
└── Dashboard available at http://localhost:8050
```

---

## 8. Continuous Loop Lifecycle

```
FOREVER:
│
├── Data Agent updates data
│   └── emits "data_updated" event
│
├── Strategy Factory generates new strategy
│   └── posts "backtest" task to Backtest Runner
│
├── Backtest Runner processes queue
│   ├── runs backtest
│   ├── stores results
│   └── emits "backtest_complete" event
│
├── Evolution Agent reads results
│   ├── optimizes top strategies
│   ├── creates evolved variants
│   └── posts new "backtest" tasks
│
├── Meta Agent evaluates system health
│   ├── spawns/kills agents as needed
│   └── creates new agent types if needed
│
├── Plugin Scout searches for tools
│   └── installs useful packages
│
├── Token Manager tracks costs
│   └── suggests optimizations
│
├── Model Router adjusts routing
│   └── based on success rates
│
├── UI Director refreshes dashboard
│   └── creates new views for milestones
│
└── REPEAT
```

---

## 9. Error Handling

- **Agent crash:** Orchestrator detects stale heartbeat → restart agent (max 5 restarts, then emit critical event, Meta Agent decides)
- **Internet down:** Orchestrator pauses all agents, polls connectivity every 30s, resumes when back
- **MT5 disconnected:** Data Agent falls back to alternative sources
- **Claude API error:** Model Router retries with exponential backoff (1s, 2s, 4s, 8s, max 60s)
- **DB locked:** All DB access uses WAL mode + retry with backoff
- **Strategy code error:** Backtest Runner catches exceptions, marks strategy as 'failed', logs error
- **Disk full:** Orchestrator monitors disk space, emits warning at 90%, pauses non-critical agents at 95%

---

## 10. Migration Path (PC → Cloud)

Current design runs on Windows with MT5. For cloud migration:
1. Replace MT5 data source with API-based alternatives (already built as fallbacks)
2. Package as Docker container
3. SQLite → PostgreSQL (if scale demands it, but SQLite handles this workload fine)
4. Dashboard already web-based — just expose port
5. `start.py` works the same on Linux

No architectural changes needed. The agents are source-agnostic by design.
