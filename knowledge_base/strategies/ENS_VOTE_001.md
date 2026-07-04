# ENS_VOTE_001

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:06:39

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
    "c007",
    "T01769",
    "T01736",
    "T01471",
    "T02136",
    "T00836",
    "T00903",
    "T01798",
    "T01021",
    "T01450",
    "T01698",
    "T00725",
    "T01884",
    "T02150",
    "T00844"
  ],
  "weights": {
    "c007": 6.7682,
    "T01769": 4.8155,
    "T01736": 2.9218,
    "T01471": 2.7698,
    "T02136": 2.7017,
    "T00836": 2.6619,
    "T00903": 2.6287,
    "T01798": 2.5823,
    "T01021": 2.4392,
    "T01450": 2.231,
    "T01698": 2.1818,
    "T00725": 2.1013,
    "T01884": 1.7752,
    "T02150": 1.693,
    "T00844": 1.3428
  },
  "avg_sl_atr": 1.9965,
  "avg_tp_atr": 2.8811,
  "monte_carlo": {
    "median_dd": 0.2066,
    "p95_dd": 0.3885,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.6608,
    "best_htf": "M5",
    "best_pf": 0.7132,
    "improvement": 1.0793,
    "htf_results": {
      "M5": {
        "pf": 0.7132,
        "wr": 0.4965,
        "trades": 288,
        "improvement": 1.0793
      },
      "M15": {
        "pf": 0.6695,
        "wr": 0.4928,
        "trades": 278,
        "improvement": 1.0132
      },
      "H1": {
        "pf": 0.6783,
        "wr": 0.4692,
        "trades": 260,
        "improvement": 1.0265
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_022",
  "redundant_cluster": [
    "ENS_VOTE_001",
    "ENS_WEIGHTED_001",
    "ENS_VOTE_022",
    "ENS_WEIGHTED_022"
  ],
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 0.6608,
    "robustness_score": 0.9384,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.3975,
          "pf": 0.3961,
          "wr": 0.4371,
          "pf_ratio": 0.5994
        },
        {
          "factor": 0.8,
          "value": 1.5972,
          "pf": 0.4323,
          "wr": 0.4327,
          "pf_ratio": 0.6542
        },
        {
          "factor": 0.9,
          "value": 1.7969,
          "pf": 0.555,
          "wr": 0.4504,
          "pf_ratio": 0.8399
        },
        {
          "factor": 1.1,
          "value": 2.1962,
          "pf": 0.7295,
          "wr": 0.4741,
          "pf_ratio": 1.104
        },
        {
          "factor": 1.2,
          "value": 2.3958,
          "pf": 0.6376,
          "wr": 0.4395,
          "pf_ratio": 0.9649
        },
        {
          "factor": 1.3,
          "value": 2.5955,
          "pf": 0.6717,
          "wr": 0.4474,
          "pf_ratio": 1.0165
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 2.0168,
          "pf": 0.7357,
          "wr": 0.4928,
          "pf_ratio": 1.1133
        },
        {
          "factor": 0.8,
          "value": 2.3049,
          "pf": 0.7099,
          "wr": 0.4783,
          "pf_ratio": 1.0743
        },
        {
          "factor": 0.9,
          "value": 2.593,
          "pf": 0.642,
          "wr": 0.4595,
          "pf_ratio": 0.9715
        },
        {
          "factor": 1.1,
          "value": 3.1692,
          "pf": 0.5886,
          "wr": 0.4465,
          "pf_ratio": 0.8907
        },
        {
          "factor": 1.2,
          "value": 3.4573,
          "pf": 0.5908,
          "wr": 0.4465,
          "pf_ratio": 0.8941
        },
        {
          "factor": 1.3,
          "value": 3.7454,
          "pf": 0.5883,
          "wr": 0.4477,
          "pf_ratio": 0.8903
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 0.7549,
          "wr": 0.473,
          "pf_ratio": 1.1424
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 0.6237,
          "wr": 0.4435,
          "pf_ratio": 0.9439
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 0.6325,
          "wr": 0.4571,
          "pf_ratio": 0.9572
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 0.5934,
          "wr": 0.4478,
          "pf_ratio": 0.898
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 0.6,
          "wr": 0.4529,
          "pf_ratio": 0.908
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 0.6802,
          "wr": 0.4617,
          "pf_ratio": 1.0294
        }
      ]
    }
  }
}
```

## Links
- [[ENS_VOTE_001 Backtest]]
