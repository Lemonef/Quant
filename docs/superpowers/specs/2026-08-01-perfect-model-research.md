# Perfect-model research — phase-2 predictive ML (proposal, pre-approval)

Status: PROPOSAL — awaiting owner approval before any build.
Prerequisite (met 2026-08-01): the factory statistics gauntlet (bootstrap CIs,
perturbation, plateau, CSCV/PBO, Hansen SPA) is implemented and every candidate
below must pass it. Provenance: López de Prado AFML (triple-barrier,
meta-labeling, CPCV); factory findings 2026-07-15 → 2026-08-01.

## What the evidence already says

1. Cross-sectional directional entries on the 22-coin daily panel are ≈ random
   (0 survivors; SPA p 0.278, PBO 0.19 — the search itself is honest, there is
   no edge to promote).
2. The ML ranker LEARNS real OOS rank structure (IC 0.04–0.09, p ≤ 1e-12) but
   net Sharpe is negative at every speed: the failure is TRANSLATION
   (signal → positions net of costs), not model capacity.
3. The book's live edges are time-series (trend/carry family), not
   cross-sectional.

Any phase-2 model that ignores (2) repeats it. The research question is
therefore not "predict better" but "predict something whose monetization
survives costs".

## Candidate tracks (each = cheap kill test first, then the full gauntlet)

### Track A — Meta-labeling on the incumbent book (primary; direct AFML fit)
Predict WHEN the already-deployed sleeves' entries win: label each incumbent
entry with the triple-barrier outcome (profit-take / stop / time-out), train a
classifier (HistGB, same shallow-tree discipline as the ranker) on
signal-state features at entry. Output = bet/no-bet (or size) on top of an
existing edge — no new turnover is created, so the ranker's translation failure
is structurally avoided. Kill test: does OOS precision beat the base win rate
on ≥ 200 entries?

### Track B — Turnover-aware translation of the ranker's IC (salvage)
The IC exists; monetization died on turnover. Variants, in order of cheapness:
prediction smoothing (EWMA of scores), no-trade bands around current holdings,
slower-horizon-only trading (20d model at 20d speed showed Sharpe ≈ 0, the
least-negative row), cost-penalized objective. Kill test: any variant with
net Sharpe > 0 on all OOS folds.

### Track C — Regime / turning-point classification (time-series, not
cross-sectional)
Forecast the anchor's regime (trend / chop / crash-risk) from realized-vol
structure, funding, breadth; gate the incumbent sleeves by predicted regime.
Extends the SMA-filter A/B already in the book with a learned switch.
Kill test: regime-gated book beats the ungated book OOS after costs.

### Track D — Spike-probability model (NN/GBM; owner's original ask)
P(large move within h days) per coin from the same feature panel; monetized
asymmetrically (options-like payoff not available on-venue, so sized entries
with wide stops). Highest variance of the four; runs LAST unless a kill test
surprises.

## Rules of engagement

- Order: A → B → C → D. One track at a time; a track dies at its kill test or
  earns the full gauntlet (FDR + folds + decay + DSR + CIs + perturbation +
  plateau + PBO + SPA — n_trials counts every variant tried).
- Same leakage discipline as the ranker: purged walk-forward, label-overlap
  purge, embargo; features causal by construction.
- Shallow-capacity models only until a kill test justifies more (the
  "simplest model that survives validation" rule).
- Every dead track logged in the strategy-test ledger with its kill evidence.

## Out of scope

Options-derived factors (separate queue item), order-book/L2 models (parked,
infra-heavy), any live deployment decision (owner-gated regardless of results).
