# PRE-REGISTRATION — GEX level → forward realized volatility (2026-10-15)

_Written BEFORE any test of this specification is run. Do not edit the hypothesis, definitions, kill line or
trigger after data is seen; amendments go in a dated section at the bottom and invalidate the run they follow._

## Why this exists

`OPTIONS_FACTORS_2026-10-15.md` tested GEX **sign** against forward **returns**. Two problems surfaced:

1. **The sign never flipped.** Net dealer gamma held one sign for all 66 days (2026-08-10 → 10-14), so a sign test
   cannot run until it does. A level-based split was deliberately not substituted after seeing the data.
2. **The target was mis-specified.** GEX's mechanism concerns **volatility, not direction**: long-gamma dealers hedge
   against moves (sell rallies, buy dips) which dampens realised volatility; short-gamma dealers hedge with moves,
   amplifying it. A returns test asks GEX a question its mechanism does not answer.

## Hypothesis (one-sided, declared)

**H1:** higher net dealer gamma (relative to its own recent history) predicts **lower** forward realised volatility of
BTC, **after controlling for recent realised volatility.**

The control is not optional. Volatility is strongly persistent, and GEX may simply track recent calm; without the
control any correlation could be RV forecasting RV.

## Definitions (frozen)

- **GEX_t** — exactly as `backtest/options_factor_test.py` computes it (Black-76 gamma from mark IV, OI, 1 BTC
  contract size, spot², calls +1 / puts −1, all live expiries), from the snapshot published by day t.
- **Signal_t** — z-score of GEX_t against its trailing 30 calendar days (≥20 valid observations required).
- **Target** — realised volatility of BTC daily log returns over (t+1 … t+h), annualised √365, for **h = 1 and 5**.
  (h=1 uses absolute next-day return as the single-day RV proxy.)
- **Control** — trailing realised volatility over (t−19 … t), same construction.
- **Publication lag** — +1 day, as in the parent test.

## Test and kill line (frozen)

- Statistic: **partial Spearman correlation** of Signal_t with forward RV, controlling for trailing RV.
- Inference: Newey–West standard errors with lag = h + 5 (overlapping targets at h=5).
- **PASS requires all of:** (a) partial ρ < 0 with |t| ≥ 2.24 (Bonferroni over the 2 horizons at α = 0.05 one-sided
  → 0.025); (b) the sign of partial ρ agrees in every purged walk-forward fold (≥ 4 folds, 10-day embargo);
  (c) on the untouched final 20% of the sample, the sign holds.
- Anything else = FAIL. A FAIL with fewer days than the trigger below is reported as UNDERPOWERED, not dead.
- Trials: **2** (two horizons). No other specification is to be run on this data without a new pre-registration.

## Run trigger (frozen)

Do **not** run before **≥ 200 usable days** of snapshots. Power basis: detecting ρ = −0.3 at α = 0.025 with 80% power
needs ≈ ((2.24 + 0.84) / atanh(0.3))² + 3 ≈ 102 independent observations; realised volatility is strongly
autocorrelated, so effective n is materially below calendar n — ~2× headroom is assumed. At the collector's daily
cadence from 2026-08-10, **200 usable days ≈ late February 2027.** Also run early if GEX changes sign, since that
event alone is informative.

## What a PASS would and would not mean

A PASS means GEX carries volatility information beyond recent volatility — useful for **sizing and regime**
(e.g. scaling the trend sleeve, or timing the carry sleeves), not as a directional signal. It would not justify a
trading rule by itself; adoption follows the repo's usual law: prereg → gauntlet → Codex gate → shadow.

## Amendments
_None._
