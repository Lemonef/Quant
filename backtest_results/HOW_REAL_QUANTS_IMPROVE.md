# How real quant desks get higher — gap analysis for this project

We built ONE alpha (price-based trend) diversified across coins → OOS Sharpe ~0.9. Good retail
systematic. Here's what real funds add, ranked by value+accessibility for a ~$3k automated crypto trader.

## 1. Many uncorrelated alphas, ensembled  ← the actual secret
Top funds don't have one genius strategy. They run **dozens of weak signals** (each Sharpe 0.2-0.5)
that are mutually uncorrelated; combined, the portfolio Sharpe stacks (Sharpe_combined ≈
Sharpe_single × √N_independent). We have 1 alpha. Adding 3-4 *genuinely different* ones (carry,
reversion at another horizon, cross-sectional) is the biggest lever — far more than tuning one.

## 2. Alternative data (price is the crowded signal)
Edge lives off-price: on-chain (exchange in/outflows, active addresses, whale wallets, stablecoin
supply), **funding rates**, social sentiment, dev/GitHub activity, ETF flows. Harder to access but
where uncrowded alpha is.

## 3. Funding-rate carry / basis trade  ← BEST accessible next alpha for us
Long spot + short the perpetual future = harvest **funding** (frequently +10-30%/yr), market-neutral,
low drawdown, **uncorrelated to the trend system**. Binance funding history is free. This is how
crypto quant desks earn steady Sharpe. Add it as a sleeve → combined Sharpe jumps, then leverage.

## 4. Risk & sizing engineering
Volatility targeting (constant risk), fractional-Kelly sizing, correlation-aware weights, regime
models (trade size down in high-vol/bear), explicit drawdown caps.

## 5. Execution
Limit/TWAP/VWAP orders to minimise slippage and market impact; matters increasingly with size.
Retail edge: use maker orders, avoid market orders in thin books.

## 6. Research infrastructure (we do this part)
Point-in-time data (no lookahead), no survivorship bias, realistic costs, walk-forward validation,
paper→live. Plus a *continuous* research pipeline, not one-shot backtests.

## 7. Factor models
Cross-sectional ranking on factors (momentum, carry, value, size, low-vol) — long top decile / short
bottom, dollar-neutral. (We tried a simple long/short; a proper multi-factor version is the pro form.)

## What this means for Zen — the concrete plan
1. **Keep the trend basket** (Donchian55/20 + MA200, ~20 coins) as the directional sleeve (Sharpe ~0.9).
2. **Add funding-rate carry** as a market-neutral sleeve (uncorrelated, steady). ← build next.
3. **Combine** the two → higher Sharpe than either; then choose leverage for target CAGR.
4. Later: add on-chain/sentiment signals; vol-target the whole book; proper execution on the VPS.

> The real lever to "higher" is **more independent edges**, not a cleverer single strategy. Everything
> we tried that was just a fancier price strategy overfit. Carry is a *different kind* of edge — that's
> why it should genuinely help.
