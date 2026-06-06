# Graph Report - d:/Quant  (2026-06-07)

## Corpus Check
- Corpus is ~20,485 words - fits in a single context window. You may not need a graph.

## Summary
- 49 nodes · 63 edges · 14 communities (7 shown, 7 thin omitted)
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 10 edges (avg confidence: 0.84)
- Token cost: 0 input · 70,150 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Obsidian Plugins Config|Obsidian Plugins Config]]
- [[_COMMUNITY_Donchian SOL Backtest Metrics|Donchian SOL Backtest Metrics]]
- [[_COMMUNITY_Project Docs & Sweep|Project Docs & Sweep]]
- [[_COMMUNITY_Obsidian App Config|Obsidian App Config]]
- [[_COMMUNITY_Donchian Strategy & Filters|Donchian Strategy & Filters]]
- [[_COMMUNITY_Regime Meta-Strategy Insight|Regime Meta-Strategy Insight]]
- [[_COMMUNITY_Quant Blend Engine|Quant Blend Engine]]
- [[_COMMUNITY_Mean-Reversion Signals|Mean-Reversion Signals]]
- [[_COMMUNITY_Trend Meter Strategy|Trend Meter Strategy]]
- [[_COMMUNITY_Breakout & EMA Indicators|Breakout & EMA Indicators]]
- [[_COMMUNITY_SOL Market|SOL Market]]
- [[_COMMUNITY_BTC Market|BTC Market]]
- [[_COMMUNITY_ETH Market|ETH Market]]
- [[_COMMUNITY_XAU Market|XAU Market]]

## God Nodes (most connected - your core abstractions)
1. `Quant Blend V1 (QB) Strategy` - 11 edges
2. `Donchian Breakout V1 Strategy` - 10 edges
3. `Quant Trading Bot Project (CLAUDE.md)` - 8 edges
4. `Quant Vault Index (Map of Content)` - 8 edges
5. `Donchian Breakout V1 Strategy` - 8 edges
6. `Strategy Sweep 4H 2023-2026` - 7 edges
7. `Trend Meter (TM) Strategy` - 7 edges
8. `Momentum Reversion (MR) Strategy` - 6 edges
9. `Donchian V1 SOL 4H 2023 Backtest Report` - 4 edges
10. `Market-Aware Meta-Strategy (route by regime/asset)` - 3 edges

## Surprising Connections (you probably didn't know these)
- `Donchian V1 SOL 4H 2023 Backtest Report` --references--> `Quant Blend V1 (QB) Strategy`  [INFERRED]
  backtest_results/DONCHIAN_V1_SOL4H_2023.md → strategies/quant-blend/quant-blend.md
- `Donchian Breakout V1 Strategy` --references--> `Quant Trading Bot Project (CLAUDE.md)`  [EXTRACTED]
  strategies/donchian-breakout/donchian-breakout.md → CLAUDE.md
- `Quant Blend V1 (QB) Strategy` --references--> `Quant Trading Bot Project (CLAUDE.md)`  [EXTRACTED]
  strategies/quant-blend/quant-blend.md → CLAUDE.md
- `Trend Meter (TM) Strategy` --references--> `Quant Trading Bot Project (CLAUDE.md)`  [EXTRACTED]
  strategies/trend-meter/trend-meter.md → CLAUDE.md
- `Trend Meter (TM) Strategy` --references--> `Quant Vault Index (Map of Content)`  [EXTRACTED]
  strategies/trend-meter/trend-meter.md → index.md

## Hyperedges (group relationships)
- **Mean-Reversion Camp (win SOL/XAU)** — quantblend_strategy, momentumreversion_strategy, claude_two_camps [EXTRACTED 1.00]
- **Trend-Following Camp (win BTC/ETH)** — trendmeter_strategy, donchianbreakout_strategy, claude_two_camps [EXTRACTED 1.00]
- **All Markets Tested in Sweep** — claude_market_sol, claude_market_btc, claude_market_eth, claude_market_xau [EXTRACTED 1.00]

## Communities (14 total, 7 thin omitted)

### Community 0 - "Obsidian Plugins Config"
Cohesion: 0.18
Nodes (10): backlink, file-explorer, global-search, graph, markdown-importer, outgoing-link, outline, page-preview (+2 more)

### Community 1 - "Donchian SOL Backtest Metrics"
Cohesion: 0.25
Nodes (9): Backtest Period Jan 1 2023 - Jun 6 2026 (DEEP), SOLUSDT 4H (SOL/TetherUS, Binance), Max Drawdown 10,446.33 USDT (45.35%), Profit Factor 1.095, Profitable Trades 38.16% (29/76), Donchian Breakout V1 SOL 4H Backtest (Strategy Tester), Donchian Breakout V1 Strategy, Total PnL +2,797.96 USDT (+27.98%) (+1 more)

### Community 2 - "Project Docs & Sweep"
Cohesion: 0.70
Nodes (5): Mandatory Pre-Record Backtest Checklist, Quant Trading Bot Project (CLAUDE.md), Quant Vault Index (Map of Content), Momentum Reversion (MR) Strategy, Strategy Sweep 4H 2023-2026

### Community 3 - "Obsidian App Config"
Cohesion: 0.50
Nodes (3): alwaysUpdateLinks, attachmentFolderPath, newLinkFormat

### Community 4 - "Donchian Strategy & Filters"
Cohesion: 0.50
Nodes (4): ADX Filter, ATR Stop / Expansion Filter, Donchian Breakout V1 Strategy, Donchian V1 SOL 4H 2023 Backtest Report

### Community 5 - "Regime Meta-Strategy Insight"
Cohesion: 0.67
Nodes (3): Two Camps / Opposite Markets Insight, Market-Aware Meta-Strategy (route by regime/asset), ADX Regime Switch (trending vs ranging)

### Community 6 - "Quant Blend Engine"
Cohesion: 0.67
Nodes (3): RSI Momentum, Quant Blend V1 (QB) Strategy, Supertrend

## Knowledge Gaps
- **19 isolated node(s):** `alwaysUpdateLinks`, `newLinkFormat`, `attachmentFolderPath`, `file-explorer`, `global-search` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Quant Blend V1 (QB) Strategy` connect `Quant Blend Engine` to `Project Docs & Sweep`, `Donchian Strategy & Filters`, `Regime Meta-Strategy Insight`, `Mean-Reversion Signals`, `Trend Meter Strategy`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Why does `Donchian Breakout V1 Strategy` connect `Donchian Strategy & Filters` to `Trend Meter Strategy`, `Breakout & EMA Indicators`, `Project Docs & Sweep`, `Quant Blend Engine`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Why does `Quant Trading Bot Project (CLAUDE.md)` connect `Project Docs & Sweep` to `Trend Meter Strategy`, `Donchian Strategy & Filters`, `Regime Meta-Strategy Insight`, `Quant Blend Engine`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Quant Blend V1 (QB) Strategy` (e.g. with `Momentum Reversion (MR) Strategy` and `Donchian V1 SOL 4H 2023 Backtest Report`) actually correct?**
  _`Quant Blend V1 (QB) Strategy` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Donchian Breakout V1 Strategy` (e.g. with `Donchian V1 SOL 4H 2023 Backtest Report` and `Trend Meter (TM) Strategy`) actually correct?**
  _`Donchian Breakout V1 Strategy` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `alwaysUpdateLinks`, `newLinkFormat`, `attachmentFolderPath` to the rest of the system?**
  _29 weakly-connected nodes found - possible documentation gaps or missing edges._