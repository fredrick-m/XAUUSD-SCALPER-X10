# ENS_VOTE_018

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 15:12:10

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
    "median_dd": 0.1449,
    "p95_dd": 0.2714,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.6389,
    "best_htf": null,
    "best_pf": 0.6389,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.9098,
        "wr": 0.5361,
        "trades": 97,
        "improvement": 1.424
      },
      "M15": {
        "pf": 0.7587,
        "wr": 0.5208,
        "trades": 96,
        "improvement": 1.1875
      },
      "H1": {
        "pf": 0.7537,
        "wr": 0.4839,
        "trades": 93,
        "improvement": 1.1797
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_012",
  "redundant_cluster": [
    "T00836",
    "ENS_VOTE_005",
    "ENS_WEIGHTED_005",
    "ENS_VOTE_012",
    "ENS_WEIGHTED_012",
    "ENS_VOTE_018",
    "ENS_WEIGHTED_018"
  ]
}
```

## Links
- [[ENS_VOTE_018 Backtest]]
