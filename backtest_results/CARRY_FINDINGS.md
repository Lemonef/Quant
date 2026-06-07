# Carry (basis trade) — findings + the exact data gap

Built carry properly with FREE data: spot + perp + funding from Binance. Long spot / short perp,
ON when funding positive, daily PnL = funding + (spot_ret − perp_ret), realistic flip costs.
`backtest/carry_v2.py`.

## Results (daily, 25 coins, 2021-2026)
| | FULL CAGR | DD | Sharpe | 2022 bear | OOS Sharpe | corr to trend |
|---|---|---|---|---|---|---|
| carry v2 (basis-risk) | 11.9% | 1.5% | 5.95 | +0.83 | 3.47 | **0.07** |
| trend core | 26.0% | 18.2% | 1.34 | −0.89 | 0.91 | — |

## Why the Sharpe is still misleadingly high (the key insight)
Binance perps track spot **very tightly** (arbitrage keeps basis ~0.01-0.1%), so carry genuinely is
smooth ~99% of the time → measured vol only 1.9%/yr → Sharpe ~6. **But the real risk is the rare
liquidation blowup**: the short-perp leg gets squeezed in a sharp pump, forced to deleverage at the
worst price. That risk is:
- **intrabar + margin-mechanics** → invisible in daily-close OHLC,
- a **fat left tail** → Sharpe and max-DD (which assume ~normal returns) literally don't capture it.

Carry is a **short-volatility trade**: steady pennies, rare steamroller. Sharpe-6 is true in calm
periods and a lie about the tail.

## The exact missing data (answers "what am I missing")
To model carry's true risk and size it responsibly, need:
1. **Liquidation data + a margin engine** — CoinGlass ~$29/mo, or model conservatively with margin
   assumptions + intraday extremes. ← the one concrete blocker.
2. Funding-spike / negative-funding regime handling (partly done: ON only when funding>0).
3. Two-leg execution/slippage + exchange/counterparty/depeg risk.

## Honest verdict
- Carry is **real and beautifully uncorrelated to trend (0.07), positive in the 2022 bear** — the
  best diversifier candidate found all project.
- **But its Sharpe-6 ignores liquidation tail risk** — I will NOT deploy or size it on that number.
- Realistic carry (after tail haircut) is probably Sharpe ~1-2 — still a great complement to trend,
  but proving that needs liquidation data + a margin model (a real build, ~$29/mo + work).

## So, the genuinely better strategy = trend + risk-modeled carry
Direction confirmed and quantified. The blocker is now specific and cheap ($29/mo liquidation data),
not vague. Until then, the deployable system remains the **trend basket** (OOS Sharpe 0.91).
