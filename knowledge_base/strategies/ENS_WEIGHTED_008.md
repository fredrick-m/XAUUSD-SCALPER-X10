# ENS_WEIGHTED_008

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:35:13

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
    "median_dd": 0.0705,
    "p95_dd": 0.1196,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.9334,
    "best_htf": null,
    "best_pf": 0.9334,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.8036,
        "wr": 0.5094,
        "trades": 53,
        "improvement": 0.8609
      },
      "M15": {
        "pf": 0.828,
        "wr": 0.5306,
        "trades": 49,
        "improvement": 0.8871
      },
      "H1": {
        "pf": 0.9975,
        "wr": 0.5652,
        "trades": 46,
        "improvement": 1.0687
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_008",
  "redundant_cluster": [
    "ENS_VOTE_008",
    "ENS_WEIGHTED_008"
  ],
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 1.582,
    "robustness_score": 0.9253,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.3148,
          "pf": 1.1108,
          "wr": 0.5385,
          "pf_ratio": 0.7021
        },
        {
          "factor": 0.8,
          "value": 1.5026,
          "pf": 1.0074,
          "wr": 0.4923,
          "pf_ratio": 0.6368
        },
        {
          "factor": 0.9,
          "value": 1.6905,
          "pf": 1.0557,
          "wr": 0.4923,
          "pf_ratio": 0.6673
        },
        {
          "factor": 1.1,
          "value": 2.0661,
          "pf": 1.5598,
          "wr": 0.5385,
          "pf_ratio": 0.986
        },
        {
          "factor": 1.2,
          "value": 2.254,
          "pf": 1.535,
          "wr": 0.5231,
          "pf_ratio": 0.9703
        },
        {
          "factor": 1.3,
          "value": 2.4418,
          "pf": 1.5711,
          "wr": 0.5077,
          "pf_ratio": 0.9931
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 1.8435,
          "pf": 1.4224,
          "wr": 0.5231,
          "pf_ratio": 0.8991
        },
        {
          "factor": 0.8,
          "value": 2.1068,
          "pf": 1.5116,
          "wr": 0.5231,
          "pf_ratio": 0.9555
        },
        {
          "factor": 0.9,
          "value": 2.3702,
          "pf": 1.4765,
          "wr": 0.5231,
          "pf_ratio": 0.9333
        },
        {
          "factor": 1.1,
          "value": 2.8969,
          "pf": 1.6112,
          "wr": 0.5231,
          "pf_ratio": 1.0185
        },
        {
          "factor": 1.2,
          "value": 3.1602,
          "pf": 1.61,
          "wr": 0.5231,
          "pf_ratio": 1.0177
        },
        {
          "factor": 1.3,
          "value": 3.4236,
          "pf": 1.6882,
          "wr": 0.5231,
          "pf_ratio": 1.0671
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 1.4944,
          "wr": 0.4923,
          "pf_ratio": 0.9446
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 1.5417,
          "wr": 0.5077,
          "pf_ratio": 0.9745
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 1.5837,
          "wr": 0.5231,
          "pf_ratio": 1.0011
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 1.5881,
          "wr": 0.5077,
          "pf_ratio": 1.0039
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 1.4908,
          "wr": 0.4923,
          "pf_ratio": 0.9424
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 1.4916,
          "wr": 0.4923,
          "pf_ratio": 0.9429
        }
      ]
    }
  }
}
```

## Links
- [[ENS_WEIGHTED_008 Backtest]]
