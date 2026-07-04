# ENS_VOTE_009

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:36:47

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
    "median_dd": 0.0594,
    "p95_dd": 0.108,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.8649,
    "best_htf": null,
    "best_pf": 0.8649,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.8825,
        "wr": 0.5246,
        "trades": 61,
        "improvement": 1.0203
      },
      "M15": {
        "pf": 0.8431,
        "wr": 0.5231,
        "trades": 65,
        "improvement": 0.9748
      },
      "H1": {
        "pf": 1.0062,
        "wr": 0.5522,
        "trades": 67,
        "improvement": 1.1634
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
- [[ENS_VOTE_009 Backtest]]
