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

## Phase 2 — ML ranker (queued behind Alpha Factory)
- Cross-sectional ML ranker (LightGBM-style, scikit-learn) trained on the factory's
  factor panel; evaluated under the same purged walk-forward + FDR rules.
  _Provenance: Qlib workflow, Machine-Learning-for-Trading (Jansen)._
- Markov regime-switching model as a regime-filter challenger to the SMA-based
  regime A/B currently live-tested; evaluate under factory rules. _Provenance:
  Financial-Models / Computational-Finance repos (second-pass salvage)._
- Macro overlay factors from FRED (DXY, rates, credit spreads) as regime features
  for the crypto book. Free data. _Provenance: "Bridgewater macro" prompt
  (second-pass salvage of its inputs, not its LLM-dashboard form)._

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

## Go-live gate (before real money, any asset class)
- Execution-quality checklist: spreads, slippage, order types, fee totals, fill-price
  tracking vs quote at order time. _Provenance: "Jane Street microstructure" prompt —
  the one keeper of that batch._

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
  prompt): no options traded. Revisit only if an options leg is ever added.
- Bloomberg terminal data: requires a paid terminal login; university lab access is
  the realistic route. Free sources cover current needs.
- Server-side web patterns (Redis, bloom filters, cache-null TTL, TanStack Query):
  static Pages site has no server; no cache problem at current scale.
- Managed vector DB / LangChain / Pinecone RAG: the brain's local hybrid search
  (`tools/semantic_search.py` v2) already covers retrieval at vault scale.
- "Act as a senior X" prompt packs: use the installed skills/commands instead — see
  brain `memory/claude-code-tooling-map.md`.
