# ENS_WEIGHTED_002

**Status** : candidate
**Family** : ensemble
**Timeframe** : M5
**Generation** : 1
**Created by** : ensemble_agent
**Created** : 2026-06-28 14:12:48

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
    "T01736"
  ],
  "weights": {
    "c007": 6.7682,
    "T01769": 4.8155,
    "T01736": 2.9218
  },
  "avg_sl_atr": 1.8924,
  "avg_tp_atr": 2.8974,
  "monte_carlo": {
    "median_dd": 0.0496,
    "p95_dd": 0.091,
    "p_x10": 0.0,
    "p_ruin": 0.0,
    "n_simulations": 10000
  },
  "monte_carlo_tested": true,
  "mtf_tested": true,
  "multi_timeframe": {
    "baseline_pf": 0.8225,
    "best_htf": null,
    "best_pf": 0.8225,
    "improvement": 1.0,
    "htf_results": {
      "M5": {
        "pf": 0.7559,
        "wr": 0.5306,
        "trades": 49,
        "improvement": 0.919
      },
      "M15": {
        "pf": 0.8264,
        "wr": 0.56,
        "trades": 50,
        "improvement": 1.0047
      },
      "H1": {
        "pf": 0.9797,
        "wr": 0.5918,
        "trades": 49,
        "improvement": 1.1911
      }
    }
  },
  "redundant": true,
  "redundant_of": "ENS_VOTE_002",
  "redundant_cluster": [
    "ENS_VOTE_002",
    "ENS_WEIGHTED_002"
  ],
  "sensitivity_tested": true,
  "sensitivity": {
    "baseline_pf": 0.8225,
    "robustness_score": 0.9831,
    "is_fragile": false,
    "param_results": {
      "sl_atr": [
        {
          "factor": 0.7,
          "value": 1.3247,
          "pf": 0.7257,
          "wr": 0.5634,
          "pf_ratio": 0.8823
        },
        {
          "factor": 0.8,
          "value": 1.5139,
          "pf": 0.69,
          "wr": 0.493,
          "pf_ratio": 0.8389
        },
        {
          "factor": 0.9,
          "value": 1.7032,
          "pf": 0.6651,
          "wr": 0.493,
          "pf_ratio": 0.8086
        },
        {
          "factor": 1.1,
          "value": 2.0816,
          "pf": 0.8596,
          "wr": 0.507,
          "pf_ratio": 1.0451
        },
        {
          "factor": 1.2,
          "value": 2.2709,
          "pf": 0.8069,
          "wr": 0.507,
          "pf_ratio": 0.981
        },
        {
          "factor": 1.3,
          "value": 2.4601,
          "pf": 0.9726,
          "wr": 0.507,
          "pf_ratio": 1.1825
        }
      ],
      "tp_atr": [
        {
          "factor": 0.7,
          "value": 2.0282,
          "pf": 0.8396,
          "wr": 0.5211,
          "pf_ratio": 1.0208
        },
        {
          "factor": 0.8,
          "value": 2.3179,
          "pf": 0.7993,
          "wr": 0.5211,
          "pf_ratio": 0.9718
        },
        {
          "factor": 0.9,
          "value": 2.6077,
          "pf": 0.8283,
          "wr": 0.5211,
          "pf_ratio": 1.0071
        },
        {
          "factor": 1.1,
          "value": 3.1871,
          "pf": 0.8248,
          "wr": 0.5211,
          "pf_ratio": 1.0028
        },
        {
          "factor": 1.2,
          "value": 3.4769,
          "pf": 0.8686,
          "wr": 0.5211,
          "pf_ratio": 1.056
        },
        {
          "factor": 1.3,
          "value": 3.7666,
          "pf": 0.8832,
          "wr": 0.5211,
          "pf_ratio": 1.0738
        }
      ],
      "atr_period": [
        {
          "factor": 0.7,
          "value": 10,
          "pf": 0.7785,
          "wr": 0.493,
          "pf_ratio": 0.9465
        },
        {
          "factor": 0.8,
          "value": 11,
          "pf": 0.7585,
          "wr": 0.4789,
          "pf_ratio": 0.9222
        },
        {
          "factor": 0.9,
          "value": 13,
          "pf": 0.7719,
          "wr": 0.5211,
          "pf_ratio": 0.9385
        },
        {
          "factor": 1.1,
          "value": 15,
          "pf": 0.8396,
          "wr": 0.507,
          "pf_ratio": 1.0208
        },
        {
          "factor": 1.2,
          "value": 17,
          "pf": 0.8217,
          "wr": 0.507,
          "pf_ratio": 0.999
        },
        {
          "factor": 1.3,
          "value": 18,
          "pf": 0.8204,
          "wr": 0.507,
          "pf_ratio": 0.9974
        }
      ]
    }
  }
}
```

## Links
- [[ENS_WEIGHTED_002 Backtest]]
