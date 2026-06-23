# ROADMAP — XAUUSD-SCALPER-X10

## Phase 1: Data Collection

**Goal:** Acquire clean, reliable XAUUSD M1 historical data covering multiple market regimes.

### Tasks
- [ ] Identify and configure data source (broker feed, Dukascopy, FXCM, or MetaTrader export)
- [ ] Download minimum 2 years of XAUUSD M1 OHLCV data
- [ ] Label market regimes: trend (up/down), range, high volatility
- [ ] Validate data quality: gaps, spikes, timezone alignment
- [ ] Store cleaned data in `data/processed/`

**Exit Criteria:** Clean M1 dataset with regime labels, ≥ 2 years, < 0.1% bad bars.

---

## Phase 2: Strategy Generation

**Goal:** Generate candidate scalping strategies with theoretical edge on XAUUSD M1.

### Tasks
- [ ] Define strategy universe: entry signals (momentum, mean-reversion, breakout, order flow proxy)
- [ ] Define exit framework: fixed TP/SL, trailing stop, time-based exit
- [ ] Parameterize each strategy class into testable configurations
- [ ] Implement strategies in `strategies/`
- [ ] Run fast pre-screening (Sharpe > 1, Win Rate > 60%) to eliminate obvious losers

**Exit Criteria:** ≥ 20 candidate strategies passing pre-screening.

---

## Phase 3: Backtesting & Validation

**Goal:** Identify strategies meeting all validation criteria across multiple regimes.

### Tasks
- [ ] Build backtesting engine or configure existing framework (e.g., Backtrader, vectorbt, custom)
- [ ] Run full backtest per strategy per regime period
- [ ] Score each run: Win Rate, Profit Factor, Max Drawdown, x10 achieved y/n
- [ ] Select strategies achieving x10 ≥ 5 times across ≥ 3 regime types
- [ ] Run walk-forward validation on top candidates
- [ ] Document results in `backtests/` and `reports/`

**Exit Criteria:** ≥ 1 strategy validated to full criteria (all 5 metrics met, x10 × 5, 3 regimes).

---

## Phase 4: Live Trading

**Goal:** Deploy validated strategy in live or paper trading environment.

### Tasks
- [ ] Set up execution environment (MT4/MT5, IBKR, or broker API)
- [ ] Implement risk management layer (position sizing, daily drawdown circuit breaker)
- [ ] Paper trade for minimum 5 trading days with real-time data
- [ ] Monitor performance vs. backtest benchmarks
- [ ] Go live with minimum capital, track daily P&L
- [ ] Document live results and flag any regime drift

**Exit Criteria:** Live paper results within ±15% of backtest expectations over 5 days; green-light for real capital.

---

## Status

| Phase | Status | Owner |
|---|---|---|
| Phase 1: Data Collection | Not Started | TBD |
| Phase 2: Strategy Generation | Not Started | TBD |
| Phase 3: Backtesting & Validation | Not Started | TBD |
| Phase 4: Live Trading | Not Started | TBD |

*Last updated: 2026-03-28*
