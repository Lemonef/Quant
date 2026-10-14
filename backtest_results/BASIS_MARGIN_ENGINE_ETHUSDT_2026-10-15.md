# ETHUSDT basis carry — MARGIN ENGINE (capital-adjusted) — 2026-10-15

Same entry/exit as basis_carry_v2 (DTE-5 exit, FULL contracts). Each contract walked day by day under a collateral policy fixed EX ANTE. Liquidation trigger = futures daily HIGH vs entry >= c - maint (0.5%); on liquidation the collateral is lost, a 1.0% fee charged and spot unwound at that close. Return is on TOTAL capital tied up = spot notional + collateral. Hurdle = cash yield 4.5%/yr. Daily high is a proxy for mark price, so liquidation counts are a LOWER bound.

Contracts: 7 · unlevered headline from v2 (return on spot notional only): **+10.5%/yr**

| policy | capital per $1 notional | liquidated | mean return ON CAPITAL /yr | worst contract | beats cash? |
|---|---|---|---|---|---|
| isolated, c=0.25 | $1.25 | 4/7 | +5.3% | -14.3% | ✅ |
| isolated, c=0.50 | $1.50 | 3/7 | -0.0% | -24.6% | ❌ |
| isolated, c=1.00 | $2.00 | 0/7 | +5.3% | +2.6% | ✅ |
| isolated, c=1.50 | $2.50 | 0/7 | +4.2% | +2.1% | ❌ |
| isolated, c=2.00 | $3.00 | 0/7 | +3.5% | +1.7% | ❌ |
| portfolio margin (upper bound) | $1.10 | 0/7 (modelled) | +9.6% | +4.7% | ✅ |

## Per contract — max adverse move on the short leg

| contract | entry | days | adverse high | liq c=0.25 | liq c=0.5 | liq c=1.0 | liq c=1.5 | liq c=2.0 |
|---|---|---|---|---|---|---|---|---|
| 240329 | 2023-11-10 | 135 | +90.7% | ⚠ | ⚠ | – | – | – |
| 240628 | 2023-12-30 | 176 | +77.9% | ⚠ | ⚠ | – | – | – |
| 240927 | 2024-03-30 | 176 | +7.5% | – | – | – | – | – |
| 241227 | 2024-06-29 | 176 | +16.1% | – | – | – | – | – |
| 250328 | 2024-09-28 | 176 | +53.9% | ⚠ | ⚠ | – | – | – |
| 250627 | 2024-12-28 | 176 | +12.0% | – | – | – | – | – |
| 251226 | 2025-07-20 | 154 | +37.3% | ⚠ | – | – | – | – |

## Reading it

- Smallest collateral that survived EVERY contract: **c = 1.00** -> $2.00 of capital per $1 of carry, returning **+5.3%/yr on capital** vs cash 4.5%. Note this c is chosen with hindsight of the worst path; an honest operator sizes ABOVE it.
- Portfolio margin would return +9.6%/yr on capital — IF the venue offers it to this account and counts the spot leg as collateral. That is an access question, not a backtest one.
