# ENS_VOTE_017

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 15:10:07

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
    "median_dd": 0.1466,
    "p95_dd": 0.277,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.6655,
    "best_htf": null,
    "best_pf": 0.6655,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.6631,
        "wr": 0.49,
        "trades": 100,
        "improvement": 0.9964
      },
      "M15": {
        "pf": 0.5799,
        "wr": 0.4767,
        "trades": 86,
        "improvement": 0.8714
      },
      "H1": {
        "pf": 0.6819,
        "wr": 0.5072,
        "trades": 69,
        "improvement": 1.0246
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
- [[ENS_VOTE_017 Backtest]]
