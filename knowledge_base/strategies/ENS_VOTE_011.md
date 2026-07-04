# ENS_VOTE_011

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:50:04

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
    "median_dd": 0.1011,
    "p95_dd": 0.1828,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.5864,
    "best_htf": null,
    "best_pf": 0.5864,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.5975,
        "wr": 0.5,
        "trades": 54,
        "improvement": 1.0189
      },
      "M15": {
        "pf": 0.6388,
        "wr": 0.5283,
        "trades": 53,
        "improvement": 1.0894
      },
      "H1": {
        "pf": 0.8498,
        "wr": 0.5957,
        "trades": 47,
        "improvement": 1.4492
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_WEIGHTED_014",
  "redundant_cluster": [
    "T00844",
    "T02136",
    "T01884",
    "T01798",
    "ENS_VOTE_011",
    "ENS_WEIGHTED_011",
    "ENS_VOTE_014",
    "ENS_WEIGHTED_014",
    "T02494",
    "T02839"
  ]
}
```

## Links
- [[ENS_VOTE_011 Backtest]]
