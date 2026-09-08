# Flip machine on DAILY bars, pooled across 10 assets — 2026-09-09

Tests Zen's higher-timeframe hypothesis with enough sample to actually measure it. BTC-only daily gave z=2.3 on 626 bars; the sqrt(n) analysis said that was mostly SAMPLE SIZE, not edge decay, so this pools 10 assets at the same ~5 flips/yr each. Folds/training stay per-asset — pooling affects the statistic only, never the fit.

Two arms: **symmetric** (the original D2 machine, long at predicted lows / short at predicted highs) and **long-only** (long at lows, FLAT at highs) — the latter tests whether the loss was the short leg fighting crypto's upward drift.

| arm | pooled z | flip Sharpe | CI lo | equal-wt hold | worst-DD p95 | PASS |
|---|---|---|---|---|---|---|
| symmetric | 9.29 | -0.65 | -1.55 | +0.39 | 84.4% | NO |
| long-only | 9.29 | -0.40 | -1.23 | +0.39 | 76.4% | NO |

**Detection (identical in both arms — same detector, only the position rule differs):** base 0.188 -> precision 0.324 on n_bet=707, **z = 9.29** vs a kill line of 1.645.

## Per-asset (symmetric arm)

| asset | OOS bars | base | precision | flip Sharpe | hold Sharpe | flips/yr |
|---|---|---|---|---|---|---|
| ADAUSDT | 939 | 0.216 | 0.386 | -0.04 | +0.08 | 6 |
| AVAXUSDT | 939 | 0.186 | 0.294 | +0.30 | +0.12 | 7 |
| BNBUSDT | 626 | 0.235 | 0.394 | +0.55 | +0.29 | 12 |
| BTCUSDT | 626 | 0.212 | 0.324 | -0.54 | +0.20 | 5 |
| DOGEUSDT | 939 | 0.157 | 0.292 | -1.12 | +0.49 | 4 |
| ETHUSDT | 939 | 0.179 | 0.353 | -0.27 | +0.18 | 7 |
| LINKUSDT | 939 | 0.209 | 0.300 | -1.18 | +0.10 | 8 |
| LTCUSDT | 626 | 0.190 | 0.143 | +0.41 | +0.03 | 17 |
| SOLUSDT | 939 | 0.104 | 0.241 | -0.53 | +0.46 | 1 |
| XRPUSDT | 626 | 0.224 | 0.500 | -0.40 | +0.83 | 10 |

## VERDICT: FAIL (both arms)

**Detection is REAL and strong at daily bars** — pooling recovers z from BTC-alone's 2.3 to ~9.3, confirming the earlier 'detection collapsed' read was a sample-size artifact, not edge decay. The detector genuinely finds near-lows well above base rate.

**It still cannot be monetised.** Fees are no longer the explanation (~5 flips/yr, versus 67/yr at 1h). Dropping the short leg recovers real ground — the drift-fighting diagnosis was correct — but not nearly enough to reach buy-and-hold.

The binding constraint is that ~32% precision on 'near a low' is a genuine edge that is still not a good enough TIMING signal: being flat during predicted-high stretches forfeits more drift than the avoided drawdowns are worth. Detection != profitable timing, and that gap does not close at any timeframe tested (15m / 1h / 4h / 1d) in either direction.

CAVEAT: crypto majors are correlated, so 10 assets is not 10x independent evidence; the pooled z overstates true independent significance. That cuts against the edge being real, never in favour, so it does not rescue the verdict.