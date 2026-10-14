# BTCUSDT basis carry — MARGIN ENGINE (capital-adjusted) — 2026-10-15

Same entry/exit as basis_carry_v2 (DTE-5 exit, FULL contracts). Each contract walked day by day under a collateral policy fixed EX ANTE. Liquidation trigger = futures daily HIGH vs entry >= c - maint (0.5%); on liquidation the collateral is lost, a 1.0% fee charged and spot unwound at that close. Return is on TOTAL capital tied up = spot notional + collateral. Hurdle = cash yield 4.5%/yr. Daily high is a proxy for mark price, so liquidation counts are a LOWER bound.

Contracts: 8 · unlevered headline from v2 (return on spot notional only): **+10.3%/yr**

| policy | capital per $1 notional | liquidated | mean return ON CAPITAL /yr | worst contract | beats cash? |
|---|---|---|---|---|---|
| isolated, c=0.25 | $1.25 | 4/8 | +2.4% | -28.8% | ❌ |
| isolated, c=0.50 | $1.50 | 4/8 | +2.0% | -12.3% | ❌ |
| isolated, c=1.00 | $2.00 | 1/8 | +5.1% | +2.9% | ✅ |
| isolated, c=1.50 | $2.50 | 0/8 | +4.1% | +2.3% | ❌ |
| isolated, c=2.00 | $3.00 | 0/8 | +3.4% | +1.9% | ❌ |
| portfolio margin (upper bound) | $1.10 | 0/8 (modelled) | +9.3% | +5.2% | ✅ |

## Per contract — max adverse move on the short leg

| contract | entry | days | adverse high | liq c=0.25 | liq c=0.5 | liq c=1.0 | liq c=1.5 | liq c=2.0 |
|---|---|---|---|---|---|---|---|---|
| 240329 | 2023-11-02 | 143 | +105.0% | ⚠ | ⚠ | ⚠ | – | – |
| 240628 | 2023-12-30 | 176 | +75.2% | ⚠ | ⚠ | – | – | – |
| 240927 | 2024-03-30 | 176 | +5.1% | – | – | – | – | – |
| 241227 | 2024-06-29 | 176 | +70.3% | ⚠ | ⚠ | – | – | – |
| 250328 | 2024-09-28 | 176 | +63.9% | ⚠ | ⚠ | – | – | – |
| 250627 | 2024-12-28 | 176 | +16.0% | – | – | – | – | – |
| 251226 | 2025-07-14 | 160 | +4.5% | – | – | – | – | – |
| 260327 | 2025-09-27 | 176 | +16.5% | – | – | – | – | – |

## Reading it

- Smallest collateral that survived EVERY contract: **c = 1.50** -> $2.50 of capital per $1 of carry, returning **+4.1%/yr on capital** vs cash 4.5%. Note this c is chosen with hindsight of the worst path; an honest operator sizes ABOVE it.
- Portfolio margin would return +9.3%/yr on capital — IF the venue offers it to this account and counts the spot leg as collateral. That is an access question, not a backtest one.
