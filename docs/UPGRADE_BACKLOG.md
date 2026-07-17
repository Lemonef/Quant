# Upgrade backlog — triaged, parked, not lost

Items collected during the 2026-07 upgrade research sweep. Each entry keeps its
provenance so it can be traced back. Nothing here is adopted without passing the same
bar as everything else: tested / measured before promotion.

**Strip-mining rule:** no source is rejected wholesale. Every source is mined for
usable parts first; the rejected list records only the remainder, and salvaged parts
are noted where they landed. (Second-pass salvage 2026-07-14: survivorship-bias
handling → spec; Markov regime-switching + FRED macro factors → below; GS-Quant
timeseries as metric reference → spec.)

Active project: **Alpha Factory** — see
`docs/superpowers/specs/2026-07-14-alpha-factory-design.md`. Absorbed into that design
(not listed below): Alpha158/Jansen factor families, Kalman spread factors, GARCH-style
vol-regime factors, Williams VIX Fix capitulation family, IC/ICIR + signal-decay
scoreboard, GBM synthetic-data harness tests, universe expansion.

## Factory iteration queue (from run findings)
- ✅ **Rebalance-frequency variant — DONE 2026-07-15 (commit 8ab6caf).** Every factor
  now judged at 1d/5d/20d (p-value from the traded-horizon IC with overlap correction,
  pooled BH-FDR across all factor×speed rows, n_trials ×3 in the deflated Sharpe).
  Result on the expanded 22-pair universe (crypto + PAXG gold + EURUSDT): **0 survivors
  at any speed.** Slower trading cuts cost-death rejections 66→25→19 and lifts median
  family Sharpes by up to +2.5 (seasonality −2.36 → +0.11), but the freed signals
  plateau at ≈0 — every FDR-passer keeps at least one negative OOS fold (best −0.11).
  Consistent with the brain's hard constraint: cross-sectional directional entries ≈
  random; the edge remains regime + diversification + carry. Scoreboard:
  `backtest_results/ALPHA_FACTORY_2026-07-15-speeds.{md,csv}` (daily-only baseline kept
  at `ALPHA_FACTORY_2026-07-15.{md,csv}`).
- pandas `pct_change` FutureWarning cleanup (`fill_method=None` where series are
  contiguous) — cosmetic, verify results unchanged before/after.
- Factory v2 statistics (queued 2026-07-15, from the techniques survey; build in this
  order): block-bootstrap CIs on fold Sharpes (cheapest, already a June TO-REVISIT) →
  lag/noise perturbation gates → parameter-plateau check for survivor configs →
  CPCV + PBO (distributional OOS + overfit probability) → Hansen SPA on the top
  survivor before any promotion. Reference: brain `skills/backtest-validation-SKILL.md`
  § QUEUED TECHNIQUES.

## Perfect model research (named project — Zen, 2026-07-15)
Goal as stated: a model that enters near the exact swing low and exits/shorts near the
exact swing high. State of the art: turning-point prediction is a real published line of
work — zigzag/extrema labeling, triple-barrier + meta-labeling (López de Prado,
*Advances in Financial Machine Learning*), peak/trough classifiers — but all of it
predicts local extrema probabilistically; sustained near-exact top/bottom timing net of
costs is not an established result. Extrema labels are scarce and noisy, so this design
has the highest overfit risk of anything in the backlog (acknowledged up front).
Implementation route: build ON the phase-2 ML ranker infrastructure — extrema /
triple-barrier labels over the factory factor panel, class-imbalance handling,
meta-label entry filter — and judge it under the full factory gate set (purged
walk-forward, pooled FDR, deflated Sharpe, improvement-vs-book). **Trigger: starts after
the multi-speed factory iteration and the factory-v2 statistics queue land; it is the
flagship phase-2 experiment, not a separate system.**
Zen's conviction note (2026-07-16): he believes this collaboration could be first to
invent a genuinely new strategy from some untried combination — treat the project not
only as replication of published turning-point work but as open-ended invention;
novel-mechanism ideas welcome at trigger time, judged under the same gates.

## Phase 2 — ML ranker (queued behind Alpha Factory)
- **Options-derived signal family (colleague tip via Zen, 2026-07-16) — NEW INFORMATION, best of the batch.**
  Crypto options data is free (Deribit public API: IV, put/call OI, term structure; CoinGlass/
  Coinalyze: max-pain, per-expiry notional). Candidate zoo factors: implied-vol level/percentile
  (fear gauge), put-skew (crash insurance demand), put/call OI ratio, IV-vs-realized spread
  (variance premium), distance-to-max-pain into major expiries (pin-risk hypothesis — evidence
  in equities is weak/mixed; treat as hypothesis, not lore), post-expiry drift. All judged under
  factory gates like any factor. This is genuinely NEW information (positioning + fear), unlike
  price-derived indicators.
- **Multi-pair stat-arb (colleague claims ~9%/wk) — TESTED-DEAD here, claim needs evidence.**
  Naive pairs + cointegration (incl. Kalman/OU) are in the dead pile (failed honest OOS ~30-way
  sweep), and the factory's Kalman-spread family died again at all 3 speeds (2026-07-15 run).
  "Many pairs" diversifies the same dead edge. 9%/wk ≈ +8,700%/yr compounded — extraordinary;
  plausible explanations: short lucky sample, hidden leverage, maker-rebate/zero-fee venue,
  or intraday frequency (blocked for Zen by the HFT wall). REOPEN ONLY IF: colleague shares a
  verifiable track record ≥6mo + the venue/fee structure, then replicate under factory rules
  at OUR fees first. Do not build on the claim alone.
- Alpha-decay concept (same tip): already core factory machinery — IC decay horizons + the
  multi-speed variant exist precisely because of it. Nothing new to build.
- Cross-sectional ML ranker (LightGBM-style, scikit-learn) trained on the factory's
  factor panel; evaluated under the same purged walk-forward + FDR rules.
  _Provenance: Qlib workflow, Machine-Learning-for-Trading (Jansen)._
- Markov regime-switching model as a regime-filter challenger to the SMA-based
  regime A/B currently live-tested; evaluate under factory rules. _Provenance:
  Financial-Models / Computational-Finance repos (second-pass salvage)._
- Macro overlay factors from FRED (DXY, rates, credit spreads) as regime features
  for the crypto book. Free data. _Provenance: "Bridgewater macro" prompt
  (second-pass salvage of its inputs, not its LLM-dashboard form)._
- Rebalancing-premium sleeve ("volatility harvesting" / Shannon's demon): fixed-weight
  basket, mechanical rebalance sells high / buys low — the spot-only analog of gamma
  scalping's realized-vol capture. Evaluate under factory rules incl. fee/turnover
  reality (rebalance frequency is the cost knob). _Provenance: gamma-scalping ask,
  strip-mined (2026-07-14)._

## Phase 3 — stock side (spike-hunter)
- Stock daily-OHLCV panel through the same factory harness → systematic pre-screen
  feeding the daily shortlist (LLM stays the judge). _Provenance: phase-1 design._
- Adversarial bear pass: a "short-seller attacks this thesis" step before any name
  enters 🆕 PROPOSED ADDITIONS; report shows attack + survival. _Provenance: viral
  prompt list, matches the blind-judge adversarial pattern already in use._
- Transcript forensics: for shortlisted names, pull earnings call / filing via the
  Bigdata MCP; extract tone shift, guidance walkbacks, dodged questions as one data
  row in the deep-dive. _Provenance: viral prompt list._
- Cohort correlation audit in the weekly review: which held names crash together,
  single-event exposure, concentration score (the June defense-cohort de-rate would
  have flagged). _Provenance: viral prompt list (portfolio exposure audit)._
- Deep-dive fundamentals upgrades from the family investing lessons (brain:
  `atoms/investing-lessons-family-2026-07.md`): explicit 10-year revenue-path math in
  the verdict ("would the price still make sense at credible-growth revenue");
  earnings-quality row (GAAP/revenue-recognition/by-function-vs-nature red flags);
  SG&A trend + FCF-vs-net-income divergence rows; liquidity row (current ratio, cash
  cycle); YoY base-effect flag (which quarter drives the jump); unit-economics-vs-
  peers row; margin-risk taxonomy (cost-push/demand-pull, cost overrun, realized-
  price-below-forecast); BOI tax check for Thai names. _Provenance: family investor
  lesson, 2026-07-14._
- Factory zoo candidates from the same lessons: "open ≈ close → don't buy" (doji/
  indecision, candle-shape family) and Darvas-box variants (box breakout + trail
  under box lows — same family as the live Donchian core, so mostly a parameterization
  test). Adopted only if they survive. _Provenance: family investor lesson._
- Additional deep-dive reads from Zen's clarifications: margin-of-safety framing in
  verdicts (state intrinsic-value estimate + discount paid); quarter-decomposition
  read (hidden strength AND weakness, e.g. flat annual profit despite a disclosed
  −50% final quarter = three strong quarters hiding); company capex-timeline read
  (weak quarter may be money-not-deployed-yet); capital-allocation structure read.
  _Provenance: family investor lesson (clarified 2026-07-14)._
- **Composite fundamental scores as pre-screen factors: Piotroski F-Score, Beneish
  M-Score (manipulation), Altman Z-Score (bankruptcy distance)** — computable from
  free fundamentals (EDGAR/yfinance), backtestable under factory rules; the
  systematic form of the statement-analysis checks. Full catalog of statement
  gap-finding checks: brain `atoms/financial-statement-insight-playbook.md`.
  _Provenance: settled forensic-accounting canon, prompted by family lessons._

## Go-live gate (before real money, any asset class)
- Execution-quality checklist: spreads, slippage, order types, fee totals, fill-price
  tracking vs quote at order time. _Provenance: "Jane Street microstructure" prompt —
  the one keeper of that batch._

## Someday/maybe — named so it stays a deliberate choice
- **Slow value book** (Buffett-style second book: hard-to-kill businesses at a
  margin-of-safety discount, multi-year holds; no catalysts required). Deliberately
  NOT started 2026-07: different animal from spike-hunting; revisit when real capital
  is deployed and the verdict ledger (≥50 resolved) shows which judgments to trust.
  The margin-of-safety discipline itself ships NOW inside the spike verdicts instead.
  _Provenance: family investing lessons._
- **Spike-hunter skill upgrade delivery path** (when phase-3 rows ship): the daily
  routine reads `skills/stock-analysis-SKILL.md` from the brain → implement by
  editing the skill file + the locked report-format doc; validate with an A/B
  deep-dive on one sample ticker (old vs new checklist) before committing. No
  cloud-routine prompt edit needed.

## Infra / cosmetic (independent projects)
- Dashboard UI glow-up for the web pages; reference aesthetics: linear.app, notion,
  vercel, sodaven.com, storytelling.noomoagency.com, harmony. Use installed design
  skills.
- Agent tooling to evaluate someday: andrej-karpathy-skills, obsidian-skills,
  Agent-Reach repo, "Omega prism". Separate from quant work.
- Fable/Claude use-case ideas (from a viral list): clone paid apps locally (e.g. a
  Whisper-Flow-alike — research its architecture first), /goal-style workflows, audit
  runs, "visual agentic OS", bug hunts, ship-from-a-single-PRD. Evaluate case by case.
- Awesome-Quant: link index only — the place to look when hunting for a library or
  reference on a specific quant topic; nothing to build from directly.

## Resolved references
- "RSI + Alchemist" = "The Alchemist's Trend" (TradingView indicator, wjdtks255):
  trend-condition labels + RSI 30-70 context + volume confirmation. Not adopted as a
  bundle — its three ingredients are already factor families in the factory zoo
  (trend, oscillator, volume); the factory evaluates the combination honestly.

## Free data sources (the "Bloomberg for free" answer — researched 2026-07)
- **OpenBB** (open-source terminal) — the closest free Bloomberg-alike; aggregates
  most sources below behind one Python API/CLI.
- Crypto prices/funding: **Binance public API** (in use — still the primary; free and
  deep). Aggregators: CoinGecko demo tier (10k calls/mo, includes derivatives
  tickers with funding + open interest), CryptoDataDownload (free historical CSVs,
  non-commercial license).
- Crypto derivatives analytics: **Coinalyze** and **CoinGlass** — open interest,
  funding history, liquidations across exchanges (free web/limited API). New factor
  inputs: OI-based and liquidation-based factors → candidate zoo family (phase 2).
- Stock EOD prices: yfinance (in use; unofficial — breaks/rate-limits occasionally,
  keep Stooq CSV as fallback), Polygon free tier (1y EOD history).
- Broad free API tiers (2026): **Twelve Data** ~800 req/day (most generous),
  **Finnhub** ~60/min incl. free WebSocket quotes AND congressional-trading data
  (extra source for the spike-hunter's gov/insider row), Alpha Vantage ~25 req/day.
- Filings/fundamentals: SEC EDGAR (free, canonical), stockanalysis.com (in use),
  Financial Modeling Prep free tier.
- Macro: FRED (Federal Reserve, free) — feeds the macro-overlay factor idea above.
- Insider/government: OpenInsider, QuiverQuant (both already in the spike-hunter),
  plus Finnhub congressional trading as cross-check.
- Real Bloomberg: only via a university finance-lab terminal (on-site export).
- Licensing note: several free tiers are non-commercial (CoinMarketCap,
  CryptoDataDownload CSVs) — fine for personal research, check before any product use.

## Explicitly rejected (with reason, so they stay rejected)
- LLM-imagined backtests ("Two Sigma simulator" prompt): fabricated numbers; the real
  engine + factory exist.
- Chart-pattern technical analysis packs: repo history shows TA variants lose OOS
  (`backtest_results/IMPROVEMENTS_TRIED.md`).
- Options/derivatives strategy material (GS-Quant, pricing-course repos, D.E. Shaw
  prompt, gamma scalping, delta hedging in their true options form): no options
  traded. Revisit only if an options leg is ever added (crypto options = Deribit;
  free public API incl. implied-vol data). Salvage already extracted: the carry
  sleeve is a live delta-neutral (hedged) structure; gamma scalping's spot-only
  cousin is below.
- Bloomberg terminal data: requires a paid terminal login; university lab access is
  the realistic route. Free sources cover current needs.
- Server-side web patterns (Redis, bloom filters, cache-null TTL, TanStack Query):
  static Pages site has no server; no cache problem at current scale.
- Managed vector DB / LangChain / Pinecone RAG: the brain's local hybrid search
  (`tools/semantic_search.py` v2) already covers retrieval at vault scale.
- "Act as a senior X" prompt packs: use the installed skills/commands instead — see
  brain `memory/claude-code-tooling-map.md`.
