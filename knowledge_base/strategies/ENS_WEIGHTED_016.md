# ENS_WEIGHTED_016

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 15:09:15

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
    "median_dd": 0.0589,
    "p95_dd": 0.1071,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7043,
    "best_htf": null,
    "best_pf": 0.7043,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 1.021,
        "wr": 0.5814,
        "trades": 43,
        "improvement": 1.4497
      },
      "M15": {
        "pf": 0.737,
        "wr": 0.5098,
        "trades": 51,
        "improvement": 1.0464
      },
      "H1": {
        "pf": 0.9417,
        "wr": 0.549,
        "trades": 51,
        "improvement": 1.3371
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_016",
  "redundant_cluster": [
    "T01450",
    "ENS_VOTE_009",
    "ENS_WEIGHTED_009",
    "ENS_VOTE_016",
    "ENS_WEIGHTED_016"
  ]
}
```

## Links
- [[ENS_WEIGHTED_016 Backtest]]
