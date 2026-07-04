# ENS_WEIGHTED_004

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:19:59

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
    "median_dd": 0.0964,
    "p95_dd": 0.172,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7648,
    "best_htf": null,
    "best_pf": 0.7648,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.5959,
        "wr": 0.4714,
        "trades": 70,
        "improvement": 0.7792
      },
      "M15": {
        "pf": 0.6629,
        "wr": 0.5,
        "trades": 64,
        "improvement": 0.8668
      },
      "H1": {
        "pf": 0.9364,
        "wr": 0.5667,
        "trades": 60,
        "improvement": 1.2244
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_007",
  "redundant_cluster": [
    "ENS_VOTE_004",
    "ENS_WEIGHTED_004",
    "ENS_VOTE_007",
    "ENS_WEIGHTED_007"
  ],
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 0.7648,
    "robustness_score": 0.9317,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.4412,
          "pf": 0.6243,
          "wr": 0.4691,
          "pf_ratio": 0.8163
        },
        {
          "factor": 0.8,
          "value": 1.6471,
          "pf": 0.6044,
          "wr": 0.4568,
          "pf_ratio": 0.7903
        },
        {
          "factor": 0.9,
          "value": 1.853,
          "pf": 0.7236,
          "wr": 0.4938,
          "pf_ratio": 0.9461
        },
        {
          "factor": 1.1,
          "value": 2.2648,
          "pf": 0.6821,
          "wr": 0.4691,
          "pf_ratio": 0.8919
        },
        {
          "factor": 1.2,
          "value": 2.4707,
          "pf": 0.6461,
          "wr": 0.4321,
          "pf_ratio": 0.8448
        },
        {
          "factor": 1.3,
          "value": 2.6766,
          "pf": 0.5912,
          "wr": 0.4444,
          "pf_ratio": 0.773
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 2.1195,
          "pf": 0.7855,
          "wr": 0.5185,
          "pf_ratio": 1.0271
        },
        {
          "factor": 0.8,
          "value": 2.4222,
          "pf": 0.737,
          "wr": 0.4938,
          "pf_ratio": 0.9637
        },
        {
          "factor": 0.9,
          "value": 2.725,
          "pf": 0.7431,
          "wr": 0.4938,
          "pf_ratio": 0.9716
        },
        {
          "factor": 1.1,
          "value": 3.3306,
          "pf": 0.7602,
          "wr": 0.4938,
          "pf_ratio": 0.994
        },
        {
          "factor": 1.2,
          "value": 3.6334,
          "pf": 0.7875,
          "wr": 0.4938,
          "pf_ratio": 1.0297
        },
        {
          "factor": 1.3,
          "value": 3.9361,
          "pf": 0.8017,
          "wr": 0.4938,
          "pf_ratio": 1.0482
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 0.6909,
          "wr": 0.4691,
          "pf_ratio": 0.9034
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 0.6592,
          "wr": 0.4568,
          "pf_ratio": 0.8619
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 0.7303,
          "wr": 0.4815,
          "pf_ratio": 0.9549
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 0.765,
          "wr": 0.4938,
          "pf_ratio": 1.0003
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 0.7556,
          "wr": 0.4938,
          "pf_ratio": 0.988
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 0.7382,
          "wr": 0.4938,
          "pf_ratio": 0.9652
        }
      ]
    }
  }
}
```

## Links
- [[ENS_WEIGHTED_004 Backtest]]
