"""System-wide configuration and constants."""
from pathlib import Path

# ── Paths ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "agent_db.sqlite"
DATA_DIR = BASE_DIR / "data"
STRATEGIES_DIR = BASE_DIR / "strategies"
PLUGINS_DIR = BASE_DIR / "plugins"
DYNAMIC_AGENTS_DIR = BASE_DIR / "agents" / "dynamic"
LOG_DIR = BASE_DIR / "logs"

# Ensure directories exist
for d in [DATA_DIR, STRATEGIES_DIR, PLUGINS_DIR, DYNAMIC_AGENTS_DIR, LOG_DIR,
          DATA_DIR / "raw", DATA_DIR / "processed"]:
    d.mkdir(parents=True, exist_ok=True)

# ── Models ─────────────────────────────────────────
MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

# Cost per 1M tokens (USD) — used by Token Manager
MODEL_COSTS = {
    "claude-haiku-4-5-20251001":  {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6":          {"input": 3.00, "output": 15.00},
    "claude-opus-4-6":            {"input": 15.00, "output": 75.00},
}

# ── Orchestrator ───────────────────────────────────
HEARTBEAT_INTERVAL = 10
HEARTBEAT_TIMEOUT = 60
MAX_AGENT_RESTARTS = 5
INTERNET_CHECK_URL = "https://api.anthropic.com"
INTERNET_CHECK_INTERVAL = 30

# ── Agent defaults ─────────────────────────────────
DEFAULT_TICK_INTERVAL = 60
DASHBOARD_PORT = 8050

# ── Core agents to register at startup ─────────────
CORE_AGENTS = [
    {
        "name": "token_manager",
        "module_path": "agents.token_manager",
        "class_name": "TokenManager",
        "config": {"tick_interval": 60},
        "can_spawn_children": False,
    },
    {
        "name": "model_router",
        "module_path": "agents.model_router",
        "class_name": "ModelRouter",
        "config": {"tick_interval": 30},
        "can_spawn_children": False,
    },
    {
        "name": "data_agent",
        "module_path": "agents.data_agent",
        "class_name": "DataAgent",
        "config": {"tick_interval": 300},
        "can_spawn_children": False,
    },
    {
        "name": "backtest_runner",
        "module_path": "agents.backtest_runner",
        "class_name": "BacktestRunner",
        "config": {"tick_interval": 5},
        "can_spawn_children": False,
    },
    {
        "name": "strategy_factory",
        "module_path": "agents.strategy_factory",
        "class_name": "StrategyFactory",
        "config": {"tick_interval": 300},
        "can_spawn_children": False,
    },
    {
        "name": "template_factory",
        "module_path": "agents.template_factory",
        "class_name": "TemplateFactory",
        "config": {"tick_interval": 15, "batch_size": 20},
        "can_spawn_children": False,
    },
    {
        "name": "evolution_agent",
        "module_path": "agents.evolution_agent",
        "class_name": "EvolutionAgent",
        "config": {"tick_interval": 60},
        "can_spawn_children": False,
    },
    {
        "name": "plugin_scout",
        "module_path": "agents.plugin_scout",
        "class_name": "PluginScout",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
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
    # ── Tier 1: Quality & Robustness ──────────────────
    {
        "name": "regime_filter",
        "module_path": "agents.regime_filter",
        "class_name": "RegimeFilter",
        "config": {"tick_interval": 120},
        "can_spawn_children": False,
    },
    {
        "name": "monte_carlo",
        "module_path": "agents.monte_carlo",
        "class_name": "MonteCarlo",
        "config": {"tick_interval": 300, "n_simulations": 10000},
        "can_spawn_children": False,
    },
    {
        "name": "correlation_agent",
        "module_path": "agents.correlation_agent",
        "class_name": "CorrelationAgent",
        "config": {"tick_interval": 600},
        "can_spawn_children": False,
    },
    {
        "name": "ensemble_agent",
        "module_path": "agents.ensemble_agent",
        "class_name": "EnsembleAgent",
        "config": {"tick_interval": 900},
        "can_spawn_children": False,
    },
    # ── Tier 2: Anti-overfitting ──────────────────────
    {
        "name": "sensitivity_agent",
        "module_path": "agents.sensitivity_agent",
        "class_name": "SensitivityAgent",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
    {
        "name": "news_calendar",
        "module_path": "agents.news_calendar",
        "class_name": "NewsCalendarAgent",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
    {
        "name": "multi_timeframe",
        "module_path": "agents.multi_timeframe",
        "class_name": "MultiTimeframeAgent",
        "config": {"tick_interval": 300},
        "can_spawn_children": False,
    },
    # ── Tier 3: Live Trading & Reporting ──────────────
    {
        "name": "signal_gatekeeper",
        "module_path": "agents.signal_gatekeeper",
        "class_name": "SignalGatekeeper",
        "config": {"tick_interval": 120},
        "can_spawn_children": False,
    },
    {
        "name": "risk_manager",
        "module_path": "agents.risk_manager",
        "class_name": "RiskManager",
        "config": {"tick_interval": 30},
        "can_spawn_children": False,
    },
    {
        "name": "paper_trade",
        "module_path": "agents.paper_trade",
        "class_name": "PaperTradeAgent",
        "config": {"tick_interval": 60},
        "can_spawn_children": False,
    },
    {
        "name": "trade_supervisor",
        "module_path": "agents.trade_supervisor",
        "class_name": "TradeSupervisor",
        "config": {"tick_interval": 30},
        "can_spawn_children": False,
    },
    {
        "name": "report_agent",
        "module_path": "agents.report_agent",
        "class_name": "ReportAgent",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
    # ── Tier 4: Learning & Optimization ──────────────
    {
        "name": "param_optimizer",
        "module_path": "agents.param_optimizer",
        "class_name": "ParamOptimizer",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
    {
        "name": "strategy_analyzer",
        "module_path": "agents.strategy_analyzer",
        "class_name": "StrategyAnalyzer",
        "config": {"tick_interval": 300},
        "can_spawn_children": False,
    },
    # ── Tier 5: Memory & Knowledge ───────────────────
    {
        "name": "knowledge_base_agent",
        "module_path": "agents.knowledge_base_agent",
        "class_name": "KnowledgeBaseAgent",
        "config": {"tick_interval": 120},
        "can_spawn_children": False,
    },
]

# ── Knowledge Base (Obsidian vault) ───────────────
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"

# ── Backtest defaults ──────────────────────────────
INITIAL_BALANCE = 50.0
PIP_VALUE = 100.0
DEFAULT_RISK_PCT = 0.04  # Monte Carlo validated: max safe risk for WR<50% strategies
MIN_LOT = 0.01
MAX_LOT = 100.0
DEFAULT_SPREAD = 0.35
SLIPPAGE_PER_FILL = 0.05

# ── Validation thresholds (M1) ─────────────────────
MIN_WIN_RATE = 0.62
MIN_PROFIT_FACTOR = 2.0
MAX_DRAWDOWN = 0.35
MIN_X10_COUNT = 5
MIN_TRADES = 200
MIN_REGIMES = 3

# ── Validation thresholds (M5) ─────────────────────
# MIN_TRADES 100: with ~11k strategies tested on the same dataset, small
# samples pass by pure chance (multiple-testing bias). A 60% WR over 5
# trades is a coin flip; over 100 trades it is evidence of an edge.
M5_MIN_WIN_RATE = 0.60
M5_MIN_PROFIT_FACTOR = 1.3
M5_MAX_DRAWDOWN = 0.25
M5_MIN_X10_COUNT = 0
M5_MIN_TRADES = 100
M5_MIN_REGIMES = 2

# ── Probation tier ─────────────────────────────────
# Strategies with a small sample but EXCEPTIONAL quality pass validation on
# probation: stricter bars compensate the small n, and they trade at reduced
# size until live trades complete the missing sample. The win-rate lower
# bound (95%) naturally scales the bar with sample size: 38 trades need
# ~68% WR to prove they beat a coin flip; 80 trades only need ~62%.
PROBATION_MIN_TRADES = 30
# PF 1.6 (was 2.0): the WR lower bound below is the real statistical guard —
# it already scales the required win rate by sample size. An extra PF>=2.0
# cap on top was discarding genuine edges (PF 1.5-2.0, WR-LB > 50%, holdout
# survivors) that deploy safely at quarter-lot with live graduation.
PROBATION_MIN_PF = 1.6        # vs 1.3 for full validation
PROBATION_MAX_DD = 0.20       # vs 0.25 for full validation
PROBATION_MIN_WR_LB = 0.50    # 95% lower confidence bound on WR must beat 50%
PROBATION_HOLDOUT_MIN_TRADES = 5   # holdout has ~1/5 of the data
PROBATION_HOLDOUT_MIN_PF = 1.0     # must at least not lose on the holdout

# ── Final holdout (never used for selection) ───────
# The last N months of data are excluded from validation and walk-forward.
# A strategy is only deployable if it also survives on this untouched slice.
HOLDOUT_MONTHS = 6
HOLDOUT_MIN_PF = 1.2
HOLDOUT_MIN_TRADES = 15

# ── Family robustness gate (deployment filter) ─────
# A single passing variant means little when thousands are generated; a
# family is only trusted once several variants with real samples confirm it.
FAMILY_MIN_TESTED = 5      # variants with >=100 trades needed to judge a family
FAMILY_MIN_GOOD_RATIO = 0.4  # fraction of those with PF >= 1.1 to allow deploys

# ── Portfolio diversification (execution-time) ─────
# Cap concurrent open trades per template family: variants of one family
# fire on the same market conditions, so stacking them multiplies one bet.
FAMILY_MAX_OPEN = 2

# ── Edge decay defense: periodic re-validation ─────
# Deployed strategies are re-run through the full gauntlet every N days
# against the (daily-refreshed) dataset. An edge that stops working on
# recent data gets undeployed before it bleeds the account.
REVALIDATION_DAYS = 7

# ── Backtest vs live divergence tracking ───────────
# After enough live trades, a strategy whose live results fall too far
# below its backtest is auto-suspended (regime drift or overfit remnant).
DIVERGENCE_MIN_TRADES = 20    # live trades before judging
DIVERGENCE_MAX_WR_DROP = 0.15  # live WR > 15 points below backtest WR → suspend
DIVERGENCE_MIN_PF_RATIO = 0.5  # live PF < 50% of backtest PF → suspend
