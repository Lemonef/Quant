# Perfect-model SPIKE — entry + exit ML for the stock spike pipeline (design)

Status: DESIGN approved-in-principle (owner 2026-08-01: "both, entry and exit,
all the components"); build gated on the shared PIT corpus below.
Companion: `2026-08-01-perfect-model-research.md` (quant side; tracks A–C died
at their kill tests — the same discipline applies here).

## Two models, one corpus

### S1 — ENTRY: spike-probability ranker
Rank screener-surfaced candidates by P(spike) BEFORE the move. Directly
addresses the standing entry-funnel complaint (big spikers missed) — instead of
tightening hand rules, learn from the misses.
- **Label:** the spike-hunter's own definition of a monster move (large
  gain within the horizon window used by the corpus builder), point-in-time.
- **Features:** the /6 score COMPONENTS as separate inputs (not the collapsed
  score), funnel stage flags (RVOL, breakout, rel-strength), traction/earnings
  metrics from filings, price/volume shape, and — when sweeper A lands —
  the social leads (virality-GIV, DD-post quality, niche-cluster membership).
- **Kill test:** OOS precision@K beats the funnel's realized hit rate by
  >= META_Z standard errors on a preregistered fresh corpus; the miss-autopsy
  list (when it arrives) becomes a held-out probe: does the model rank the
  known misses above the funnel's cut?

### S2 — EXIT: peak-proximity model
The open problem named by the event-replay chain: no skill has an
early-firing masked-PIT sell signal. Predict "within Z days of the spike's
peak" while the spike is running.
- **Label:** distance-to-peak from the realized spike trajectory (peak
  confirmed only in hindsight — training embargoes the confirmation lag).
- **Features:** run shape (gain so far, acceleration, days since entry),
  volume decay, dilution/filing events (v4 detector's P1–P3 fire states as
  inputs), spike-flavor tag.
- **Kill test:** exiting at predicted peaks beats Rule-1 hold-to-thesis-break
  expectancy on the same corpus — the bar event-replay set (mechanical hold
  lost only 0.04R to judged exits; the model must beat THAT, not zero).

## Shared corpus (the real work)

One PIT corpus serves S1, S2, AND sell-detector v4: fresh spike-class names
surfacing after 2026-07-24, built with the existing machinery
(`tools/fresh_corpus_build.py` / `fresh_corpus_replay.py`), labels for
spike outcome, death outcome, and peak timing. Corpus is built ONCE, prereg
locks metrics before scoring, and it burns after one read — same law as every
corpus before it.

## Order of work

1. v4 detector corpus + prereg (already approved) — the corpus build doubles
   as the S1/S2 data foundation.
2. S1 entry ranker (kill test on the same corpus reveal).
3. S2 exit model (needs peak-trajectory labels from the same corpus).
4. Social features join S1 only after sweeper A produces preregistered series.

## Out of scope

Live wiring of any model output (owner-gated), option-flow features for stocks
(no data source), any threshold tuning after a corpus is scored.
