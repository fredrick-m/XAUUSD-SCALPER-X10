# ENS_WEIGHTED_005

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:23:35

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
  "method": "weighted",
  "component_ids": [
    "c007",
    "T01769",
    "T00836"
  ],
  "weights": {
    "c007": 6.7682,
    "T01769": 4.8155,
    "T00836": 2.6619
  },
  "avg_sl_atr": 1.9535,
  "avg_tp_atr": 3.0157,
  "monte_carlo": {
    "median_dd": 0.1026,
    "p95_dd": 0.1753,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.7042,
    "best_htf": null,
    "best_pf": 0.7042,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.9692,
        "wr": 0.4925,
        "trades": 67,
        "improvement": 1.3763
      },
      "M15": {
        "pf": 0.8981,
        "wr": 0.5135,
        "trades": 74,
        "improvement": 1.2753
      },
      "H1": {
        "pf": 0.8362,
        "wr": 0.4762,
        "trades": 84,
        "improvement": 1.1874
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
  ],
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 0.6469,
    "robustness_score": 0.9757,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.3674,
          "pf": 0.422,
          "wr": 0.4,
          "pf_ratio": 0.6523
        },
        {
          "factor": 0.8,
          "value": 1.5628,
          "pf": 0.5296,
          "wr": 0.3929,
          "pf_ratio": 0.8187
        },
        {
          "factor": 0.9,
          "value": 1.7582,
          "pf": 0.5416,
          "wr": 0.4206,
          "pf_ratio": 0.8372
        },
        {
          "factor": 1.1,
          "value": 2.1489,
          "pf": 1.0326,
          "wr": 0.4811,
          "pf_ratio": 1.5962
        },
        {
          "factor": 1.2,
          "value": 2.3442,
          "pf": 0.6417,
          "wr": 0.4569,
          "pf_ratio": 0.992
        },
        {
          "factor": 1.3,
          "value": 2.5396,
          "pf": 0.6338,
          "wr": 0.4261,
          "pf_ratio": 0.9797
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 2.111,
          "pf": 0.5926,
          "wr": 0.4348,
          "pf_ratio": 0.9161
        },
        {
          "factor": 0.8,
          "value": 2.4126,
          "pf": 0.6135,
          "wr": 0.4261,
          "pf_ratio": 0.9484
        },
        {
          "factor": 0.9,
          "value": 2.7141,
          "pf": 0.6253,
          "wr": 0.4138,
          "pf_ratio": 0.9666
        },
        {
          "factor": 1.1,
          "value": 3.3173,
          "pf": 0.646,
          "wr": 0.4087,
          "pf_ratio": 0.9986
        },
        {
          "factor": 1.2,
          "value": 3.6188,
          "pf": 0.6163,
          "wr": 0.4052,
          "pf_ratio": 0.9527
        },
        {
          "factor": 1.3,
          "value": 3.9204,
          "pf": 0.6167,
          "wr": 0.4052,
          "pf_ratio": 0.9533
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 0.6719,
          "wr": 0.4397,
          "pf_ratio": 1.0386
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 0.6706,
          "wr": 0.431,
          "pf_ratio": 1.0366
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 0.6211,
          "wr": 0.4138,
          "pf_ratio": 0.9601
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 0.6142,
          "wr": 0.4138,
          "pf_ratio": 0.9495
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 0.6518,
          "wr": 0.4174,
          "pf_ratio": 1.0076
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 0.6196,
          "wr": 0.4087,
          "pf_ratio": 0.9578
        }
      ]
    }
  }
}
```

## Links
- [[ENS_WEIGHTED_005 Backtest]]
