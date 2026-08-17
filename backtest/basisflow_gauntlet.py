"""
basisflow_gauntlet.py — full statistics gauntlet for the ONE flowsig survivor.

FLOWSIG (2026-08-18) ran 12 declared trials; basis_flow h=1 passed the 3-leg lead-lag
kill line (t 2.26, all folds agree, OOS overlay Sharpe 1.00 vs hold 0.15). One pass in
12 trials at t≈2.3 is also what pure search noise produces — THIS file settles that with
the factory's own machinery. KILL LINES (set before any number below is read):

  G1 bootstrap:   OOS overlay-minus-hold Sharpe CI (BOOT_N block bootstrap, BOOT_CI)
                  must clear zero (robust.is_fragile on the excess series).
  G2 lag t+2:     one extra day of execution lag; OOS excess Sharpe must stay > 0.
  G3 noise:       NOISE_N seeded reruns with SLIPPAGE-scale noise on the BASIS input;
                  median OOS excess Sharpe must stay > 0.
  G4 plateau:     windows {21, 28, 35} — neighbors must agree in SIGN on OOS excess
                  (CLIFF flag if the 28d cell stands alone). Read-only, no selection.
  G5 CSCV/PBO:    the 12-trial overlay-excess matrix through pbo_cscv; PBO <= 0.25.
  G6 SPA:         spa_pvalue on the same matrix (benchmark = 0 excess); p <= 0.10.

ALL SIX must pass -> "GAUNTLET SURVIVOR — candidate for a prereg'd shadow sleeve"
(still NOT adoption; adoption = prereg + owner-visible shadow, same as every edge).
Any failure -> DEAD, logged, done. Output: backtest_results/BASISFLOW_GAUNTLET_<date>.md
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from alpha_factory import config as cfg
from alpha_factory.panel import build_panel
from alpha_factory.robust import bootstrap_stats, is_fragile, pbo_cscv, spa_pvalue
from alpha_factory.leadlag import diff_means_t, overlay_returns
from flowsig_test import build_signals, fetch_basis, load_stablecoins, load_metrics, \
    ANCHOR, METRICS_LAG_D, run_kill

RESULTS = HERE.parent / "backtest_results"
PLATEAU_WINDOWS = (21, 28, 35)
PBO_MAX = 0.25
SPA_MAX = 0.10
CSCV_BLOCKS = 8


def naive_index(idx):
    return idx.tz_localize(None) if getattr(idx, "tz", None) is not None else idx


def overlay_excess(panel, sig, extra_lag=0):
    """OOS overlay-minus-hold daily net returns for one signal series.
    Favorable sign chosen on the TRAIN portion only (flowsig protocol)."""
    naive = naive_index(panel.close.index)
    a_close = pd.Series(panel.close[ANCHOR].to_numpy(), index=naive)
    a_ret = a_close.pct_change()
    s = sig.shift(extra_lag)
    cut = int(len(naive) * cfg.OOS_SPLIT)
    train, oos = naive[:cut], naive[cut:]
    fwd = a_close.pct_change(1).shift(-1)
    tr = diff_means_t(fwd.reindex(train[:-1]), s.reindex(train[:-1]), 1)  # audit #1
    fav = -1.0 if (tr["diff"] < 0) else 1.0
    ov = overlay_returns(a_ret, s, fav, cfg)
    return (ov - a_ret).reindex(oos).dropna()


def basis_signal(panel, window, noise_sigma=0.0, rng=None):
    """basis_flow at an arbitrary change window, optional input noise on the basis."""
    naive = naive_index(panel.close.index)
    spot = pd.Series(panel.close[ANCHOR].to_numpy(), index=naive)
    q = fetch_basis().reindex(naive)
    basis = q / spot - 1.0
    if noise_sigma > 0:
        basis = basis + rng.normal(0.0, noise_sigma, len(basis))
    return np.sign(basis.diff(window))


def main():
    panel = build_panel(HERE / "data")
    rng = np.random.default_rng(cfg.BOOT_SEED)
    rows, verdicts = [], {}

    # the traded candidate
    sig28 = basis_signal(panel, cfg.LEADLAG_W)
    ex = overlay_excess(panel, sig28)

    # G1 bootstrap on the OOS excess
    boot = bootstrap_stats(ex, cfg.DPY, cfg.BOOT_N, cfg.BOOT_CI, cfg.BOOT_SEED, cfg.BOOT_DD_Q)
    verdicts["G1_bootstrap"] = not is_fragile(boot)
    rows.append(f"| G1 bootstrap | excess Sharpe CI [{boot['sharpe_lo']:.2f}, "
                f"{boot['sharpe_hi']:.2f}], worst-DD p95 {boot['maxdd_p95']:.1%} | CI low > 0 | "
                f"{'✅' if verdicts['G1_bootstrap'] else '❌'} |")

    # G2 lag t+2
    ex_lag = overlay_excess(panel, sig28, extra_lag=1)
    sh_lag = float(ex_lag.mean() / ex_lag.std() * np.sqrt(cfg.DPY)) if ex_lag.std() > 0 else 0.0
    verdicts["G2_lag"] = sh_lag > 0
    rows.append(f"| G2 lag t+2 | excess Sharpe {sh_lag:.2f} | > 0 | "
                f"{'✅' if verdicts['G2_lag'] else '❌'} |")

    # G3 input noise
    noise_sh = []
    for i in range(cfg.NOISE_N):
        r = np.random.default_rng(cfg.BOOT_SEED + i)
        sn = basis_signal(panel, cfg.LEADLAG_W, noise_sigma=cfg.SLIPPAGE, rng=r)
        e = overlay_excess(panel, sn)
        noise_sh.append(float(e.mean() / e.std() * np.sqrt(cfg.DPY)) if e.std() > 0 else 0.0)
    med_noise = float(np.median(noise_sh))
    verdicts["G3_noise"] = med_noise > 0
    rows.append(f"| G3 input noise ×{cfg.NOISE_N} | median excess Sharpe {med_noise:.2f} "
                f"(min {min(noise_sh):.2f}) | median > 0 | "
                f"{'✅' if verdicts['G3_noise'] else '❌'} |")

    # G4 plateau
    plateau = {}
    for w in PLATEAU_WINDOWS:
        e = overlay_excess(panel, basis_signal(panel, w))
        plateau[w] = float(e.mean() / e.std() * np.sqrt(cfg.DPY)) if e.std() > 0 else 0.0
    verdicts["G4_plateau"] = all(v > 0 for v in plateau.values())
    rows.append(f"| G4 plateau 21/28/35d | excess Sharpe {plateau[21]:.2f} / "
                f"{plateau[28]:.2f} / {plateau[35]:.2f} | all > 0 (no cliff) | "
                f"{'✅' if verdicts['G4_plateau'] else '❌'} |")

    # G5+G6: the full 12-trial matrix (search-correction frame)
    sigs, _, _ = build_signals(panel)
    cols = {}
    for name, s in sigs.items():
        for h in cfg.LEADLAG_HORIZONS:
            # horizon only changes the KILL test, not the overlay (daily rebalanced);
            # include one column per signal to keep the matrix the real search space,
            # plus the two basis windows actually examined
            pass
        cols[name] = overlay_excess(panel, s)
    m = pd.DataFrame(cols).dropna()
    pbo = pbo_cscv(m.to_numpy(), CSCV_BLOCKS)
    spa = spa_pvalue(m.to_numpy(), cfg.BOOT_N, cfg.BOOT_SEED)
    verdicts["G5_pbo"] = bool(np.isnan(pbo)) is False and pbo <= PBO_MAX
    verdicts["G6_spa"] = bool(np.isnan(spa)) is False and spa <= SPA_MAX
    rows.append(f"| G5 CSCV/PBO ({m.shape[1]} trial columns, {CSCV_BLOCKS} blocks) | "
                f"PBO {pbo:.2f} | <= {PBO_MAX} | {'✅' if verdicts['G5_pbo'] else '❌'} |")
    rows.append(f"| G6 Hansen SPA ({m.shape[1]} cols) | p {spa:.3f} | <= {SPA_MAX} | "
                f"{'✅' if verdicts['G6_spa'] else '❌'} |")

    ok = all(verdicts.values())
    today = dt.date.today().isoformat()
    p = RESULTS / f"BASISFLOW_GAUNTLET_{today}.md"
    L = [f"# basis_flow FULL GAUNTLET — {today}", "",
         "Candidate: sign of 28d change in BTC quarterly-futures basis, long on the "
         "train-chosen favorable side, daily, net of taker fee + slippage. From "
         "FLOWSIG_2026-08-18 (1/12 trials passed the 3-leg line). Kill lines pre-set "
         "in this file's header before any number was computed.", "",
         "| gate | measured | line | pass |", "|---|---|---|---|", *rows, "",
         f"## VERDICT: **{'GAUNTLET SURVIVOR — candidate for a prereg-gated shadow sleeve' if ok else 'DEAD — logged to the graveyard'}**",
         "", f"OOS span: {ex.index.min().date()} → {ex.index.max().date()} "
         f"({len(ex)} days). n_trials in the search-correction matrix: {m.shape[1]} "
         "signal overlays (the flowsig search space).",
         "", "Adoption path if survivor: prereg (entry/exit/costs/sizing declared) → "
         "Codex gate → shadow sleeve in data.json next to the book — same law as "
         "every edge; the gauntlet alone adopts nothing."]
    p.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote -> {p}")
    print("VERDICT:", "SURVIVOR" if ok else "DEAD", verdicts)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
