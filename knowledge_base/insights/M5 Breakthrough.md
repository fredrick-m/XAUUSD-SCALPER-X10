# M5 Breakthrough

**Date** : 2026-06-25
**Importance** : CRITIQUE

## Probleme
M1 XAUUSD est mathematiquement unviable avec spread $0.35 sur compte $50.
- Spread $0.40/trade mange 15.5% du risque ($2.50 a 5%)
- 2200+ strategies testees sur M1 → TOUTES echouent
- Meme les signaux aleatoires performent mieux que nos indicateurs sur M1

## Decouverte
En resampant les donnees M1 en **M5**, le spread impact passe de 15.5% a 6.5%.
- M1 ATR(14) moyen : $1.29
- M5 ATR(14) moyen : $3.06
- Ratio : 2.4x → spread proportionnellement 2.4x plus petit

## Preuve
[[D008v2 - ATR Expansion Trend]] sur M5 :
- PF = 1.40 (vs 0.78 sur M1)
- $50 → $263 (+425%) a risk=5%
- $50 → $420 (+740%) a risk=12%
- 193 trades sur 3 ans

## Regle
> **TOUTES les futures strategies doivent cibler M5, pas M1.**

## Liens
- [[Selectivite des Signaux]]
- [[D008v2 - ATR Expansion Trend]]
- [[Parametres Optimaux M5]]
