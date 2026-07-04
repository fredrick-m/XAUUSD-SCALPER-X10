# ENS_VOTE_027

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 16:40:13

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
  "method": "vote",
  "component_ids": [
    "ENS_VOTE_006",
    "ENS_WEIGHTED_006",
    "c007"
  ],
  "weights": {
    "ENS_VOTE_006": 8.1739,
    "ENS_WEIGHTED_006": 8.1739,
    "c007": 6.7682
  },
  "avg_sl_atr": 2.0585,
  "avg_tp_atr": 2.7506,
  "monte_carlo": {
    "median_dd": 0.0562,
    "p95_dd": 0.1076,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7996,
    "best_htf": null,
    "best_pf": 0.7996,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.7634,
        "wr": 0.4898,
        "trades": 49,
        "improvement": 0.9547
      },
      "M15": {
        "pf": 0.7871,
        "wr": 0.5088,
        "trades": 57,
        "improvement": 0.9844
      },
      "H1": {
        "pf": 0.9483,
        "wr": 0.5538,
        "trades": 65,
        "improvement": 1.186
      }
    }
  }
}
```

## Links
- [[ENS_VOTE_027 Backtest]]
