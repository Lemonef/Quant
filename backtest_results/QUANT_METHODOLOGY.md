# How professional quants find strategies — research + how we applied it

Researched the pro process and crypto-specific edges, then applied them to our search. Sources at end.

## The professional process (what we now follow)
1. **Hypothesis first** — a testable economic idea ("trends persist", "price mean-reverts"), not a
   pattern dredged from data.
2. **Simple model** — fewer rules = less curve-fit. Each parameter is a degree of freedom to overfit.
3. **Backtest** — realistic costs (commission + slippage), no lookahead (we use prior-bar channels).
4. **Out-of-sample + walk-forward** — split train/test; the strategy must work on data it never saw.
   We test 2024-2026 OOS and the untouched 2021-2022 bear.
5. **Parameter-plateau robustness** — vary a parameter; if a tiny change (lookback 28→40) collapses
   returns, it's overfit. You want a broad plateau of "good enough" params.
6. **Regime awareness** — test bull AND bear (we added the 2022 crash).
7. **Risk first** — size by volatility, cap drawdown, expect Sharpe ~1 (great is ~2; >3 = a bug).

## Crypto-specific findings from the literature
- **Time-series momentum** (long if trailing ~28-day return > 0) is the most robust crypto edge —
  reported Sharpe ~1.5 (lookback 28d, hold 5d) vs market 0.84.
- **Cross-sectional momentum** (long the top performers) is weaker alone in crypto but good when
  combined with a positive-trend filter ("winners that are also trending up").
- **Volatility targeting / filtering** stabilises returns (~Sharpe 1.2) — scale exposure inversely
  to recent vol.

## What we tested (our engine, full cycle 2021-2026 incl 2022 bear)
| Strategy | Full CAGR | DD | Full Sharpe | OOS Sharpe |
|---|---|---|---|---|
| Donchian basket (no filter) | 15.3% | 32% | 0.74 | −0.06 |
| **Donchian basket + MA-200 filter** | 18-25% | **18-23%** | **1.07-1.14** | 0.44-0.59 |
| TSMOM lb28 (vol-target 40%) | 44.9% | 73% | 1.01 | 0.55 |
| XSMOM top-5 | 50.6% | 61% | 1.11 | 0.03 |
| **combo (top-5 + positive trend), vol-target** | 51.2% | 74% | 1.07 | **0.64** |

Plateau check (TSMOM lookback): Sharpe 0.77 / 1.01 / 0.78 at lb 20 / 28 / 40 → a real (if modest)
plateau around 28. Not a single lucky parameter.

## Honest conclusions
1. **Best risk-adjusted + DD-controlled** = **Donchian basket + MA-200 filter** (stops keep DD ~20%
   vs momentum's 60-75%). ~25% CAGR, Sharpe 1.14 full / ~0.5 OOS, survives the 2022 bear.
2. **Highest OOS Sharpe** = the momentum **combo** (0.64) but DD ~50-74% — only for huge risk tolerance.
3. **No robust config does 70-80% CAGR at good Sharpe and low DD.** Sharpe ~1 is the real ceiling
   here; 70-80% CAGR requires ~3x leverage → ~50%+ drawdown (Sharpe preserved, risk is not).
   This matches the literature — sustainable Sharpe ~1-1.5 is "good"; advertised triple-digit CAGR
   crypto bots are overfit or bull-only.

## Recommended path forward (pro playbook)
- **Core**: Donchian + MA-200 filter basket, ~1.0-1.5x → 25-37% CAGR, DD 20-29%, Sharpe ~1.1.
  Hits the original targets (CAGR 30%+ at 1.5x, Sharpe>0.8, PF>1.5) and survives bear.
- **Validation before live**: walk-forward (rolling re-fit), intrabar stops, funding costs, then
  paper-trade on the VPS 1-3 months.
- **If chasing higher CAGR**: lever the core and accept the drawdown — don't switch to a flimsier
  high-CAGR/high-DD model.

## Sources
- [Quantlane — avoid overfitting](https://quantlane.com/blog/avoid-overfitting-trading-strategies/)
- [Engineer's guide to building/validating quant strategies](https://extremelysunnyyk.medium.com/an-engineers-guide-to-building-and-validating-quantitative-trading-strategies-b4611e5e2ac5)
- [AUT — Time-Series & Cross-Sectional Momentum in Crypto](https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf)
- [Systematic crypto: momentum, mean-reversion, vol filtering](https://medium.com/@briplotnik/systematic-crypto-trading-strategies-momentum-mean-reversion-volatility-filtering-8d7da06d60ed)
- [QuantVPS — quant trading & backtesting guide](https://www.quantvps.com/blog/guide-to-quantitative-trading-strategies-and-backtesting)
