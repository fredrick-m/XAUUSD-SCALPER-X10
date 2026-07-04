# ENS_WEIGHTED_021

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 15:19:28

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
    "median_dd": 0.1238,
    "p95_dd": 0.2324,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.8967,
    "best_htf": null,
    "best_pf": 0.8967,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.8775,
        "wr": 0.5783,
        "trades": 83,
        "improvement": 0.9786
      },
      "M15": {
        "pf": 0.6987,
        "wr": 0.5211,
        "trades": 71,
        "improvement": 0.7792
      },
      "H1": {
        "pf": 0.8661,
        "wr": 0.5636,
        "trades": 55,
        "improvement": 0.9659
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_003",
  "redundant_cluster": [
    "T01471",
    "ENS_VOTE_003",
    "ENS_WEIGHTED_003",
    "ENS_VOTE_010",
    "ENS_WEIGHTED_010",
    "ENS_VOTE_017",
    "ENS_WEIGHTED_017",
    "ENS_VOTE_020",
    "ENS_WEIGHTED_020",
    "ENS_VOTE_021",
    "ENS_WEIGHTED_021"
  ]
}
```

## Links
- [[ENS_WEIGHTED_021 Backtest]]
