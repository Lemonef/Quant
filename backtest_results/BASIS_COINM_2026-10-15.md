# COIN-M inverse quarterly basis carry — 2026-10-15

## Preregistration (declared before downloading / calculating results)

Hypothesis: BTC collateral and an inverse BTCUSD quarterly short with USD face
N = Q * F_entry remove the separate USDT margin capital drag, survive at 1x,
and earn the basis on capital Q * S_entry. This is a basis/liquidity risk premium.

Kill line, identical to v2: FULL contracts, worst-of-exit-family mean annualized
net > MIN_NET_ANN (5%) AND >=80% positive at DTE5 AND DTE5 contract-bootstrap
CI lower bound >0 AND leave-one-delivery-year-out means all >0. Additional gate:
worst-of-family USD return ON CAPITAL beats 4.5% cash, and no observed 1x
liquidation. Missing exit-family evidence fails the test.

Universe: last-Friday quarterly deliveries from 2021 through 2026, settled at
least seven days before fixed as-of 2026-10-15 (same universe rule as v2).
Signal: first close t with DTE >=21 and
(F_close/S_close - 1 - 0.5% terminal allowance - 0.62% cost allowance)
*365/DTE >5%. Fill both legs at the NEXT CALENDAR DAY open, entry DTE >=20.
No signal retuning after observing results. DTE exits 3/5/7/10 and hold (DTE0).
Annualization is simple net*365/actual days, contract-equal mean, 10,000
contract bootstrap draws (seed 20260724), LOYO and pre/post-2024 split.
These are trade-period rates, not a compounded portfolio CAGR; no idle-cash
return, reinvestment or simultaneous-contract portfolio is claimed.

FULL requires first common spot/future bar at least DTE60 AND uninterrupted
daily data from that bar through delivery. Missing or late coverage is PARTIAL;
never interpolate, forward-fill, or move a fill to a later available bar.
PARTIAL results are descriptive only and unknown liquidation paths stay unknown.

Costs: spot inherits [v2's cost configuration](../backtest/alpha_factory/config.py)
and [cost model](../backtest/basis_carry_v2.py): assumed 0.06% fee +0.05% slippage, 0.11% per leg;
this is the repository cost assumption, not a verified regular-user spot tier.
COIN-M taker 0.05% +0.05% slippage, doubled together to 0.20% per futures leg,
following v2's 2x haircut convention. No maker rebate, VIP/BNB discount, funding
or borrowing. Fees/slippage are cash haircuts, not additional fill-price shifts.
Use a frozen fee assumption across history; no historical fee ledger available.
The [official calculation example](https://www.binance.com/en-NZ/support/faq/detail/360033544231) supports BTC fee = N/F * rate and
0.05% taker; the [current schedule](https://www.binance.com/en/fee/deliveryFee) did not expose populated rows
to the browser, so an account-specific current/historical rate is unverified.

Mechanics: [Binance quarterly specifications](https://www.binance.bh/en-AE/support/faq/detail/d33f37e2c7fe4da3b35ffc904e8fbab5) give $100 face,
BTC collateral/settlement, and inverse PnL. Short PnL = contracts*$100*
(1/F_exit - 1/F_entry), valued in USD at exit SPOT, never at exit futures.
Choose an even integer contract count floor(F_entry/200)*2 and set
Q=contracts*$100/F_entry (approximately one BTC); hedge is exact, no fractional
contracts. Capital = Q*S_entry, with no extra USDT. Q is the gross BTC purchase;
spot-entry haircut Q*spot_cost and futures-entry haircut N/F_entry*fut_cost
are deducted from this same BTC pool. Entry costs thus slightly undercollateralize
the ideal pre-fee 1x hedge. BTC_end = Q - entry costs + inverse PnL -
N/F_exit*fut_cost; final spot-sale cost deducts BTC_end*spot_cost.
USD net = BTC_end_after_sale*S_exit/(Q*S_entry)-1;
BTC net = BTC_end_after_sale/Q-1 (USD-hedged wealth expressed in BTC).

Margin: same Q BTC, short N=L*Q*F_entry for L=1/1.5/2; only 1x is USD neutral.
Walk every held daily HIGH and exit-day OPEN (exit-day high occurs after exit
and is excluded, correcting v2's path endpoint). High of last-traded contract
is a conservative adverse MARK proxy, not a guaranteed bound on true marks.
Equity_BTC = Q - spot-entry cost - futures-entry cost + N*(1/M-1/F_entry).
Margin ratio = maintenance_BTC/equity_BTC; equity<=0 or ratio>=100% triggers.
Also report a conservative liquidation count reserving the full 0.20% futures
exit haircut: (maintenance+N/M*fut_cost)/equity>=100%.
No liquidation-damaged leveraged return is passed off as a carry return.

Maintenance uses the [published 2021 BTC quarterly tier table](https://www.binance.com/en/support/announcement/detail/7c000aa897f74e59bf285ca05dccb1a6),
frozen across this sample, with [cumulative bracket calculation](https://www.binance.com/en-AU/support/faq/detail/be2c7d9d95b04a7e8044ed02dd7dfe5c):
BTC-value caps 10/20/30/50/100/200/400/1000/infinity; marginal rates
0.4/0.5/1/2.5/5/10/12.5/15/25%. This is an explicit historical-tier assumption,
not proof of each expired contract's contemporaneous account brackets.
Report the maximum observed position BTC value/tier; results apply to the
declared ~1 BTC scale. Include a 1% maintenance sensitivity at 1x.

Hold is v2's delivery-day 00:00 UTC OPEN proxy, not actual 08:00 settlement or
the index's final-hour average. It pays the same taker+slippage haircut as a
normal close; no additional double settlement fee. Delivery settlement details
are in the specifications link. USDT spot is treated as USD (no depeg/FX model).

## Exit family (FULL, 1x)

| DTE | n | USD positive | USD mean ann ROC | BTC mean ann | USD CI95 | worst USD net | pre-2024 | post-2024 | LOYO min |
|---|---|---|---|---|---|---|---|---|---|
| 3 | 10 | 10/10 | +10.00% | -16.38% | [+7.06%, +13.85%] | +1.989% | +6.33% | +10.41% | +7.66% |
| 5 | 10 | 10/10 | +10.01% | -15.18% | [+7.03%, +13.90%] | +1.930% | +5.97% | +10.46% | +7.56% |
| 7 | 10 | 10/10 | +10.11% | -15.42% | [+7.08%, +14.03%] | +1.946% | +6.19% | +10.54% | +7.75% |
| 10 | 10 | 10/10 | +10.11% | -15.48% | [+7.01%, +14.19%] | +1.674% | +6.54% | +10.51% | +7.81% |
| hold proxy | 10 | 10/10 | +9.99% | -15.62% | [+7.09%, +13.79%] | +2.150% | +6.38% | +10.39% | +7.59% |

**Family-worst USD ROC: +10.00%/yr.** DTE5 LOYO: drop 2023: +10.46%, drop 2024: +7.56%, drop 2025: +11.18%, drop 2026: +10.42%

## Every contract (DTE5; PARTIAL never enters the verdict)

| contract | bucket/status | entry → exit | DTE entry | signal basis | actual entry basis | gross USD | net USD | USD ann ROC | BTC net / ann | inverse PnL BTC / USD | capital USD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 210326 | PARTIAL: NO SPOT OVERLAP | — | — | — | — | — | — | — | — | — | — |
| 210625 | PARTIAL: NO SPOT OVERLAP | — | — | — | — | — | — | — | — | — | — |
| 210924 | PARTIAL: NO SPOT OVERLAP | — | — | — | — | — | — | — | — | — | — |
| 211231 | PARTIAL: NO SPOT OVERLAP | — | — | — | — | — | — | — | — | — | — |
| 220325 | PARTIAL: NO SPOT OVERLAP | — | — | — | — | — | — | — | — | — | — |
| 220624 | PARTIAL: NO SPOT OVERLAP | — | — | — | — | — | — | — | — | — | — |
| 220930 | PARTIAL: NO SPOT OVERLAP | — | — | — | — | — | — | — | — | — | — |
| 221230 | PARTIAL: NO SPOT OVERLAP | — | — | — | — | — | — | — | — | — | — |
| 230331 | FULL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 230630 | FULL | 2023-02-27 → 2023-06-25 | 123 | +2.84% | +2.83% | +2.649% | +1.930% | +5.97% | -21.35% / -66.04% | -0.207769 / -6342.65 | 23532.97 |
| 230929 | PARTIAL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 231229 | PARTIAL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 240329 | FULL | 2023-10-31 → 2024-03-24 | 150 | +3.22% | +3.26% | +2.994% | +2.100% | +5.29% | -44.99% / -113.26% | -0.442658 / -28325.72 | 34284.05 |
| 240628 | FULL | 2023-12-30 → 2024-06-23 | 181 | +7.83% | +7.80% | +7.680% | +6.874% | +14.26% | -30.04% / -62.30% | -0.294156 / -18903.09 | 41931.41 |
| 240927 | FULL | 2024-03-30 → 2024-09-22 | 181 | +12.57% | +12.56% | +12.402% | +11.772% | +24.41% | +23.24% / +48.20% | +0.239298 / +15159.26 | 69828.32 |
| 241227 | FULL | 2024-06-29 → 2024-12-22 | 181 | +6.25% | +6.25% | +6.046% | +5.219% | +10.82% | -34.65% / -71.86% | -0.341337 / -33209.39 | 60425.77 |
| 250328 | FULL | 2024-09-28 → 2025-03-23 | 181 | +5.13% | +5.15% | +5.011% | +4.291% | +8.90% | -18.19% / -37.72% | -0.175825 / -14741.24 | 65621.21 |
| 250627 | FULL | 2024-12-28 → 2025-06-22 | 181 | +6.56% | +6.56% | +6.454% | +5.789% | +12.01% | -2.31% / -4.80% | -0.016973 / -1733.29 | 94221.42 |
| 250926 | FULL | 2025-04-10 → 2025-09-21 | 169 | +3.63% | +3.63% | +3.442% | +2.688% | +5.98% | -26.67% / -59.35% | -0.261243 / -30222.04 | 82601.52 |
| 251226 | FULL | 2025-07-13 → 2025-12-21 | 166 | +3.44% | +3.46% | +3.282% | +2.729% | +6.19% | +36.51% / +82.78% | +0.372212 / +32888.95 | 117336.49 |
| 260327 | FULL | 2025-09-27 → 2026-03-22 | 181 | +3.64% | +3.60% | +3.557% | +3.042% | +6.31% | +63.93% / +132.59% | +0.646427 / +44550.52 | 109458.42 |
| 260626 | FULL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 260925 | FULL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |

USD losers (DTE5, including PARTIAL): none.
BTC losses are listed explicitly above; BTC-denominated loss does not imply USD carry loss.

## PARTIAL exit family (descriptive)

| DTE | entered | positive USD | USD mean ann | BTC mean ann |
|---|---|---|---|---|
| 3 | 0 | — | — | — |
| 5 | 0 | — | — | — |
| 7 | 0 | — | — | — |
| 10 | 0 | — | — | — |
| hold proxy | 0 | — | — | — |

## Liquidation by leverage (observed paths; ratio threshold 100%)

| bucket / exit | leverage | paths | maintenance-only hits | with exit-cost reserve | peak raw margin ratio | peak reserved ratio | max BTC position value | max tier |
|---|---|---|---|---|---|---|---|---|---|
| FULL / 3 | 1x | 10 | 0 | 0 | 0.40% | 0.60% | 1.7426 | 1 |
| FULL / 3 | 1.5x | 10 | 0 | 0 | 1.38% | 2.07% | 2.6140 | 1 |
| FULL / 3 | 2x | 10 | 1 | 1 | inf% | inf% | 3.4853 | 1 |
| FULL / 5 | 1x | 10 | 0 | 0 | 0.40% | 0.60% | 1.7426 | 1 |
| FULL / 5 | 1.5x | 10 | 0 | 0 | 1.38% | 2.07% | 2.6140 | 1 |
| FULL / 5 | 2x | 10 | 1 | 1 | inf% | inf% | 3.4853 | 1 |
| FULL / 7 | 1x | 10 | 0 | 0 | 0.40% | 0.60% | 1.7426 | 1 |
| FULL / 7 | 1.5x | 10 | 0 | 0 | 1.38% | 2.07% | 2.6140 | 1 |
| FULL / 7 | 2x | 10 | 1 | 1 | inf% | inf% | 3.4853 | 1 |
| FULL / 10 | 1x | 10 | 0 | 0 | 0.40% | 0.60% | 1.7426 | 1 |
| FULL / 10 | 1.5x | 10 | 0 | 0 | 1.38% | 2.07% | 2.6140 | 1 |
| FULL / 10 | 2x | 10 | 1 | 1 | inf% | inf% | 3.4853 | 1 |
| FULL / hold | 1x | 10 | 0 | 0 | 0.40% | 0.60% | 1.7426 | 1 |
| FULL / hold | 1.5x | 10 | 0 | 0 | 1.38% | 2.07% | 2.6140 | 1 |
| FULL / hold | 2x | 10 | 1 | 1 | inf% | inf% | 3.4853 | 1 |

First hits, DTE5 (raw / reserved); — means observed and survived, UNKNOWN means no complete trade path:

| contract | 1x | 1.5x | 2x |
|---|---|---|---|
| 210326 | UNKNOWN | UNKNOWN | UNKNOWN |
| 210625 | UNKNOWN | UNKNOWN | UNKNOWN |
| 210924 | UNKNOWN | UNKNOWN | UNKNOWN |
| 211231 | UNKNOWN | UNKNOWN | UNKNOWN |
| 220325 | UNKNOWN | UNKNOWN | UNKNOWN |
| 220624 | UNKNOWN | UNKNOWN | UNKNOWN |
| 220930 | UNKNOWN | UNKNOWN | UNKNOWN |
| 221230 | UNKNOWN | UNKNOWN | UNKNOWN |
| 230331 | NO POSITION | NO POSITION | NO POSITION |
| 230630 | — / — | — / — | — / — |
| 230929 | UNKNOWN | UNKNOWN | UNKNOWN |
| 231229 | UNKNOWN | UNKNOWN | UNKNOWN |
| 240329 | — / — | — / — | 2024-03-05 / 2024-03-05 |
| 240628 | — / — | — / — | — / — |
| 240927 | — / — | — / — | — / — |
| 241227 | — / — | — / — | — / — |
| 250328 | — / — | — / — | — / — |
| 250627 | — / — | — / — | — / — |
| 250926 | — / — | — / — | — / — |
| 251226 | — / — | — / — | — / — |
| 260327 | — / — | — / — | — / — |
| 260626 | NO POSITION | NO POSITION | NO POSITION |
| 260925 | NO POSITION | NO POSITION | NO POSITION |

1% flat maintenance + exit reserve sensitivity: 0/50 FULL trade paths hit at 1x.
Counts across exits are overlapping observations, not independent contracts. At >1x collateral is the same Q BTC but the short is larger; this is not a USD-neutral carry position.

## Capital comparison (existing reports, different data windows/universes)

| model | capital per $1 spot value | ann return | observed liquidation |
|---|---|---|---|
| COIN-M, family-worst FULL | $1 | +10.00% | none on observed 1x paths |
| COIN-M, DTE5 FULL | $1 | +10.01% | same daily proxy |
| USD-M v2, family-worst (archived, 8 contracts) | $1 spot denominator, collateral excluded | +10.1% | short not independently funded |
| USD-M margin engine, DTE5 c=1.50 (archived, 8 contracts) | $2.50 | +4.1% | 0/8; c selected with hindsight |
| USD-M margin engine, DTE5 c=2.00 | $3 | +3.4% | 0/8 |
| USD-M portfolio-margin upper bound | $1.10 | +9.3% | modelled |
| declared cash hurdle | $1 | +4.5% | not modelled here |

Sources: [v2 archived result](BASIS_CARRY_V2_BTCUSDT_2026-08-19.md), [margin-engine result](BASIS_MARGIN_ENGINE_BTCUSDT_2026-10-15.md). These archived USD-M results are read-only benchmarks; not rerun or presented as a matched sample.
COIN-M DTE5 on 8/8 archived USD-M delivery codes: +11.02%/yr (delivery-matched only; entry dates differ).

## Data coverage and gaps

Spot files combined, range 2023-01-01 through 2026-10-14. Later supplemental file takes precedence on overlaps. One revision found: 2026-06-06 close 60,593.99 in original versus 60,884.62 in supplemental (which has explicit close_time); original terminal row appears to be an unfinished bar. No spot data before 2023; no additional downloads of spot or substitution of perpetual futures.

| contract | futures first / last | first common DTE | bucket | reason |
|---|---|---|---|---|
| 210326 | 2020-09-25 / 2021-03-26 | None | PARTIAL | no spot overlap |
| 210625 | 2020-12-25 / 2021-06-25 | None | PARTIAL | no spot overlap |
| 210924 | 2021-03-26 / 2021-09-24 | None | PARTIAL | no spot overlap |
| 211231 | 2021-06-25 / 2021-12-31 | None | PARTIAL | no spot overlap |
| 220325 | 2021-09-24 / 2022-03-25 | None | PARTIAL | no spot overlap |
| 220624 | 2021-12-31 / 2022-06-24 | None | PARTIAL | no spot overlap |
| 220930 | 2022-03-25 / 2022-09-30 | None | PARTIAL | no spot overlap |
| 221230 | 2022-06-24 / 2022-12-30 | None | PARTIAL | no spot overlap |
| 230331 | 2022-09-30 / 2023-03-31 | 89 | FULL | complete common daily history |
| 230630 | 2022-12-30 / 2023-06-30 | 180 | FULL | complete common daily history |
| 230929 | 2023-03-31 / 2023-09-29 | 182 | PARTIAL | 4 missing futures days through delivery; 4 missing common days through delivery |
| 231229 | 2023-06-30 / 2023-12-29 | 182 | PARTIAL | 4 missing futures days through delivery; 4 missing common days through delivery |
| 240329 | 2023-09-29 / 2024-03-29 | 182 | FULL | complete common daily history |
| 240628 | 2023-12-29 / 2024-06-28 | 182 | FULL | complete common daily history |
| 240927 | 2024-03-29 / 2024-09-27 | 182 | FULL | complete common daily history |
| 241227 | 2024-06-28 / 2024-12-27 | 182 | FULL | complete common daily history |
| 250328 | 2024-09-27 / 2025-03-28 | 182 | FULL | complete common daily history |
| 250627 | 2024-12-27 / 2025-06-27 | 182 | FULL | complete common daily history |
| 250926 | 2025-03-28 / 2025-09-26 | 182 | FULL | complete common daily history |
| 251226 | 2025-06-27 / 2025-12-26 | 182 | FULL | complete common daily history |
| 260327 | 2025-09-26 / 2026-03-27 | 182 | FULL | complete common daily history |
| 260626 | 2025-12-26 / 2026-06-26 | 182 | FULL | complete common daily history |
| 260925 | 2026-03-27 / 2026-09-25 | 182 | FULL | complete common daily history |

Missing futures dates 230929: 2023-08-28, 2023-08-29, 2023-08-30, 2023-08-31.
Missing common dates 230929: 2023-08-28, 2023-08-29, 2023-08-30, 2023-08-31.
Missing futures dates 231229: 2023-08-28, 2023-08-29, 2023-08-30, 2023-08-31.
Missing common dates 231229: 2023-08-28, 2023-08-29, 2023-08-30, 2023-08-31.

Monthly requests: 276; available 161; HTTP404 115; other errors 0. 404s before listing are expected, not manufactured missing daily bars. All monthly statuses/URLs are in backtest/data/basis_cm/download_manifest_2026-10-15.json. Raw ZIPs retained; missing URLs cached as dated .missing.json files.

## VERDICT: **PASS — COIN-M rescues carry on observed 1x capital paths**

This is conditional on the observed daily price proxy and frozen fee/tier assumptions. It does not establish real mark-price liquidation immunity, order-book capacity, historical account margin settings, or a portfolio CAGR. Missing contracts cannot be declared liquidation-free.

## Actual printed run output

```text
Mechanics checks: inverse PnL, USD hedge, cumulative tiers, 1x/2x liquidation PASS
As-of 2026-10-15; settled quarterly contracts checked: 23
Spot coverage: 2023-01-01 through 2026-10-14
Cost allowance: 0.62%; CM futures leg 0.20%; spot leg 0.11%
FULL exit=3: n=10 positive=10/10 USD_ROC_ann=+10.0025% BTC_ann=-16.3797% CI95=[+7.0638%,+13.8529%]
FULL exit=5: n=10 positive=10/10 USD_ROC_ann=+10.0131% BTC_ann=-15.1753% CI95=[+7.0306%,+13.8958%]
FULL exit=7: n=10 positive=10/10 USD_ROC_ann=+10.1060% BTC_ann=-15.4160% CI95=[+7.0789%,+14.0288%]
FULL exit=10: n=10 positive=10/10 USD_ROC_ann=+10.1100% BTC_ann=-15.4752% CI95=[+7.0127%,+14.1934%]
FULL exit=hold: n=10 positive=10/10 USD_ROC_ann=+9.9891% BTC_ann=-15.6154% CI95=[+7.0925%,+13.7859%]
FULL DTE5 leverage=1x: liquidation=0/10; with_exit_reserve=0/10
FULL DTE5 leverage=1.5x: liquidation=0/10; with_exit_reserve=0/10
FULL DTE5 leverage=2x: liquidation=1/10; with_exit_reserve=1/10
PARTIAL contracts: 210326, 210625, 210924, 211231, 220325, 220624, 220930, 221230, 230929, 231229
USD losers DTE5: none
VERDICT: PASS — COIN-M rescues carry on observed 1x capital paths
1x family-worst USD ROC +10.0025%/yr vs USD-M margin engine +4.1%/yr
wrote -> D:\Quant\backtest_results\BASIS_COINM_2026-10-15.md
```
