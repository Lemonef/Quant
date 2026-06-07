# Everything tried to get "higher" — and the honest outcome

Goal: beat the validated core (Donchian55/20 + 200-MA, basket) — OOS Sharpe **0.61**, ~17-25% CAGR,
DD ~20%. Out-of-sample (2024-26) is the judge; full-period is inflated by the 2021/2023 bulls.

## Techniques tested (daily, merged 2021-2026, basket)
| Technique | FULL Sharpe | 2022 BEAR | **OOS Sharpe** | Verdict |
|---|---|---|---|---|
| **Trend (Donchian+MA)** — the core | 1.20 | −1.02 | **0.61** | ✅ best OOS |
| Mean-reversion | −0.39 | −1.21 | −0.29 | ❌ |
| Time-series momentum (TSMOM) | 0.80 | −0.90 | 0.05 | ❌ OOS decays, DD 79% |
| Long/Short neutral (no costs) | 1.34 | +1.32 | 0.65 | ⚠️ great but unrealistic |
| Long/Short neutral (real short costs) | 0.91 | +0.80 | 0.05 | ⚠️ bear hedge only |
| Ensemble trend+MR+TSMOM | 0.66 | −1.50 | 0.09 | ❌ worse than core |
| Ensemble trend+LS | 1.05 | +0.12 | 0.19 | ❌ worse OOS than core |
| trend85/LS15 + vol-target | 1.17 | −0.14 | 0.30 | ❌ worse OOS, DD 49% |

## The lesson (textbook quant)
- **Added complexity raised full-period numbers but LOWERED out-of-sample Sharpe every time.** That
  is overfitting — the exact trap the methodology research warned about. Simpler won.
- **Long/Short is the only genuinely uncorrelated idea** (positive in the 2022 bear, +0.80 even
  after costs) — valuable as a *crash hedge*, not a CAGR booster. After realistic short funding/
  borrow it doesn't beat the core out-of-sample.
- Constant-vol targeting inflated drawdowns (50-60%) — removed.

## So how do you actually get "higher"? Only honest answers:
1. **Leverage the core.** OOS Sharpe is fixed (~0.6); CAGR scales with leverage and so does DD:
   1x ≈ 17% CAGR / 20% DD · 2x ≈ 25% / 43% · 3x ≈ 31% / 60%. No free lunch.
2. **Expand the universe** (more coins = more independent trend bets = genuinely higher Sharpe, NOT
   overfitting). The one clean lever left to test (10 → 25-30 liquid coins).
3. **Accept the ceiling.** Robust crypto systematic = Sharpe ~0.6-1.0. 70-80% CAGR at low DD does
   not exist here; it only appears via leverage (high DD) or bugs (the one I killed).

## Recommendation
Run the **core (Donchian55/20 + MA200, basket)** at the leverage matching your DD tolerance, add a
**small Long/Short sleeve as a bear hedge** (optional), and consider **universe expansion** as the
only non-overfit way to lift Sharpe. Validate walk-forward, then paper-trade on the VPS.
