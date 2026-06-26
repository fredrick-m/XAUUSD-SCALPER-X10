# G001 — RSI Pullback Discovery

**Date** : 2026-06-25
**Importance** : MAJEURE

## Decouverte

Nouvelle famille de strategies decorrelees de D008v2:
- **D008v2** : WR=35.8%, PF=1.40, TP large (4.0 ATR) — profit sur peu de trades gagnants
- **G001** : WR=63.8%, PF=1.47, TP serre (2.0 ATR) — profit sur beaucoup de trades gagnants

## Logique G001

EMA(8) > EMA(21) > EMA(50) stacked 20+ bars (meme filtre que D008v2)
+ RSI descend entre 25 et 40 dans le trend haussier = pullback confirme
+ RSI monte entre 60 et 75 dans le trend baissier = rebond confirme

## Resultats

| Config | Trades | WR | PF | DD | Balance |
|--------|--------|-----|-----|-----|---------|
| risk=5% | 69 | 63.8% | 1.46 | 21.8% | $81 |
| risk=10% | 69 | 63.8% | 1.47 | 42.5% | $117 |
| risk=15% | 69 | 63.8% | 1.41 | 58.4% | $134 |

## Regle Decouverte

> **RSI < 40 dans un trend confirme = signal d'achat haute probabilite.**
> Mais SEULEMENT avec EMA stack 20+ bars. Sans le filtre, RSI < 40 donne PF = 0.54.

## F-Series : 5 strategies testees, toutes echouent

| Strat | Concept | Signaux | PF | Raison echec |
|-------|---------|---------|-----|--------------|
| F001 | Momentum breakout | 773 | 0.35 | Trop de signaux |
| F002 | RSI divergence | 395 | 0.36 | Signaux anti-predictifs |
| F003 | Bollinger squeeze | 1571 | 0.62 | Beaucoup trop de signaux |
| F004 | VWAP reversion | 996 | 0.78 | Trop de signaux |
| F005 | Keltner + ADX | 1183 | 0.62 | Trop de signaux |

> **Confirmation** : sans filtre EMA-stack, AUCUN indicateur standard ne fonctionne seul.
> L'edge est dans la COMBINAISON EMA-stack + indicateur selectif.

## Liens
- [[D008v2 - ATR Expansion Trend]]
- [[M5 Breakthrough]]
- [[Philosophie — Amelioration Continue]]
