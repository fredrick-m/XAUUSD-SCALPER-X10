# ENS_WEIGHTED_022

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 16:31:36

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
  "monte_carlo": {
    "median_dd": 0.2046,
    "p95_dd": 0.4031,
    "p_x10": 0.0,
    "p_ruin": 0.0001,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.567,
    "best_htf": "M15",
    "best_pf": 0.716,
    "improvement": 1.2628,
    "htf_results": {
      "M5": {
        "pf": 0.7031,
        "wr": 0.4825,
        "trades": 315,
        "improvement": 1.24
      },
      "M15": {
        "pf": 0.716,
        "wr": 0.4918,
        "trades": 305,
        "improvement": 1.2628
      },
      "H1": {
        "pf": 0.7035,
        "wr": 0.4694,
        "trades": 294,
        "improvement": 1.2407
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_022",
  "redundant_cluster": [
    "ENS_VOTE_001",
    "ENS_WEIGHTED_001",
    "ENS_VOTE_022",
    "ENS_WEIGHTED_022"
  ]
}
```

## Links
- [[ENS_WEIGHTED_022 Backtest]]
