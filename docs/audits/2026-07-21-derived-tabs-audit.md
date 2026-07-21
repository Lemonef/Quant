# Derived-tabs audit — carry-class bug hunt (2026-07-21)

Read-only verifier audit of every derived dashboard tab in `live_bot/paper_bot.py`
(`write_webdata`) + `web/build_board.py`, following the 2026-07-17 carry-tab fix.
Verdict: carry fix held for side changes; same bug class present in four other tabs.

## Blockers
1. `paper_bot.py:266` — `fetch("BTCUSDT", limit=1300)`: Binance clamps klines to 1000
   (verified live) → `rolling(1200)` all-NaN → 100/200 tab's BTC leg permanently zero;
   the 50/150-vs-canonical A/B compares against a dead strategy.
2. `paper_bot.py:224-226` — Book v2 bear multiplier uses `regk[i+1]` (end-of-window
   regime) to scale `tr[i]` (that window's return): look-ahead — the flip-triggering
   loss is dodged. Correct index: `regk[i]`.
3. `paper_bot.py:345-349` — `hr_lev` decided from CURRENT funding, multiplied into all
   history each run: retroactive signal; displayed history mutates day to day.

## Majors
- Free regime-flip teleports, zero cost: Regime A/B (`:271`, 40% BTC<->cash), Book v2
  (12 flips x 70% notional). Carry-class recurrence.
- Carry froth gate (`:392-393`): 0.3<->1.0 size jump on both legs, no hysteresis, no
  cost — fix charged side changes only.
- Positional kline<->cycle alignment (`:241-243,264-272,297-298,333-340`): 207 rows vs
  238 bars, 102 non-4h gaps measured; timestamps exist but ignored (index-join).
- 50/150 warmup: `fillna(False)` renders first ~105/205 cycles fake "cash".

## Minors
- PAXG fetch clamp time-bomb (~Dec 2026: gold legs silently zero).
- ETH funding gaps bridged with BTC's rate (`:387`).
- Inline literals: 0.4/0.4, 0.5/0.5 (5 sites), 0.90/5.0 CPPI, 0.00005 gate,
  `(n-1)*10` financing in build_board.py:252.
- Blend tabs: frictionless per-cycle rebalance idealization undisclosed.

Fix decisions + implementation: see fix commit(s) referencing this file.

## Resolution (2026-07-21)
Fixes merged (`0268919`): all blockers/majors addressed per DD1-DD9; verifier verdict
MERGE (0 blockers/majors). `board.html` regenerated; `data.json` regenerates on the
next scheduled bot cycle — derived-tab/deploy reads valid only after that run.

Accepted follow-ups (verifier minors/spec-gaps, none flattering to results):
1. Cost-model consistency: side cost flat vs gate/flip cost |delta|-scaled — currently
   overcharges small positions (conservative). Decide one convention.
2. Book v2 regk head-aligned fallback: dead branch today; add a loud failure if
   `regime_log.csv` is ever shorter than the equity tail (silent look-ahead risk).
3. Funding fetch `limit=1000` unpaginated (klines got pagination, funding did not);
   pre-history cycles default to HR_LEV_COOL silently once equity outgrows it.
4. BTC/ETH funding join is exact-ms; tolerance-window join more robust (failure mode
   today is the honest skip+count path).
5. `eth_funding_skipped` not rendered in the UI.
