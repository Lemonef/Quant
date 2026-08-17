# basis_flow FULL GAUNTLET — 2026-08-18

Candidate: sign of 28d change in BTC quarterly-futures basis, long on the train-chosen favorable side, daily, net of taker fee + slippage. From FLOWSIG_2026-08-18 (1/12 trials passed the 3-leg line). Kill lines pre-set in this file's header before any number was computed.

| gate | measured | line | pass |
|---|---|---|---|
| G1 bootstrap | excess Sharpe CI [-0.39, 1.43], worst-DD p95 57.0% | CI low > 0 | ❌ |
| G2 lag t+2 | excess Sharpe 0.47 | > 0 | ✅ |
| G3 input noise ×5 | median excess Sharpe 0.42 (min 0.35) | median > 0 | ✅ |
| G4 plateau 21/28/35d | excess Sharpe 0.21 / 0.51 / 0.36 | all > 0 (no cliff) | ✅ |
| G5 CSCV/PBO (6 trial columns, 8 blocks) | PBO 0.23 | <= 0.25 | ✅ |
| G6 Hansen SPA (6 cols) | p 0.419 | <= 0.1 | ❌ |

## VERDICT: **DEAD — logged to the graveyard**

OOS span: 2024-04-04 → 2026-06-06 (794 days). n_trials in the search-correction matrix: 6 signal overlays (the flowsig search space).

Adoption path if survivor: prereg (entry/exit/costs/sizing declared) → Codex gate → shadow sleeve in data.json next to the book — same law as every edge; the gauntlet alone adopts nothing.