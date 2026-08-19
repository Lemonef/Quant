# ETHUSDT quarterly basis carry — v2 (post-critique) — 2026-08-19

**Headline class: short basis / liquidity tail-risk premium (not alpha).** Signal on close t, fill next-bar OPEN both legs. Hurdle: (entry basis − 0.5% terminal allowance − 0.66% round-trip) annualized > 5%. Futures legs costed at 0.22%/leg (2× haircut), spot 0.11%. Exit family (3, 5, 7, 10) + hold; verdict on FULL-history contracts (first bar ≥ DTE 60); PARTIAL bucket shown apart. Liquidation flags = daily-HIGH proxy for the short leg at 3x/5x isolated with 0.5% maintenance (intraday marks are WORSE — a real margin engine is the gauntlet's job).

## Exit family (FULL contracts)

| exit DTE | n | positive | mean ann net | CI95 | worst | OOS≥2024 | LOYO min | liq@3x | liq@5x | max adverse (short leg, high) |
|---|---|---|---|---|---|---|---|---|---|---|
| 3 | 7 | 7/7 | +10.5% | [+7.2%, +14.5%] | +2.025% | +10.5% | +8.1% | 4 | 4 | +90.7% |
| 5 | 7 | 7/7 | +10.5% | [+7.2%, +14.6%] | +1.922% | +10.5% | +8.1% | 4 | 4 | +90.7% |
| 7 | 7 | 7/7 | +10.5% | [+7.1%, +14.7%] | +1.703% | +10.5% | +8.2% | 4 | 4 | +90.7% |
| 10 | 7 | 7/7 | +10.3% | [+6.6%, +14.7%] | +1.158% | +10.3% | +8.3% | 4 | 4 | +90.7% |
| hold | 7 | 7/7 | +10.6% | [+7.5%, +14.5%] | +2.442% | +10.6% | +8.0% | 4 | 4 | +90.7% |

Worst-of-family mean ann net (the headline): **+10.3%/yr unlevered**

## Per-contract (DTE 5 exit)

| contract | bucket | entry | DTE | basis@sig | gross | net | net ann | adverse close/high | liq3 | liq5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 240329 | full | 2023-11-10 | 140 | +3.16% | +2.582% | +1.922% | +5.2% | +89.3%/+90.7% | ⚠ | ⚠ |
| 240628 | full | 2023-12-30 | 181 | +7.48% | +7.233% | +6.573% | +13.6% | +76.6%/+77.9% | ⚠ | ⚠ |
| 240927 | full | 2024-03-30 | 181 | +10.69% | +10.619% | +9.959% | +20.7% | +6.9%/+7.5% | – | – |
| 241227 | full | 2024-06-29 | 181 | +5.60% | +5.404% | +4.744% | +9.8% | +13.6%/+16.1% | – | – |
| 250328 | full | 2024-09-28 | 181 | +4.07% | +3.953% | +3.293% | +6.8% | +50.7%/+53.9% | ⚠ | ⚠ |
| 250627 | full | 2024-12-28 | 181 | +6.19% | +6.092% | +5.432% | +11.3% | +10.3%/+12.0% | – | – |
| 251226 | full | 2025-07-20 | 159 | +3.35% | +3.283% | +2.623% | +6.2% | +33.5%/+37.3% | ⚠ | ⚠ |

Never qualified (hurdle not met): 230331, 230630, 230929, 231229, 250926, 260327, 260626 · PARTIAL-history contracts: 0

## VERDICT (FULL contracts, family-worst): **PASS → prereg + full gauntlet (margin engine, execution depth, funding-carry overlap, Thai access) BEFORE any shadow**

Blockers still OPEN regardless of verdict (Codex #2/#3): real margin/liquidation engine on mark prices; Binance USD-M delivery-futures access for a Thai retail account (owner must verify). Not a sleeve until both close.