# System Insights (Auto-Generated)

**Last Updated** : 2026-06-25T14:00:00
**Strategies Analyzed** : 2280
**Total Backtests** : 0

## Key Insights
1. M1 ATR(14) avg $1.29 makes spread ($0.40) eat 15.5% of risk - fatal for any strategy
2. M5 ATR(14) avg $3.06 reduces spread drag to 6.5% - strategies become viable
3. RSI mean reversion + trend filter produces highest WR (73% on M1, profitable on M5)
4. Optimal R:R on M5 is sl_atr=2.0 / tp_atr=3.0 (PF=1.59)
5. 10% risk on M5 doubles the final balance vs 5% risk with manageable DD (50%)
6. Trailing stop has zero effect on PF - not worth the complexity
7. Strategies with sl_atr < 1.5 always blow account regardless of timeframe
8. All 2000+ EMA crossover strategies are random noise - zero predictive edge
9. Cooldowns of 15-25 M5 bars needed to generate 200+ trades over 3 years of data

## Failure Modes
| Mode | Count |
|------|-------|
| spread_drag | 2200 |
| random_signals | 2100 |
| low_wr_with_high_rr | 1800 |
| too_few_trades | 50 |
| high_wr_with_low_rr | 10 |

## Links
- [[M5 Breakthrough]]
- [[Philosophie — Amelioration Continue]]
