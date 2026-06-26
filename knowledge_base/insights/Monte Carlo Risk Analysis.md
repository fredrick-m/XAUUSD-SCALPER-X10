# Monte Carlo Risk Analysis

**Date** : 2026-06-26
**Importance** : CRITIQUE

## Decouverte

Le risk sizing est aussi important que la strategie elle-meme. I003 (PF=1.62) passe de VIABLE a RUINE selon le % risque par trade.

### I003 — Monte Carlo 10,000 simulations

| Risk | PF | DD | Balance | P(x10) | P(Ruin) | Verdict |
|------|----|----|---------|--------|---------|---------|
| 2% | 1.51 | 15.9% | $125 | 0% | 0% | SAFE |
| 3% | 1.55 | 19.9% | $194 | 0% | 0.1% | SAFE |
| **4%** | **1.56** | **26.4%** | **$264** | **0%** | **1.7%** | **OPTIMAL** |
| 5% | 1.61 | 31.2% | $392 | 0% | 9.3% | BORDERLINE |
| 6% | 1.63 | 36.3% | $545 | 78.9% | 21.1% | RISQUE |
| 10% | 1.62 | 54.0% | $1,377 | 39.5% | 60.5% | RUINE |
| 15% | 1.53 | 73.3% | $1,741 | 29.1% | 70.9% | SUICIDE |

## Regle

> **Risk par trade = 4% maximum pour les strategies a WR < 50%**
> **Au-dessus de 6%, P(Ruin) > 20% — inacceptable pour du capital reel**

## Mecanisme

Avec WR=44.7%, on a 104 pertes pour 84 gains. Les sequences de pertes consecutives sont longues. A 10% risk, 7 pertes consécutives = -70% du capital. Monte Carlo montre que dans 60% des ordonnements possibles, ces sequences detruisent le compte.

## Impact

Le backtest montre $1,377 a 10% risk, mais c'est trompeur — on voit UNE sequence historique. Monte Carlo montre les 10,000 sequences possibles, et 60% d'entre elles menent a la ruine.

A 4% risk, on obtient $264 (5.3x) avec seulement 1.7% de chance de ruine. C'est le compromis rendement/survie optimal.

## Liens
- [[I003 — OR Logic Strategy]]
- [[Trailing Stop Rule]]
- [[Selectivite des Signaux]]
