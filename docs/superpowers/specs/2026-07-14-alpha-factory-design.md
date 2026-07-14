# Alpha Factory — design spec (2026-07-14)

Systematic factor-mining pipeline for the crypto research side. Replaces one-off
hand-written strategy test scripts with a single harness that computes a large library
of candidate signals ("factors") over the existing data panel, evaluates every one with
walk-forward discipline, applies multiple-testing statistics that punish mass-testing
luck, and emits a ranked scoreboard with SURVIVED / REJECTED verdicts.

## Problem

Strategy research currently tests one hand-crafted idea per script (~60 files in
`backtest/`). The documented history (`backtest_results/IMPROVEMENTS_TRIED.md`) shows
most ideas win in-sample and lose out-of-sample; the honest robust ceiling found so far
is Sharpe ~1.0-1.1. The weekly review has repeatedly recorded "frontier exhausted — no
new testable idea." The bottleneck is idea *throughput with honest evaluation*, not
evaluation discipline (which exists) or engine quality.

## Goals

1. Test hundreds of candidate factors per run instead of one per session.
2. Make overfitting mathematically detectable instead of manually policed: purged
   walk-forward, IC statistics, deflated Sharpe, FDR correction across the whole zoo.
3. Reuse the existing engine, data, and cost assumptions — no new platform.
4. Produce a repeatable artifact: a ranked scoreboard report per run.
5. Keep the harness asset-class-agnostic so a stock panel can run through it later
   (phase 3).

## Non-goals (out of scope for phase 1)

- No ML models (phase 2 consumes this pipeline's factor panel).
- No changes to `live_bot/`, the paper-bot workflow, or the dashboard.
- No stock-side changes (phase 3).
- No new paid data sources.
- No automatic promotion of survivors into the book — promotion stays a human decision.

## Architecture

New package `backtest/alpha_factory/` beside the existing scripts:

```
backtest/alpha_factory/
  panel.py          # data panel construction (reuses engine.py / existing loaders)
  zoo.py            # operator library + factor definitions with provenance tags
  evaluate.py       # per-factor IC / quantile-portfolio evaluation, purged walk-forward
  stats.py          # deflated Sharpe, FDR (Benjamini-Hochberg) across the zoo
  report.py         # scoreboard rendering (markdown + CSV)
alpha_factory.py    # CLI entry point (in backtest/)
tests/              # synthetic-data validation of the harness itself
```

### panel.py — data panel

- Builds the daily panel (close, OHLCV aggregates, funding) from `backtest/data/`
  using the exact conventions of `alphas.py`/`factor.py`: merged `*_bear_4h` + `*_4h`
  history, deduplicated, resampled to daily; universe = every coin with full data
  (self-measuring — derived from the data directory, never a hardcoded list).
- Universe expansion step: reuse the `fetch_universe.py` machinery to pull the top-N
  liquid Binance USDT pairs (N is one named config constant). Prior finding: expanding
  10→20 coins lifted OOS Sharpe 0.61→0.91 and saturated ~15-20; the wider panel gives
  the cross-sectional factors more breadth.
- **Survivorship-bias handling (required)**: selecting today's top-N coins excludes
  coins that died, inflating results. Mitigation: select the universe by liquidity as
  of the *start* of the evaluation window where the data allows (point-in-time
  selection); where it does not, the report must carry an explicit survivorship-bias
  caveat on every affected metric. The same rule applies verbatim to the phase-3 stock
  panel (delisted names).

### zoo.py — factor library

Small composable operators (rolling mean/std/rank/corr, delta, decay-weighted sums,
cross-sectional z-score/rank) plus factor definitions built from them. Each factor
carries metadata: name, family, provenance (which reference source it was adapted
from), and formula.

Factor families (~100-160 total):

| Family | Contents | Provenance |
|---|---|---|
| K-bar / candle shape | body/wick ratios, close position in range | Qlib Alpha158 |
| Momentum / reversal | multi-horizon returns, ts-rank of price, reversal at short horizons | Qlib Alpha158, Jansen |
| Volatility | realized vol levels/ratios, vol-of-vol, GARCH-style clustering proxies | Jansen; Financial-Models / Computational-Finance (concept-mined) |
| Volume / liquidity | volume z-scores, price-volume correlation, turnover proxies | Qlib Alpha158 |
| Capitulation / panic | Williams VIX Fix, drawdown-from-rolling-high spikes | TikTok lead, validated as a factor candidate; overlaps live flush sleeve — factory arbitrates |
| Carry / funding | funding level/trend/cross-sectional rank | existing `alphas.py` carry |
| Spread / pairs | Kalman-filter hedge-ratio spread z-scores on cointegrated pairs | Financial-Models (concept-mined); upgrade of `statarb_pairs_test.py` |
| Seasonality | day-of-week/month effects | existing `seasonality_scan.py` idea |
| Baselines | the 5 existing `alphas.py` alphas (trend, xsmom, carry, rsi2dip, tsmom) | in-repo; sanity anchors |

### evaluate.py — per-factor evaluation

For each factor, on the daily panel:

1. **IC analysis**: cross-sectional Spearman rank IC against forward returns at
   multiple horizons (1d, 5d, 20d) → mean IC, IC-IR (mean/std), and **decay profile**
   (how fast the signal dies; short-lived signals that only pay fees get flagged).
2. **Quantile long-short portfolio**: rank coins by factor daily, long top-K / short
   bottom-K (K derived from universe size), dollar-neutral, next-day execution
   (`shift(1)` — no same-bar fills), with the repo's existing cost assumptions (taker
   fee, short borrow), a configurable per-trade slippage haircut (real fills are worse
   than quotes; one config constant), and turnover accounting.
3. **Purged walk-forward**: contiguous folds over the full history with an embargo gap
   between train/eval boundaries so no leakage crosses folds; per-fold OOS metrics
   reported separately (never blended into one flattering number).

### stats.py — anti-fooling layer

- Metric formulas (returns, vol, drawdown, Sharpe) cross-checked against the open
  GS-Quant `timeseries` module as a reference implementation.
- **Deflated Sharpe ratio** per factor given the number of trials in the run.
- **FDR control (Benjamini-Hochberg)** across the entire zoo's OOS results.
- Survival requires ALL of: passes FDR at the configured rate, positive OOS result in
  every fold, decay horizon above the minimum useful holding period, and
  turnover-adjusted economics that survive costs.

### Improvement gate vs the incumbent book (required)

Statistical survival is necessary but not sufficient. Every survivor is additionally
measured against the existing book:

1. **Correlation to each incumbent sleeve** (the 5 `alphas.py` alphas) — a survivor
   highly correlated to an existing sleeve is flagged REDUNDANT, not an improvement.
2. **Ensemble delta**: OOS metrics of the incumbent ensemble (inverse-vol weights, as
   in `alphas.py`) WITH the survivor added vs WITHOUT it. The report states
   `IMPROVES BOOK: yes/no (ΔOOS Sharpe, ΔmaxDD)`. Only survivors with a positive
   ensemble delta are promotion candidates.

### report.py + CLI

`python backtest/alpha_factory.py` runs panel → zoo → evaluate → stats and writes
`backtest_results/ALPHA_FACTORY_<date>.md` (+ `.csv`): one row per factor — family,
provenance, IC/IC-IR per horizon, decay, per-fold OOS Sharpe, deflated Sharpe, FDR
verdict, turnover, and SURVIVED/REJECTED with the failing criterion named. Config
(fold count, embargo length, FDR rate, K, cost rates, universe size N) lives in one
constants block at the top of the CLI — single source of truth, no magic numbers
scattered through modules.

## Validation (the harness must prove itself before judging factors)

pytest suite on synthetic data, runnable without real data files:

1. **Planted signal**: GBM price paths with an injected predictive signal → the
   corresponding factor must rank near the top and SURVIVE.
2. **Pure noise**: all-noise factors → survivors must not exceed the configured FDR
   rate (statistical bound, not zero).
3. **Leak detection**: a deliberately look-ahead factor (uses same-day return) must be
   caught by the purged-split/shift conventions (its live-executable variant shows no
   edge).
4. **Baseline reproduction**: the 5 existing alphas reproduce their known qualitative
   OOS behavior on real data (carry positive; most others weak) — anchors the harness
   against the repo's documented history.

GBM path generation for tests is the concept-mined use of the stochastic-process
material (Monte Carlo / GBM) from the reference notebooks.

## Honest expectations

Most of the zoo will be rejected — that is the machine working as designed. Value:
(a) those ~150 ideas never need hand-testing again; (b) anything that survives did so
against deflated statistics, not enthusiasm; (c) phase 2 (ML ranker) consumes this
exact factor panel.

## Roadmap context

- **Phase 1 (this spec)**: Alpha Factory on the crypto panel + universe expansion.
- **Phase 2**: cross-sectional ML ranker (LightGBM-style, scikit-learn stack) trained
  on the factor panel, evaluated by the same harness rules.
- **Phase 3**: stock daily-OHLCV panel through the same harness → systematic pre-screen
  feeding the spike-hunter shortlist. Same survival bar.

Promotion of any survivor into the live book remains a human decision, made the same
way existing sleeves were promoted.

## Success criteria

1. All four validation tests pass.
2. One command produces the full scoreboard on the real panel.
3. The run completes on the existing data without touching `live_bot/` or the web
   pipeline.
4. The report names, for every factor, exactly why it survived or was rejected.
