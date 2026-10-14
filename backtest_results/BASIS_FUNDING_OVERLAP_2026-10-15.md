# COIN-M basis vs perp-funding overlap — 2026-10-15

## Preregistered interpretation thresholds

- Correlation > 0.6: **largely the same premium**.
- Correlation < 0.3: **genuinely different**.
- Otherwise: **partially overlapping**.

## Matched construction and coverage

COIN-M is the same FULL DTE5 1x positions selected by `basis_coinm_test.py`: long BTC spot and short the inverse quarterly. Daily USD wealth is marked from the daily closes as `Q * F_entry * S_t / F_t`, less the already-paid entry BTC fees; the DTE5 exit observation uses the source strategy's open exit and exit costs. When dated contracts overlap, their approximately one-BTC-capital daily returns are equal-capital averaged. Funding is the live `paper_bot.py` 1x `fund_block` rule exactly: matched BTC/ETH prints, equal-weight funding, trailing 21-print side signal, 30%/100% hysteretic gate, and 0.30% two-leg costs on side changes and resizes. It is aggregated from 8h returns to UTC daily compounded returns.

- Basis held windows: 10 FULL DTE5 trades; 2023-02-27 to 2026-03-22, 993 marked trading days.
- Matched active days: 993; 2023-02-27 to 2026-03-22. No flat days are inserted between quarterly holds.
- Funding input coverage: 2021-01-01 to 2026-06-06; its matched-day returns are used above.

## Return-stream overlap

- Daily-return correlation: **-0.008**.
- 30-observation rolling-return correlation: **-0.021**.
- Drawdown-depth correlation (each sleeve's cumulative equity drawdown on the matched active-day sequence): **-0.375**.
- Classification from daily correlation: **genuinely different**.

## Risk-adjusted comparison

Sharpe uses the daily matched observations and is annualised at **365** (no cap).

| sleeve | annualised Sharpe (365) |
|---|---:|
| COIN-M basis | 1.976 |
| Perp funding | 8.430 |
| 50/50 daily-return combination | 3.419 |

## Level-versus-funding test

The quarterly basis level is `quarterly_close / BTC spot close - 1`; funding is the trailing 30-day (90-print) mean BTC perp rate, both aligned at daily close. Coverage is 2023-01-01 to 2026-06-06, n=1253. Correlation: **+0.523**.

## Verdict

On matched active days, COIN-M basis and the live funding sleeve are **genuinely different** by the declared daily-return threshold. The level/funding correlation is reported separately as the leverage-demand diagnostic; it is not substituted for return-stream overlap.

---

## Reviewer note (Claude, 2026-10-15) — read before using the verdict above

The automated verdict "genuinely different" rests on daily-return correlation ≈ 0. Treat that with caution:

1. **A near-constant series correlates ≈ 0 with everything.** The funding sleeve accrues almost smoothly, so its daily
   returns have tiny variance; the near-zero correlation is partly a mechanical consequence of that, not evidence of
   independent risk.
2. **The funding Sharpe of 8.43 is the near-zero-volatility artifact** — the same one `live_bot/paper_bot.py` caps at
   ±3 for exactly this reason. The "50/50 = 3.42" combination figure inherits the distortion and should not be quoted.
3. **The informative number is the LEVEL correlation, +0.52.** Quarterly basis and trailing funding are driven by the
   same leverage demand. When that demand collapses (a deleveraging regime), BOTH premia shrink together — so the
   diversification benefit is weaker than the daily correlation suggests, and the drawdown correlation (−0.375) should
   not be read as a hedge.

**Working conclusion:** different *return paths*, largely the same *economic driver*. Coin-M basis carry adds a second
way to harvest the leverage premium with different timing, not an independent source of return. Size them as one risk
bucket, not two.
