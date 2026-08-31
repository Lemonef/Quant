# Trend-efficiency-gated flip machine (D2 reopen trigger b, 2nd mechanism) — 2026-08-31

Gate: Kaufman efficiency ratio(20 bars) >= 0.5 (net progress >= half the path length traveled — chop has large path length but small net progress, so this differs from a raw volatility-SIZE gate). Detector/labels/folds/costs = extrema.track_d2_kill verbatim. Kill line = D2's 3 legs. n_trials = 2 series x 1 gate; ungated rows = the D2 baseline for the paired read.

**Context: the plain SIZE gate (flipgate_test.py, 2026-08-19) already failed** — gating on raw vol magnitude made flips WORSE (67->188/yr, Sharpe -0.84->-1.16 on 1h) because big-but-choppy periods passed the gate too. This test asks a different question: does gating on DIRECTIONAL PERSISTENCE (not size) behave differently?

| series | gated | OOS bars | near-low z | flip Sharpe | CI lo | hold Sharpe | active | flips/yr | worst-DD p95 | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT_1h | no | 22536 | 18.3 | -0.84 | -1.80 | 0.66 | 100% | 67 | 93.7% | ❌ |
| BTCUSDT_1h | YES | 22536 | 18.3 | -2.68 | -3.58 | 0.66 | 8% | 190 | 78.9% | ❌ |
| BTCUSDT_4h | no | 5634 | 8.7 | -0.22 | -1.23 | 0.65 | 100% | 32 | 87.9% | ❌ |
| BTCUSDT_4h | YES | 5634 | 8.7 | -1.11 | -2.04 | 0.65 | 10% | 58 | 66.3% | ❌ |

## VERDICT: 0/2 gated rows pass

Read: if the efficiency gate lifts flip Sharpe above hold with CI lo > 0 AND reduces (not increases) flip frequency vs the ungated baseline, trend-persistence (not swing size) was the missing condition. If it also fails, both mechanisms of the 'bigger-swing regime filter' reopen trigger are exhausted; remaining doors = zero-cost venue, options/GEX data.