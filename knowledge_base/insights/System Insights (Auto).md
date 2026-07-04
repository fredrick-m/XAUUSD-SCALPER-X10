# System Insights (Auto-Generated)

**Last Updated** : 2026-07-04T21:33:58.781164+00:00
**Strategies Analyzed** : 1819
**Total Backtests** : 2314

## Key Insights
1. Strategies with sl_atr < 4.0 have never achieved PF >= 1.0
2. Strategies with sl_atr < 1.5 always blow account — spread drag dominates
3. Optimal SL bucket: sl_atr ~4.0 yields highest average PF
4. Optimal TP bucket: tp_atr ~3.5 yields highest average PF
5. Best family: 'ensemble' — avg PF 2.37, avg WR 67.1%
6. Worst family: 'hybrid_ichimoku_rsi' — avg PF 0.37, avg WR 21.5%
7. Family 'parabolic_sar' has high PF variance (std=0.61) — results are unstable, needs parameter narrowing
8. Family 'rsi_bb_combo' has high PF variance (std=0.69) — results are unstable, needs parameter narrowing
9. Family 'mean_reversion_bb' has high PF variance (std=0.57) — results are unstable, needs parameter narrowing
10. Family 'regression_break' has high PF variance (std=1.27) — results are unstable, needs parameter narrowing
11. Family 'supertrend' has high PF variance (std=0.62) — results are unstable, needs parameter narrowing
12. Family 'hybrid_supertrend_rsi' has high PF variance (std=0.75) — results are unstable, needs parameter narrowing
13. Family 'rsi_pullback' has high PF variance (std=0.59) — results are unstable, needs parameter narrowing
14. Family 'dual_rsi' has high PF variance (std=1.66) — results are unstable, needs parameter narrowing
15. Family 'gap_scalping' has high PF variance (std=0.69) — results are unstable, needs parameter narrowing
16. Family 'ensemble' has high PF variance (std=1.07) — results are unstable, needs parameter narrowing
17. Family 'trend_reversal' has high PF variance (std=1.48) — results are unstable, needs parameter narrowing
18. Dominant failure mode: 'high_dd' — 493/930 (53%) of failing strategies

## Family Performance
| Family | Count | Avg PF | Avg WR | Max PF | % Profitable |
|--------|-------|--------|--------|--------|-------------|
| ensemble | 52 | 2.37 | 67.1% | 4.85 | 100% |
| ema_stack_rsi_m5_v2 | 1 | 1.91 | 63.2% | 1.91 | 100% |
| ema_bounce | 1 | 1.63 | 41.8% | 1.63 | 100% |
| ema_stack_rsi_m5 | 1 | 1.56 | 59.7% | 1.56 | 100% |
| dual_rsi | 70 | 1.53 | 46.7% | 9.96 | 61% |
| supertrend | 176 | 1.45 | 51.8% | 4.24 | 80% |
| hybrid_vol_rsi_bb | 1 | 1.38 | 54.1% | 1.38 | 100% |
| hybrid_supertrend_rsi | 171 | 1.33 | 50.3% | 5.96 | 73% |
| gap_scalping | 58 | 1.25 | 48.2% | 2.83 | 59% |
| trend_reversal | 14 | 1.24 | 48.8% | 5.78 | 33% |
| regression_break | 54 | 1.22 | 48.3% | 9.60 | 50% |
| volume_spike | 38 | 1.21 | 48.7% | 2.55 | 78% |
| squeeze_momentum | 16 | 1.16 | 53.4% | 1.76 | 69% |
| williams_percent_r | 3 | 1.14 | 37.4% | 1.14 | 100% |
| rsi_bb_combo | 206 | 1.14 | 46.0% | 6.65 | 55% |
| hybrid_fib_macd | 5 | 1.09 | 40.9% | 1.09 | 100% |
| mean_reversion_bb | 43 | 1.08 | 42.1% | 2.77 | 60% |
| range_trading | 7 | 1.04 | 48.6% | 1.71 | 57% |
| rsi_macd_dual | 123 | 1.03 | 43.9% | 2.38 | 46% |
| rsi_pin_bar | 154 | 1.02 | 43.8% | 3.60 | 51% |
| bb_squeeze | 51 | 1.02 | 40.6% | 1.83 | 57% |
| vwap_deviation | 36 | 1.00 | 43.6% | 1.52 | 36% |
| rsi_pullback | 152 | 0.98 | 42.5% | 4.28 | 37% |
| multi_tf_rsi | 142 | 0.95 | 42.4% | 3.05 | 37% |
| macd_momentum | 1 | 0.93 | 51.0% | 0.93 | 0% |
| adx_breakout | 39 | 0.92 | 41.6% | 2.16 | 36% |
| or_logic_rsi_atr | 26 | 0.92 | 41.4% | 1.43 | 54% |
| market_profile | 56 | 0.92 | 39.0% | 2.60 | 38% |
| momentum_breakout | 52 | 0.88 | 38.0% | 1.88 | 46% |
| adx_trend | 122 | 0.86 | 40.7% | 3.74 | 27% |
| liquidity_sweep | 129 | 0.85 | 40.6% | 1.48 | 33% |
| multi_tf_ema | 3 | 0.84 | 46.8% | 0.86 | 0% |
| parabolic_sar | 42 | 0.82 | 38.8% | 3.41 | 22% |
| inside_bar | 29 | 0.78 | 39.6% | 1.29 | 14% |
| triple_ema_pullback | 3 | 0.78 | 40.3% | 0.78 | 0% |
| hybrid_session_volume | 68 | 0.77 | 35.5% | 1.54 | 28% |
| london_open | 28 | 0.76 | 37.1% | 1.70 | 18% |
| engulfing_candle | 32 | 0.75 | 38.3% | 1.25 | 22% |
| fake_breakout | 5 | 0.75 | 42.0% | 0.82 | 0% |
| bollinger_breakout | 3 | 0.74 | 36.9% | 0.74 | 0% |
| hybrid_rsi_stoch | 6 | 0.73 | 37.2% | 0.91 | 0% |
| momentum_roc | 47 | 0.65 | 35.0% | 2.05 | 13% |
| atr_expansion | 8 | 0.61 | 31.2% | 0.73 | 0% |
| rsi_divergence_m5 | 1 | 0.53 | 19.7% | 0.53 | 0% |
| ny_open | 28 | 0.46 | 28.4% | 1.30 | 4% |
| stochastic_cross | 3 | 0.43 | 22.7% | 0.43 | 0% |
| hybrid_ichimoku_rsi | 8 | 0.37 | 21.5% | 0.76 | 0% |

## Optimal Parameter Ranges
- **Min viable SL** : 4.0
- **Optimal SL range** : [4.0, 4.0]
- **Optimal TP range** : [3.5, 3.5]
- **Best SL bucket** : 4.0
- **Best TP bucket** : 3.5
- **Sample size** : 1

## Failure Modes
| Mode | Count |
|------|-------|
| high_dd | 493 |
| too_few_trades | 436 |
| low_wr | 1 |

## Links
- [[M5 Breakthrough]]
- [[Philosophie — Amelioration Continue]]
