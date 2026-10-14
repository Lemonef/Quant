# COIN-M inverse quarterly basis carry — 2026-10-15

## Preregistration (declared before downloading / calculating results)

Hypothesis: ETH collateral and an inverse ETHUSD quarterly short with USD face
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
The [official calculation example](https://www.binance.com/en-NZ/support/faq/detail/360033544231) supports ETH fee = N/F * rate and
0.05% taker; the [current schedule](https://www.binance.com/en/fee/deliveryFee) did not expose populated rows
to the browser, so an account-specific current/historical rate is unverified.

Mechanics: [Binance quarterly specifications](https://www.binance.bh/en-AE/support/faq/detail/d33f37e2c7fe4da3b35ffc904e8fbab5) give $10 face,
ETH collateral/settlement, and inverse PnL. Short PnL = contracts*$10*
(1/F_exit - 1/F_entry), valued in USD at exit SPOT, never at exit futures.
Choose an even integer contract count floor(F_entry/200)*2 and set
Q=contracts*$10/F_entry (approximately one ETH); hedge is exact, no fractional
contracts. Capital = Q*S_entry, with no extra USDT. Q is the gross ETH purchase;
spot-entry haircut Q*spot_cost and futures-entry haircut N/F_entry*fut_cost
are deducted from this same ETH pool. Entry costs thus slightly undercollateralize
the ideal pre-fee 1x hedge. ETH_end = Q - entry costs + inverse PnL -
N/F_exit*fut_cost; final spot-sale cost deducts ETH_end*spot_cost.
USD net = ETH_end_after_sale*S_exit/(Q*S_entry)-1;
ETH net = ETH_end_after_sale/Q-1 (USD-hedged wealth expressed in ETH).

Margin: same Q ETH, short N=L*Q*F_entry for L=1/1.5/2; only 1x is USD neutral.
Walk every held daily HIGH and exit-day OPEN (exit-day high occurs after exit
and is excluded, correcting v2's path endpoint). High of last-traded contract
is a conservative adverse MARK proxy, not a guaranteed bound on true marks.
Equity_ETH = Q - spot-entry cost - futures-entry cost + N*(1/M-1/F_entry).
Margin ratio = maintenance_ETH/equity_ETH; equity<=0 or ratio>=100% triggers.
Also report a conservative liquidation count reserving the full 0.20% futures
exit haircut: (maintenance+N/M*fut_cost)/equity>=100%.
No liquidation-damaged leveraged return is passed off as a carry return.

Maintenance uses the [published 2021 ETH quarterly tier table](https://www.binance.com/en/support/announcement/detail/7c000aa897f74e59bf285ca05dccb1a6),
frozen across this sample, with [cumulative bracket calculation](https://www.binance.com/en-AU/support/faq/detail/be2c7d9d95b04a7e8044ed02dd7dfe5c):
ETH-value caps 100/500/1000/2000/4000/6000/8000/10000/infinity; marginal rates
0.5/0.65/1/2.5/5/10/12.5/15/25%. This is an explicit historical-tier assumption,
not proof of each expired contract's contemporaneous account brackets.
Report the maximum observed position ETH value/tier; results apply to the
declared ~1 ETH scale. Include a 1% maintenance sensitivity at 1x.

Hold is v2's delivery-day 00:00 UTC OPEN proxy, not actual 08:00 settlement or
the index's final-hour average. It pays the same taker+slippage haircut as a
normal close; no additional double settlement fee. Delivery settlement details
are in the specifications link. USDT spot is treated as USD (no depeg/FX model).

## Exit family (FULL, 1x)

| DTE | n | USD positive | USD mean ann ROC | ETH mean ann | USD CI95 | worst USD net | pre-2024 | post-2024 | LOYO min |
|---|---|---|---|---|---|---|---|---|---|
| 3 | 7 | 7/7 | +10.68% | +16.76% | [+7.20%, +15.08%] | +1.904% | +nan% | +10.68% | +8.07% |
| 5 | 7 | 7/7 | +10.78% | +23.68% | [+7.30%, +15.19%] | +2.014% | +nan% | +10.78% | +8.14% |
| 7 | 7 | 7/7 | +10.77% | +22.17% | [+7.25%, +15.18%] | +1.880% | +nan% | +10.77% | +8.18% |
| 10 | 7 | 7/7 | +10.72% | +20.31% | [+7.05%, +15.44%] | +1.513% | +nan% | +10.72% | +8.38% |
| hold proxy | 7 | 7/7 | +10.78% | +20.05% | [+7.50%, +15.03%] | +2.343% | +nan% | +10.78% | +8.00% |

**Family-worst USD ROC: +10.68%/yr.** DTE5 LOYO: drop 2024: +8.14%, drop 2025: +12.76%

## Every contract (DTE5; PARTIAL never enters the verdict)

| contract | bucket/status | entry → exit | DTE entry | signal basis | actual entry basis | gross USD | net USD | USD ann ROC | ETH net / ann | inverse PnL ETH / USD | capital USD |
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
| 230630 | FULL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 230929 | PARTIAL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 231229 | PARTIAL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 240329 | FULL | 2023-11-11 → 2024-03-24 | 139 | +3.09% | +3.07% | +2.829% | +2.014% | +5.49% | -36.34% / -98.99% | -0.358081 / -1192.24 | 2076.34 |
| 240628 | FULL | 2023-12-30 → 2024-06-23 | 181 | +7.31% | +7.32% | +7.201% | +6.398% | +13.27% | -30.02% / -62.26% | -0.294027 / -1027.85 | 2292.17 |
| 240927 | FULL | 2024-03-30 → 2024-09-22 | 181 | +11.36% | +11.36% | +11.240% | +10.665% | +22.12% | +48.68% / +100.95% | +0.493444 / +1289.07 | 3502.25 |
| 241227 | FULL | 2024-06-29 → 2024-12-22 | 181 | +5.65% | +5.73% | +5.536% | +4.904% | +10.17% | +6.20% / +12.86% | +0.068132 / +227.49 | 3367.06 |
| 250328 | FULL | 2024-09-28 → 2025-03-23 | 181 | +4.07% | +4.10% | +3.969% | +3.419% | +7.09% | +40.69% / +84.38% | +0.413603 / +819.22 | 2689.62 |
| 250627 | FULL | 2024-12-28 → 2025-06-22 | 181 | +5.97% | +6.03% | +5.909% | +5.367% | +11.13% | +53.00% / +109.91% | +0.535643 / +1229.69 | 3319.83 |
| 250926 | FULL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 251226 | FULL | 2025-07-16 → 2025-12-21 | 163 | +3.37% | +3.32% | +3.291% | +2.677% | +6.18% | +8.19% / +18.93% | +0.088342 / +263.08 | 3136.00 |
| 260327 | FULL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 260626 | PARTIAL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |
| 260925 | PARTIAL: NO SIGNAL | — | — | — | — | — | — | — | — | — | — |

USD losers (DTE5, including PARTIAL): none.
ETH losses are listed explicitly above; ETH-denominated loss does not imply USD carry loss.

## PARTIAL exit family (descriptive)

| DTE | entered | positive USD | USD mean ann | ETH mean ann |
|---|---|---|---|---|
| 3 | 0 | — | — | — |
| 5 | 0 | — | — | — |
| 7 | 0 | — | — | — |
| 10 | 0 | — | — | — |
| hold proxy | 0 | — | — | — |

## Liquidation by leverage (observed paths; ratio threshold 100%)

| bucket / exit | leverage | paths | maintenance-only hits | with exit-cost reserve | peak raw margin ratio | peak reserved ratio | max BTC position value | max tier |
|---|---|---|---|---|---|---|---|---|---|
| FULL / 3 | 1x | 7 | 0 | 0 | 0.50% | 0.70% | 2.1961 | 1 |
| FULL / 3 | 1.5x | 7 | 0 | 0 | 1.44% | 2.02% | 3.2942 | 1 |
| FULL / 3 | 2x | 7 | 0 | 0 | 22.56% | 31.58% | 4.3923 | 1 |
| FULL / 5 | 1x | 7 | 0 | 0 | 0.50% | 0.70% | 2.1961 | 1 |
| FULL / 5 | 1.5x | 7 | 0 | 0 | 1.44% | 2.02% | 3.2942 | 1 |
| FULL / 5 | 2x | 7 | 0 | 0 | 22.56% | 31.58% | 4.3923 | 1 |
| FULL / 7 | 1x | 7 | 0 | 0 | 0.50% | 0.70% | 2.1961 | 1 |
| FULL / 7 | 1.5x | 7 | 0 | 0 | 1.44% | 2.02% | 3.2942 | 1 |
| FULL / 7 | 2x | 7 | 0 | 0 | 22.56% | 31.58% | 4.3923 | 1 |
| FULL / 10 | 1x | 7 | 0 | 0 | 0.50% | 0.70% | 2.1961 | 1 |
| FULL / 10 | 1.5x | 7 | 0 | 0 | 1.44% | 2.02% | 3.2942 | 1 |
| FULL / 10 | 2x | 7 | 0 | 0 | 22.56% | 31.58% | 4.3923 | 1 |
| FULL / hold | 1x | 7 | 0 | 0 | 0.50% | 0.70% | 2.1961 | 1 |
| FULL / hold | 1.5x | 7 | 0 | 0 | 1.44% | 2.02% | 3.2942 | 1 |
| FULL / hold | 2x | 7 | 0 | 0 | 22.56% | 31.58% | 4.3923 | 1 |

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
| 230630 | NO POSITION | NO POSITION | NO POSITION |
| 230929 | UNKNOWN | UNKNOWN | UNKNOWN |
| 231229 | UNKNOWN | UNKNOWN | UNKNOWN |
| 240329 | — / — | — / — | — / — |
| 240628 | — / — | — / — | — / — |
| 240927 | — / — | — / — | — / — |
| 241227 | — / — | — / — | — / — |
| 250328 | — / — | — / — | — / — |
| 250627 | — / — | — / — | — / — |
| 250926 | NO POSITION | NO POSITION | NO POSITION |
| 251226 | — / — | — / — | — / — |
| 260327 | NO POSITION | NO POSITION | NO POSITION |
| 260626 | UNKNOWN | UNKNOWN | UNKNOWN |
| 260925 | UNKNOWN | UNKNOWN | UNKNOWN |

1% flat maintenance + exit reserve sensitivity: 0/35 FULL trade paths hit at 1x.
Counts across exits are overlapping observations, not independent contracts. At >1x collateral is the same Q BTC but the short is larger; this is not a USD-neutral carry position.

## Capital comparison (existing reports, different data windows/universes)

| model | capital per $1 spot value | ann return | observed liquidation |
|---|---|---|---|
| COIN-M, family-worst FULL | $1 | +10.68% | none on observed 1x paths |
| COIN-M, DTE5 FULL | $1 | +10.78% | same daily proxy |
| USD-M v2, family-worst (archived, 8 contracts) | $1 spot denominator, collateral excluded | +10.1% | short not independently funded |
| USD-M margin engine, DTE5 c=1.50 (archived, 8 contracts) | $2.50 | +4.1% | 0/8; c selected with hindsight |
| USD-M margin engine, DTE5 c=2.00 | $3 | +3.4% | 0/8 |
| USD-M portfolio-margin upper bound | $1.10 | +9.3% | modelled |
| declared cash hurdle | $1 | +4.5% | not modelled here |

Sources: [v2 archived result](BASIS_CARRY_V2_BTCUSDT_2026-08-19.md), [margin-engine result](BASIS_MARGIN_ENGINE_BTCUSDT_2026-10-15.md). These archived USD-M results are read-only benchmarks; not rerun or presented as a matched sample.
COIN-M DTE5 on 7/8 archived USD-M delivery codes: +10.78%/yr (delivery-matched only; entry dates differ).

## Data coverage and gaps

Spot file ETHUSDT_1d.csv, range 2023-01-01 through 2026-06-06. No spot data before 2023; no additional downloads of spot or substitution of perpetual futures.

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
| 260626 | 2025-12-26 / 2026-06-26 | 182 | PARTIAL | 20 missing common days through delivery |
| 260925 | 2026-03-27 / 2026-09-25 | 182 | PARTIAL | 111 missing common days through delivery |

Missing futures dates 230929: 2023-08-28, 2023-08-29, 2023-08-30, 2023-08-31.
Missing common dates 230929: 2023-08-28, 2023-08-29, 2023-08-30, 2023-08-31.
Missing futures dates 231229: 2023-08-28, 2023-08-29, 2023-08-30, 2023-08-31.
Missing common dates 231229: 2023-08-28, 2023-08-29, 2023-08-30, 2023-08-31.
Missing common dates 260626: 2026-06-07, 2026-06-08, 2026-06-09, 2026-06-10, 2026-06-11, 2026-06-12, 2026-06-13, 2026-06-14, 2026-06-15, 2026-06-16, 2026-06-17, 2026-06-18, 2026-06-19, 2026-06-20, 2026-06-21, 2026-06-22, 2026-06-23, 2026-06-24, 2026-06-25, 2026-06-26.
Missing common dates 260925: 2026-06-07, 2026-06-08, 2026-06-09, 2026-06-10, 2026-06-11, 2026-06-12, 2026-06-13, 2026-06-14, 2026-06-15, 2026-06-16, 2026-06-17, 2026-06-18, 2026-06-19, 2026-06-20, 2026-06-21, 2026-06-22, 2026-06-23, 2026-06-24, 2026-06-25, 2026-06-26, 2026-06-27, 2026-06-28, 2026-06-29, 2026-06-30, 2026-07-01, 2026-07-02, 2026-07-03, 2026-07-04, 2026-07-05, 2026-07-06, 2026-07-07, 2026-07-08, 2026-07-09, 2026-07-10, 2026-07-11, 2026-07-12, 2026-07-13, 2026-07-14, 2026-07-15, 2026-07-16, 2026-07-17, 2026-07-18, 2026-07-19, 2026-07-20, 2026-07-21, 2026-07-22, 2026-07-23, 2026-07-24, 2026-07-25, 2026-07-26, 2026-07-27, 2026-07-28, 2026-07-29, 2026-07-30, 2026-07-31, 2026-08-01, 2026-08-02, 2026-08-03, 2026-08-04, 2026-08-05, 2026-08-06, 2026-08-07, 2026-08-08, 2026-08-09, 2026-08-10, 2026-08-11, 2026-08-12, 2026-08-13, 2026-08-14, 2026-08-15, 2026-08-16, 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-20, 2026-08-21, 2026-08-22, 2026-08-23, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-08-28, 2026-08-29, 2026-08-30, 2026-08-31, 2026-09-01, 2026-09-02, 2026-09-03, 2026-09-04, 2026-09-05, 2026-09-06, 2026-09-07, 2026-09-08, 2026-09-09, 2026-09-10, 2026-09-11, 2026-09-12, 2026-09-13, 2026-09-14, 2026-09-15, 2026-09-16, 2026-09-17, 2026-09-18, 2026-09-19, 2026-09-20, 2026-09-21, 2026-09-22, 2026-09-23, 2026-09-24, 2026-09-25.

Monthly requests: 276; available 161; HTTP404 115; other errors 0. 404s before listing are expected, not manufactured missing daily bars. All monthly statuses/URLs are in backtest/data/basis_cm/download_manifest_2026-10-15.json. Raw ZIPs retained; missing URLs cached as dated .missing.json files.

## VERDICT: **PASS — COIN-M rescues carry on observed 1x capital paths**

This is conditional on the observed daily price proxy and frozen fee/tier assumptions. It does not establish real mark-price liquidation immunity, order-book capacity, historical account margin settings, or a portfolio CAGR. Missing contracts cannot be declared liquidation-free.

## Actual printed run output

```text
Mechanics checks: inverse PnL, USD hedge, cumulative tiers, 1x/2x liquidation PASS
As-of 2026-10-15; settled quarterly contracts checked: 23
Spot coverage: 2023-01-01 through 2026-06-06
Cost allowance: 0.62%; CM futures leg 0.20%; spot leg 0.11%
FULL exit=3: n=7 positive=7/7 USD_ROC_ann=+10.6797% BTC_ann=+16.7582% CI95=[+7.1952%,+15.0770%]
FULL exit=5: n=7 positive=7/7 USD_ROC_ann=+10.7781% BTC_ann=+23.6824% CI95=[+7.2983%,+15.1858%]
FULL exit=7: n=7 positive=7/7 USD_ROC_ann=+10.7741% BTC_ann=+22.1715% CI95=[+7.2460%,+15.1778%]
FULL exit=10: n=7 positive=7/7 USD_ROC_ann=+10.7210% BTC_ann=+20.3144% CI95=[+7.0492%,+15.4351%]
FULL exit=hold: n=7 positive=7/7 USD_ROC_ann=+10.7776% BTC_ann=+20.0472% CI95=[+7.5035%,+15.0325%]
FULL DTE5 leverage=1x: liquidation=0/7; with_exit_reserve=0/7
FULL DTE5 leverage=1.5x: liquidation=0/7; with_exit_reserve=0/7
FULL DTE5 leverage=2x: liquidation=0/7; with_exit_reserve=0/7
PARTIAL contracts: 210326, 210625, 210924, 211231, 220325, 220624, 220930, 221230, 230929, 231229, 260626, 260925
USD losers DTE5: none
VERDICT: PASS — COIN-M rescues carry on observed 1x capital paths
1x family-worst USD ROC +10.6797%/yr vs USD-M margin engine +4.1%/yr
wrote -> D:\Quant\backtest_results\BASIS_COINM_ETH_2026-10-15.md
```
