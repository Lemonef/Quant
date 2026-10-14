# Options snapshot factors — 2026-10-15

## PRE-REGISTRATION (written before factor or target results are computed)

BTC only; six factors x horizons h = 1, 3, 7 calendar days; n_trials = 18. No VRP or ETH tests.

Kill line: |t| >= floor AND every purged fold agrees on the sign AND the train-side overlay beats buy-and-hold on the untouched OOS tail net of costs.

floor = 2.0. Four contiguous folds, 10-day leading embargo after fold 1, with forward-label endpoints additionally purged at each fold boundary. Calendar 60% train / 40% untouched tail; train labels ending in the tail are excluded. Both signs must occur in every fold. Reuse leadlag.diff_means_t, including effective counts floor(n_positive/h) and floor(n_negative/h). The all-sample t and fold signs are diagnostics; only train labels choose the overlay side. Sharpe uses 365 days/year and requires >30 daily observations, as in leadlag.py; otherwise report NA and the gate cannot pass. Cost is 0.0006 fee + 0.0005 slippage per unit turnover; charge initial entry and final liquidation to overlay and hold alike.

Declared publication lag: snapshot dated t becomes usable at close t+1 UTC. Target log(C[t+1+h]/C[t+1]); first traded daily bar ends t+2. This adds the publication day before the usual next-bar execution and never uses snapshot-day returns. No forward fill of missing snapshots or closes. Last snapshot timestamp within each UTC day is used; expired contracts are excluded at that timestamp.

Factor definitions and directional hypotheses (priors, not fitted restrictions):

1. GEX level = sum(call +1, put -1) * gamma * OI * 1 BTC * spot^2 across live expiries; test its raw sign. Positive hypothesized to accompany higher future returns (weak exposure-timing prior; gamma more directly concerns volatility). Gamma absent: derive Black-76 gamma = phi(d1)/(F*sigma*sqrt(T)), discount rate zero, mark_iv/100, underlying_price as per-contract forward F, expiry 08:00 UTC, ACT/365. Spot proxy is median snapshot underlying_price, since a separate index spot is absent. Level is dollar delta change per unit proportional move (multiply by 0.01 for a 1% move). Dealer calls-long/puts-short is a stipulated proxy, not observed inventory.
2. Put/call OI, all live expiries: sum put OI / sum call OI. High ratio hypothesized bearish.
3. Put/call OI, front monthly expiry: nearest live last-Friday-of-month expiry, not the nearest daily/weekly expiry. High ratio hypothesized bearish.
4. Front-expiry 25-delta risk reversal = call IV at +0.25 delta minus put IV at -0.25 delta, in percentage points. Black-76 forward deltas derived from IV; linear interpolation in each side's absolute delta, no extrapolation; missing when 0.25 is not bracketed. Higher RR hypothesized bullish.
5. Front ATM IV: average call/put mark IV at the listed strike nearest the snapshot spot proxy. Its expanding percentile uses only strictly earlier valid ATM observations; minimum 20 earlier observations. Test sign(percentile - 0.5). High percentile hypothesized bearish. No realized-volatility subtraction.
6. Front-expiry max-pain distance = (spot - minimizing strike)/spot; minimize OI-weighted USD intrinsic payouts on listed strikes (lowest strike breaks ties). Positive distance hypothesized bearish via pinning. This is the conventional USD intrinsic proxy for inverse options, not an exact inverse settlement calculation.

Front expiry means earliest expiry still live at snapshot time, including same-day expiry. For PCR and RR, high/low = sign(level - median of strictly prior 20 calendar days), with >=10 valid prior observations; GEX uses raw sign and max-pain uses sign(distance). Zero signs abstain. No alternative windows or definitions will be tried.

Overlay: daily long BTC on the train-chosen favorable sign, otherwise cash; choose the side separately for each horizon using purged train conditional mean gap. Gap <0 chooses negative, gap >0 chooses positive, missing/zero gap leaves gate untestable. Daily returns are simple returns for trading/SR, log returns for statistical targets. Start flat at OOS entry; settle final exit at tail end. Missing signals are cash; missing traded BTC bars make overlay SR unavailable. OOS range is fixed from snapshot calendar coverage and independent of factor warmups.

Multiple testing: 18 nominal two-sided tests at about 5% imply 0.9 expected nominal false positives; under independence P(at least one) = 1 - 0.95^18 = 60.3%. Trials are dependent. The three-leg gate has no calibrated family-wise error rate. Report Bonferroni reference alpha=0.05/18 and every row, including unavailable rows. A pass is a candidate, never deployment evidence.

Power plan: report balanced-group standardized conditional mean gap MDE at 80% power using (critical normal z + z_0.8)*2/sqrt(n_eff), nominal and Bonferroni. These are optimistic approximations, before serial dependence, imbalance, sign consistency and the OOS gate. Planning target d=0.5 pooled SD: estimate independent observations required and multiply by h; also require >=31 OOS daily bars. Failures at this sample size are UNDERPOWERED — cannot conclude, not DEAD. More observations cannot recover missing historical closes but can build a prospective test.

Data policy: local BTCUSDT_1d.csv first; if required daily closes are missing, fetch only data-api.binance.vision /api/v3/klines in memory. Do not modify existing files or substitute Deribit forward marks for BTC spot closes. Reject incomplete current-day candles and never fabricate missing targets. Record fetch errors and report untestable rows if necessary.

Sources for modelling conventions: [Deribit inverse options](https://support.deribit.com/hc/en-us/articles/31424939096093-Inverse-Options), [Deribit expiry listing policy](https://support.deribit.com/hc/en-us/articles/25944688876957), [KTH Black-76 lecture](https://www.math.kth.se/matstat/gru/sf2701/2015/lecture9.pdf).

## Data coverage and real printed output

```text
Snapshot coverage: 2026-08-10 to 2026-10-14; 66 observed days / 66 calendar days.
Snapshots=66; instrument rows=62274; duplicate rows=0; expired rows excluded=0.
Snapshot gaps: none
Local BTC closes: 2023-01-01 to 2026-06-06, n=1253.
Required closes absent locally: 66 days; permitted fetch attempted: https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1d&startTime=1786320000000&endTime=1792022399999&limit=1000
Fetch returned 66 completed candles; no data file written.
Usable BTC closes in requested window: 66/74; OOS 2026-09-20 to 2026-10-14, 25 daily bars, 25 valid returns.
Gamma and delta: Black-76 derived; underlying_price is a forward/spot proxy, mark_iv is percent; 1 BTC contract size, rate zero.
Factor coverage (raw n / usable nonzero sign n; first to last raw observation; missing calendar days):
  gex: 66 / 66; 2026-08-10 to 2026-10-14; missing=none
    Decision signs: positive=66, negative=0, zero=0, unavailable=0.
  pcr_all: 66 / 56; 2026-08-10 to 2026-10-14; missing=none
    Decision signs: positive=32, negative=24, zero=0, unavailable=10.
  pcr_month: 66 / 56; 2026-08-10 to 2026-10-14; missing=none
    Decision signs: positive=26, negative=30, zero=0, unavailable=10.
  rr25: 66 / 56; 2026-08-10 to 2026-10-14; missing=none
    Decision signs: positive=26, negative=30, zero=0, unavailable=10.
  iv_percentile: 46 / 45; 2026-08-30 to 2026-10-14; missing=2026-08-10, 2026-08-11, 2026-08-12, 2026-08-13, 2026-08-14, 2026-08-15, 2026-08-16, 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-20, 2026-08-21, 2026-08-22, 2026-08-23, 2026-08-24, 2026-08-25, 2026-08-26, 2026-08-27, 2026-08-28, 2026-08-29
    Decision signs: positive=28, negative=17, zero=1, unavailable=20.
  maxpain_distance: 66 / 66; 2026-08-10 to 2026-10-14; missing=none
    Decision signs: positive=47, negative=19, zero=0, unavailable=0.
Invalid IV rows in selected live snapshots: 0.
GEX lacks both signs in this sample: its conditional gap cannot be tested even if missing closes are recovered.
The 25-bar completed OOS tail is below the precedent's >30-bar Sharpe requirement: the trading gate is unavailable even if closes are recovered.

factor | h | n | n_eff | t | folds agree | OOS overlay SR | hold SR | PASS
gex | 1 | 64 | 64 | NA | no | NA | NA | NO
gex | 3 | 62 | 20 | NA | no | NA | NA | NO
gex | 7 | 58 | 8 | NA | no | NA | NA | NO
pcr_all | 1 | 54 | 54 | 0.40 | no | NA | NA | NO
pcr_all | 3 | 52 | 17 | 0.17 | no | NA | NA | NO
pcr_all | 7 | 48 | 6 | 0.03 | no | NA | NA | NO
pcr_month | 1 | 54 | 54 | 1.42 | no | NA | NA | NO
pcr_month | 3 | 52 | 17 | 1.20 | no | NA | NA | NO
pcr_month | 7 | 48 | 6 | 0.64 | no | NA | NA | NO
rr25 | 1 | 54 | 54 | 0.15 | no | NA | NA | NO
rr25 | 3 | 52 | 16 | -0.12 | no | NA | NA | NO
rr25 | 7 | 48 | 6 | 0.23 | no | NA | NA | NO
iv_percentile | 1 | 43 | 43 | 0.43 | no | NA | NA | NO
iv_percentile | 3 | 41 | 13 | 0.52 | no | NA | NA | NO
iv_percentile | 7 | 37 | 5 | 0.18 | no | NA | NA | NO
maxpain_distance | 1 | 64 | 64 | 0.28 | no | NA | NA | NO
maxpain_distance | 3 | 62 | 20 | 0.36 | no | NA | NA | NO
maxpain_distance | 7 | 58 | 8 | -0.48 | no | NA | NA | NO

Fold sign / fold observation count / train favorable side / OOS turnover:
  gex h=1: NA,NA,NA,NA / [16, 6, 5, 4] / NA / 0
  gex h=3: NA,NA,NA,NA / [14, 4, 3, 2] / NA / 0
  gex h=7: NA,NA,NA,NA / [10, 0, 0, 0] / NA / 0
  pcr_all h=1: 1,NA,1,NA / [6, 6, 5, 4] / 1 / 10
  pcr_all h=3: 1,NA,NA,NA / [4, 4, 3, 2] / 1 / 10
  pcr_all h=7: NA,NA,NA,NA / [0, 0, 0, 0] / 1 / 10
  pcr_month h=1: 1,NA,1,NA / [6, 6, 5, 4] / 1 / 4
  pcr_month h=3: 1,NA,NA,NA / [4, 4, 3, 2] / 1 / 4
  pcr_month h=7: NA,NA,NA,NA / [0, 0, 0, 0] / 1 / 4
  rr25 h=1: NA,1,-1,-1 / [6, 6, 5, 4] / 1 / 12
  rr25 h=3: NA,1,1,-1 / [4, 4, 3, 2] / -1 / 10
  rr25 h=7: NA,NA,NA,NA / [0, 0, 0, 0] / 1 / 12
  iv_percentile h=1: NA,1,1,-1 / [0, 6, 5, 4] / 1 / 12
  iv_percentile h=3: NA,-1,NA,NA / [0, 4, 3, 2] / 1 / 12
  iv_percentile h=7: NA,NA,NA,NA / [0, 0, 0, 0] / 1 / 12
  maxpain_distance h=1: 1,1,1,-1 / [16, 6, 5, 4] / 1 / 10
  maxpain_distance h=3: 1,-1,1,-1 / [14, 4, 3, 2] / 1 / 10
  maxpain_distance h=7: -1,NA,NA,NA / [10, 0, 0, 0] / -1 / 8

80% power MDE (standardized conditional gap, optimistic balanced-group normal approximation):
  At n=70, h=1, n_eff~70: nominal MDE=0.67 SD, Bonferroni MDE=0.92 SD; nominal power for d=0.5: 55.2%.
  At n=70, h=3, n_eff~23: nominal MDE=1.17 SD, Bonferroni MDE=1.60 SD; nominal power for d=0.5: 22.4%.
  At n=70, h=7, n_eff~10: nominal MDE=1.77 SD, Bonferroni MDE=2.42 SD; nominal power for d=0.5: 12.4%.
Actual-row MDE (nominal / Bonferroni); NA means no evaluable targets:
  gex h=1: NA / NA SD
  gex h=3: NA / NA SD
  gex h=7: NA / NA SD
  pcr_all h=1: 0.77 / 1.05 SD
  pcr_all h=3: 1.36 / 1.86 SD
  pcr_all h=7: 2.29 / 3.13 SD
  pcr_month h=1: 0.77 / 1.05 SD
  pcr_month h=3: 1.38 / 1.89 SD
  pcr_month h=7: 2.43 / 3.32 SD
  rr25 h=1: 0.77 / 1.05 SD
  rr25 h=3: 1.41 / 1.93 SD
  rr25 h=7: 2.29 / 3.13 SD
  iv_percentile h=1: 0.88 / 1.21 SD
  iv_percentile h=3: 1.60 / 2.19 SD
  iv_percentile h=7: 2.56 / 3.50 SD
  maxpain_distance h=1: 0.77 / 1.05 SD
  maxpain_distance h=3: 1.37 / 1.87 SD
  maxpain_distance h=7: 2.29 / 3.13 SD

VERDICT: 0/18 PASS — UNDERPOWERED — cannot conclude. No factor is DEAD on this sample.
What would make this conclusive: recover matched completed BTC spot closes, then accrue h=1: ~236 usable days (~170 more than current snapshots, before warmup/imbalance); h=3: ~708 usable days (~642 more than current snapshots, before warmup/imbalance); h=7: ~1652 usable days (~1586 more than current snapshots, before warmup/imbalance); >=31 valid untouched OOS bars, both signs in all purged folds, and independent replication. This targets 80% power for d=0.5 at Bonferroni alpha; no fixed n guarantees a pass.
18 tests: expected nominal false positives ~0.9; independence reference P(any)~60.3%; a single nominal pass is unsurprising.
VRP was not retested. No existing files or live_bot files modified.
```

## Results

| factor | h | n | t | folds agree | OOS overlay SR | hold SR | PASS |
|---|---:|---:|---:|---|---:|---:|---|
| gex | 1 | 64 | NA | no | NA | NA | NO |
| gex | 3 | 62 | NA | no | NA | NA | NO |
| gex | 7 | 58 | NA | no | NA | NA | NO |
| pcr_all | 1 | 54 | 0.40 | no | NA | NA | NO |
| pcr_all | 3 | 52 | 0.17 | no | NA | NA | NO |
| pcr_all | 7 | 48 | 0.03 | no | NA | NA | NO |
| pcr_month | 1 | 54 | 1.42 | no | NA | NA | NO |
| pcr_month | 3 | 52 | 1.20 | no | NA | NA | NO |
| pcr_month | 7 | 48 | 0.64 | no | NA | NA | NO |
| rr25 | 1 | 54 | 0.15 | no | NA | NA | NO |
| rr25 | 3 | 52 | -0.12 | no | NA | NA | NO |
| rr25 | 7 | 48 | 0.23 | no | NA | NA | NO |
| iv_percentile | 1 | 43 | 0.43 | no | NA | NA | NO |
| iv_percentile | 3 | 41 | 0.52 | no | NA | NA | NO |
| iv_percentile | 7 | 37 | 0.18 | no | NA | NA | NO |
| maxpain_distance | 1 | 64 | 0.28 | no | NA | NA | NO |
| maxpain_distance | 3 | 62 | 0.36 | no | NA | NA | NO |
| maxpain_distance | 7 | 58 | -0.48 | no | NA | NA | NO |

NA is unavailable, not a zero Sharpe or zero t. No targets are substituted or imputed. Bonferroni is a reference for power/multiplicity, not an extra retroactive kill gate. Fold counts and actual MDEs appear in stdout above. Statistical t can also be unavailable when either effective group has <2 observations.

## Daily factor levels

| snapshot date | GEX level | GEX sign | PCR all | PCR month | RR25 pp | ATM IV % | IV percentile | max-pain strike | max-pain distance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-08-10 | 10137041132.50 | 1 | 0.5754 | 0.6715 | 2.0844 | 24.9100 | NA | 65000.00 | 0.007199 |
| 2026-08-11 | 2238663200.55 | 1 | 0.5717 | 0.6724 | -3.1591 | 21.1700 | NA | 64500.00 | -0.002751 |
| 2026-08-12 | 2830770467.04 | 1 | 0.5655 | 0.6458 | -2.5412 | 20.1100 | NA | 64000.00 | 0.000485 |
| 2026-08-13 | 4063119508.35 | 1 | 0.5530 | 0.6457 | 2.2557 | 25.8500 | NA | 64000.00 | -0.003370 |
| 2026-08-14 | 6536256312.87 | 1 | 0.5514 | 0.6508 | -0.0600 | 20.5700 | NA | 64000.00 | -0.002396 |
| 2026-08-15 | 2852654988.98 | 1 | 0.5434 | 0.6478 | -3.7706 | 14.2900 | NA | 63000.00 | 0.004499 |
| 2026-08-16 | 1215111255.82 | 1 | 0.5563 | 0.6447 | -3.1504 | 12.4800 | NA | 63000.00 | 0.004712 |
| 2026-08-17 | 2524111445.60 | 1 | 0.5579 | 0.6543 | -3.6506 | 20.4300 | NA | 63000.00 | 0.005607 |
| 2026-08-18 | 8776132669.22 | 1 | 0.5600 | 0.6784 | -2.2845 | 17.4000 | NA | 64000.00 | 0.007411 |
| 2026-08-19 | 9919021652.96 | 1 | 0.5633 | 0.6809 | -0.3564 | 17.5800 | NA | 64000.00 | 0.010657 |
| 2026-08-20 | 25591859025.35 | 1 | 0.5589 | 0.6459 | 3.9389 | 37.1400 | NA | 65000.00 | 0.072336 |
| 2026-08-21 | 28951200828.02 | 1 | 0.5550 | 0.6386 | 4.5423 | 73.1100 | NA | 67000.00 | 0.112109 |
| 2026-08-22 | 25029053326.21 | 1 | 0.5939 | 0.7419 | 5.6477 | 40.4400 | NA | 74000.00 | 0.052685 |
| 2026-08-23 | 24275181675.19 | 1 | 0.5932 | 0.7487 | 2.1218 | 30.1800 | NA | 70000.00 | 0.096398 |
| 2026-08-24 | 23588160298.74 | 1 | 0.5957 | 0.7456 | 2.7634 | 51.5100 | NA | 76500.00 | 0.011554 |
| 2026-08-25 | 25961163181.49 | 1 | 0.6051 | 0.8049 | 7.4527 | 51.6200 | NA | 77500.00 | 0.029888 |
| 2026-08-26 | 25958386606.15 | 1 | 0.5937 | 0.8528 | 3.7108 | 39.7100 | NA | 79000.00 | 0.000416 |
| 2026-08-27 | 30141792599.17 | 1 | 0.5868 | 0.9109 | 6.9809 | 46.6500 | NA | 69000.00 | 0.143210 |
| 2026-08-28 | 24211018140.82 | 1 | 0.5333 | 0.5108 | 5.3281 | 51.3800 | NA | 80000.00 | 0.004350 |
| 2026-08-29 | 12885579934.85 | 1 | 0.5659 | 0.5304 | -3.6671 | 18.3200 | NA | 79000.00 | -0.016019 |
| 2026-08-30 | 21351906333.35 | 1 | 0.5621 | 0.5273 | 1.4290 | 17.0400 | 0.1000 | 78000.00 | 0.009247 |
| 2026-08-31 | 18328826902.34 | 1 | 0.5701 | 0.5287 | -1.7277 | 33.2100 | 0.6190 | 78500.00 | 0.001597 |
| 2026-09-01 | 24081523950.06 | 1 | 0.5641 | 0.5272 | 0.0249 | 29.9500 | 0.5455 | 78500.00 | 0.012324 |
| 2026-09-02 | 15459138728.71 | 1 | 0.5634 | 0.5185 | -1.1735 | 27.4900 | 0.5217 | 78500.00 | -0.006356 |
| 2026-09-03 | 19493903098.50 | 1 | 0.5533 | 0.5098 | -0.0325 | 25.8500 | 0.4792 | 77500.00 | 0.007456 |
| 2026-09-04 | 42711605076.58 | 1 | 0.5557 | 0.5109 | 15.8525 | 48.9600 | 0.8400 | 72000.00 | 0.118266 |
| 2026-09-05 | 25346812285.56 | 1 | 0.5470 | 0.5020 | 1.5415 | 20.3850 | 0.2692 | 79500.00 | 0.005865 |
| 2026-09-06 | 27077882988.39 | 1 | 0.5492 | 0.5029 | 0.3280 | 26.6100 | 0.5185 | 80000.00 | 0.004245 |
| 2026-09-07 | 24863501035.07 | 1 | 0.5491 | 0.5034 | -0.0982 | 27.1800 | 0.5357 | 80000.00 | 0.000827 |
| 2026-09-08 | 25604989293.31 | 1 | 0.5392 | 0.5045 | -1.3961 | 25.2000 | 0.4138 | 79500.00 | -0.003858 |
| 2026-09-09 | 31959899521.87 | 1 | 0.5311 | 0.5087 | 1.9524 | 27.8800 | 0.6000 | 79000.00 | 0.004706 |
| 2026-09-10 | 27060501410.30 | 1 | 0.5477 | 0.5152 | 1.7957 | 28.5800 | 0.6129 | 79000.00 | -0.002865 |
| 2026-09-11 | 17526358363.75 | 1 | 0.5459 | 0.5134 | -0.8832 | 28.3100 | 0.5938 | 78000.00 | -0.006395 |
| 2026-09-12 | 19939114486.58 | 1 | 0.5476 | 0.5144 | 0.4058 | 17.2500 | 0.0909 | 78000.00 | -0.003828 |
| 2026-09-13 | 18336824778.26 | 1 | 0.5580 | 0.5142 | 1.3750 | 15.9800 | 0.0588 | 77500.00 | 0.001810 |
| 2026-09-14 | 21139843969.97 | 1 | 0.5579 | 0.5171 | 0.0288 | 30.3200 | 0.7143 | 77000.00 | 0.012575 |
| 2026-09-15 | 20373089766.84 | 1 | 0.5524 | 0.5195 | -2.1099 | 27.8800 | 0.5694 | 78000.00 | -0.000424 |
| 2026-09-16 | 11866219197.53 | 1 | 0.5523 | 0.5263 | 1.1589 | 31.1600 | 0.7297 | 77000.00 | -0.009005 |
| 2026-09-17 | 17517141997.73 | 1 | 0.5538 | 0.5312 | -1.2296 | 27.3700 | 0.5000 | 76500.00 | 0.004808 |
| 2026-09-18 | 23175351480.87 | 1 | 0.5640 | 0.5319 | 3.4238 | 33.1200 | 0.7436 | 77500.00 | 0.003412 |
| 2026-09-19 | 39067031761.68 | 1 | 0.5623 | 0.5468 | 1.6275 | 26.7900 | 0.4500 | 78000.00 | 0.041658 |
| 2026-09-20 | 33058952611.58 | 1 | 0.5648 | 0.5493 | -0.3442 | 27.7150 | 0.5366 | 80000.00 | 0.011388 |
| 2026-09-21 | 38587700620.25 | 1 | 0.5649 | 0.5524 | 3.5776 | 35.1000 | 0.7857 | 80500.00 | 0.017109 |
| 2026-09-22 | 44759133404.87 | 1 | 0.5327 | 0.6589 | 2.3734 | 32.9200 | 0.7209 | 82500.00 | 0.039470 |
| 2026-09-23 | 45425116533.05 | 1 | 0.5657 | 0.6793 | 4.7653 | 40.5400 | 0.8636 | 85500.00 | 0.023491 |
| 2026-09-24 | 30737698321.49 | 1 | 0.5999 | 0.7570 | -1.4722 | 31.0300 | 0.6667 | 85000.00 | -0.008826 |
| 2026-09-25 | 33772113191.20 | 1 | 0.6149 | 0.8563 | 0.6091 | 32.8600 | 0.6957 | 78000.00 | 0.077252 |
| 2026-09-26 | 22561798455.55 | 1 | 0.5215 | 0.3013 | 0.7998 | 22.0300 | 0.2766 | 85000.00 | -0.003948 |
| 2026-09-27 | 27728591256.39 | 1 | 0.5184 | 0.3015 | -0.0023 | 21.3700 | 0.2708 | 84500.00 | 0.006983 |
| 2026-09-28 | 17258795363.83 | 1 | 0.5226 | 0.3068 | -4.7218 | 26.9700 | 0.4286 | 84000.00 | -0.002595 |
| 2026-09-29 | 18589124380.55 | 1 | 0.5332 | 0.3150 | -1.2596 | 27.0900 | 0.4400 | 84000.00 | -0.000552 |
| 2026-09-30 | 21296337041.23 | 1 | 0.5493 | 0.3292 | -0.3872 | 27.3000 | 0.4706 | 84000.00 | 0.001016 |
| 2026-10-01 | 23120369747.86 | 1 | 0.5669 | 0.3655 | 0.0957 | 31.5400 | 0.7115 | 84000.00 | 0.012186 |
| 2026-10-02 | 32749863811.28 | 1 | 0.5795 | 0.3926 | 7.9034 | 54.9300 | 0.9811 | 82000.00 | 0.054671 |
| 2026-10-03 | 21870685507.18 | 1 | 0.5589 | 0.3939 | 3.5882 | 26.0400 | 0.3519 | 85000.00 | 0.003103 |
| 2026-10-04 | 22122075141.48 | 1 | 0.5561 | 0.3948 | -3.9251 | 20.5600 | 0.2000 | 85000.00 | 0.006184 |
| 2026-10-05 | 27210529982.24 | 1 | 0.5602 | 0.3994 | 0.2084 | 39.2300 | 0.8214 | 85000.00 | 0.016197 |
| 2026-10-06 | 21310226858.22 | 1 | 0.5582 | 0.4002 | -0.1209 | 26.6500 | 0.3860 | 86000.00 | -0.000877 |
| 2026-10-07 | 17267419107.28 | 1 | 0.5621 | 0.4059 | -2.2756 | 35.9000 | 0.7931 | 86000.00 | -0.012401 |
| 2026-10-08 | 10101554472.25 | 1 | 0.5760 | 0.4386 | -1.1669 | 39.9200 | 0.8475 | 84500.00 | -0.013690 |
| 2026-10-09 | 9072013615.44 | 1 | 0.5990 | 0.4764 | -3.4647 | 35.1600 | 0.7667 | 84000.00 | -0.011771 |
| 2026-10-10 | 14295949041.85 | 1 | 0.5871 | 0.4798 | 0.8650 | 33.5500 | 0.7377 | 83000.00 | 0.004093 |
| 2026-10-11 | 18107171424.80 | 1 | 0.5870 | 0.4791 | -4.6749 | 18.9200 | 0.1290 | 82500.00 | 0.013165 |
| 2026-10-12 | 22895756739.25 | 1 | 0.5793 | 0.4739 | 2.9747 | 33.3900 | 0.7302 | 83000.00 | 0.018157 |
| 2026-10-13 | 18931743480.32 | 1 | 0.5947 | 0.4862 | 4.3365 | 37.3100 | 0.8125 | 83000.00 | 0.014886 |
| 2026-10-14 | 17679460117.28 | 1 | 0.6062 | 0.4942 | 1.2740 | 26.2500 | 0.3385 | 83000.00 | 0.014503 |

## Power and verdict

VERDICT: 0/18 PASS — UNDERPOWERED — cannot conclude. No factor is DEAD on this sample.

What would make this conclusive: recover matched completed BTC spot closes, then accrue h=1: ~236 usable days (~170 more than current snapshots, before warmup/imbalance); h=3: ~708 usable days (~642 more than current snapshots, before warmup/imbalance); h=7: ~1652 usable days (~1586 more than current snapshots, before warmup/imbalance); >=31 valid untouched OOS bars, both signs in all purged folds, and independent replication. This targets 80% power for d=0.5 at Bonferroni alpha; no fixed n guarantees a pass.

The power estimates are optimistic: serial dependence of signals, overlapping returns, group imbalance, four-fold sign agreement and the trading gate further reduce power. Failure here does not establish structural cost drag or a population wrong-sign effect.
