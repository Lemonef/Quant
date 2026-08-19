# BTCUSDT quarterly basis carry — v2 (post-critique) — 2026-08-19

**Headline class: short basis / liquidity tail-risk premium (not alpha).** Signal on close t, fill next-bar OPEN both legs. Hurdle: (entry basis − 0.5% terminal allowance − 0.66% round-trip) annualized > 5%. Futures legs costed at 0.22%/leg (2× haircut), spot 0.11%. Exit family (3, 5, 7, 10) + hold; verdict on FULL-history contracts (first bar ≥ DTE 60); PARTIAL bucket shown apart. Liquidation flags = daily-HIGH proxy for the short leg at 3x/5x isolated with 0.5% maintenance (intraday marks are WORSE — a real margin engine is the gauntlet's job).

## Exit family (FULL contracts)

| exit DTE | n | positive | mean ann net | CI95 | worst | OOS≥2024 | LOYO min | liq@3x | liq@5x | max adverse (short leg, high) |
|---|---|---|---|---|---|---|---|---|---|---|
| 3 | 8 | 8/8 | +10.2% | [+7.2%, +14.0%] | +2.360% | +10.2% | +7.9% | 4 | 4 | +105.0% |
| 5 | 8 | 8/8 | +10.3% | [+7.2%, +14.0%] | +2.253% | +10.3% | +7.9% | 4 | 4 | +105.0% |
| 7 | 8 | 8/8 | +10.2% | [+7.1%, +14.1%] | +1.782% | +10.2% | +8.1% | 4 | 4 | +105.0% |
| 10 | 8 | 8/8 | +10.1% | [+6.9%, +14.2%] | +1.536% | +10.1% | +8.1% | 4 | 4 | +105.0% |
| hold | 8 | 8/8 | +10.3% | [+7.4%, +14.0%] | +2.646% | +10.3% | +7.8% | 4 | 4 | +105.0% |

Worst-of-family mean ann net (the headline): **+10.1%/yr unlevered**

## Per-contract (DTE 5 exit)

| contract | bucket | entry | DTE | basis@sig | gross | net | net ann | adverse close/high | liq3 | liq5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 240329 | full | 2023-11-02 | 148 | +3.26% | +2.913% | +2.253% | +5.8% | +102.1%/+105.0% | ⚠ | ⚠ |
| 240628 | full | 2023-12-30 | 181 | +7.42% | +7.190% | +6.530% | +13.5% | +72.6%/+75.2% | ⚠ | ⚠ |
| 240927 | full | 2024-03-30 | 181 | +10.98% | +10.869% | +10.209% | +21.2% | +4.9%/+5.1% | – | – |
| 241227 | full | 2024-06-29 | 181 | +5.83% | +5.443% | +4.783% | +9.9% | +66.6%/+70.3% | ⚠ | ⚠ |
| 250328 | full | 2024-09-28 | 181 | +4.55% | +4.481% | +3.821% | +7.9% | +60.6%/+63.9% | ⚠ | ⚠ |
| 250627 | full | 2024-12-28 | 181 | +6.23% | +6.152% | +5.492% | +11.4% | +12.3%/+16.0% | – | – |
| 251226 | full | 2025-07-14 | 165 | +3.46% | +3.388% | +2.728% | +6.2% | +3.5%/+4.5% | – | – |
| 260327 | full | 2025-09-27 | 181 | +3.68% | +3.595% | +2.935% | +6.1% | +13.9%/+16.5% | – | – |

Never qualified (hurdle not met): 230331, 230630, 230929, 231229, 250926, 260626 · PARTIAL-history contracts: 0

## VERDICT (FULL contracts, family-worst): **PASS → prereg + full gauntlet (margin engine, execution depth, funding-carry overlap, Thai access) BEFORE any shadow**

Blockers still OPEN regardless of verdict (Codex #2/#3): real margin/liquidation engine on mark prices; Binance USD-M delivery-futures access for a Thai retail account (owner must verify). Not a sleeve until both close.