# Alpha library — built all 5 properly, measured out-of-sample

Goal: find a *better* strategy by stacking uncorrelated alphas (the real quant secret). Built each
correctly this time, daily, merged 2021-2026, 25 coins. `backtest/alphas.py`.

## Results (OOS = last 40%, ~2024-2026)
| Alpha | FULL Sharpe | OOS Sharpe | OOS DD | Verdict |
|---|---|---|---|---|
| trend (Donchian55/20+MA200) | 1.34 | **0.91** | 18% | ✅ only robust real edge |
| xsmom (long top5/short bot5) | 0.79 | −0.54 | 79% | ❌ decays OOS |
| tsmom (28d sign) | 0.84 | −0.15 | 83% | ❌ decays OOS |
| rsi2dip (Connors RSI2 in uptrend) | 0.34 | 0.13 | 10% | 🟡 weak but positive |
| carry (long spot/short perp, funding>0) | 8.10 | 11.05 | 0.4% | ⚠️ MODEL ARTIFACT — see below |

Correlation to trend: xsmom 0.19, **carry 0.15**, **rsi2dip 0.05**, tsmom 0.50.

## Why carry's Sharpe 11 is fake (important)
My carry model collects funding with essentially **zero modeled risk** (DD 0.4%) — it ignores the
real risks of a spot-perp basis trade: **liquidation of the short leg, basis blowouts, funding-rate
spikes, exchange/counterparty risk, execution slippage on two legs.** Real basis-trade Sharpe is
more like 1-2, not 11. The inverse-vol ensemble then over-weighted carry to 93% and produced an
absurd "Kelly 242×" — a classic tiny-variance artifact. **Rejected as-is.**

## Honest conclusion
- **Trend remains the only alpha that survives realistic modeling out-of-sample** (Sharpe 0.91).
- Momentum sleeves overfit the 2021 bull and go negative OOS.
- **Carry is the genuine opportunity:** it's a real desk edge AND uncorrelated to trend (0.15). Even
  haircut to a realistic Sharpe ~1.5, blending it with trend would lift combined Sharpe (uncorrelated
  edges stack). But it must be modeled with **basis + liquidation + funding-spike risk** — which needs
  orderbook/liquidation data and careful work (a multi-week project, not a session).

## So: is there a better strategy than the trend basket right now?
**No — not one I can honestly validate in a session.** The better strategy is *trend basket + a
properly-risk-modeled carry sleeve*, and carry is the concrete next build. Everything else either
overfits (momentum) or is too idealized to trust (naive carry). The path is real; the work is real.
