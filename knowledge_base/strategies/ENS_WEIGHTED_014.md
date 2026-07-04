# ENS_WEIGHTED_014

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 15:05:39

## Best Results
| Metric | Value |
|--------|-------|
| Win Rate | — |
| Profit Factor | — |
| Max Drawdown | — |
| x10 Count | 0 |
| Final Balance | — |

## Parameters
```json
{
  "method": "weighted",
  "component_ids": [
    "c007",
    "T01736",
    "T01798"
  ],
  "weights": {
    "c007": 6.7682,
    "T01736": 2.9218,
    "T01798": 2.5823
  },
  "avg_sl_atr": 2.0266,
  "avg_tp_atr": 3.2068,
  "monte_carlo": {
    "median_dd": 0.0776,
    "p95_dd": 0.1432,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.5485,
    "best_htf": null,
    "best_pf": 0.5485,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.5986,
        "wr": 0.4746,
        "trades": 59,
        "improvement": 1.0913
      },
      "M15": {
        "pf": 0.6478,
        "wr": 0.5,
        "trades": 56,
        "improvement": 1.181
      },
      "H1": {
        "pf": 0.8072,
        "wr": 0.549,
        "trades": 51,
        "improvement": 1.4716
      }
    }
  }
}
```

## Links
- [[ENS_WEIGHTED_014 Backtest]]
