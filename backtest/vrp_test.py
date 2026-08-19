"""
vrp_test.py — D3 of the OPTIONS-INSIGHT-LEDGER: variance-risk-premium as an exposure timer.

INSIGHT (B1): implied vol > realized vol on average — the gap is the price the crowd pays for
fear. When VRP is HIGH the crowd is overpaying for protection (fear priced in → forward
returns tend positive); when VRP collapses or goes negative the crowd is complacent /
caught (forward returns tend poor). Nothing here is a turning-point call — it is a
"how much to lean in" dial for exposure, the same mechanism VRP-harvest funds sell.

SIGNAL (declared, one convention): vrp[t] = DVOL[t]/100 − RV20[t]·√365, both known at close
t (DVOL is Deribit's EOD index; RV from closes ≤ t). Signal = sign(vrp − trailing-1y
median of vrp) — "fear above its own norm" vs below. Sign boundary, not fitted.
Traded: the anchor (BTC) — leadlag 3-leg kill line VERBATIM at h=1,5 (favorable side chosen
on train only, boundary-leak fix applied), then, if it passes, the full basisflow-style
gauntlet is the next step. n_trials = 1 signal × 2 horizons.

Also reported (context only): the ungated VRP mean and its OOS percentiles, DVOL-history
span, and the correlation of vrp with the composite regime (over_ma200) so a pass can't be
"just the trend filter in disguise" (that redundancy killed the stablecoin idea before).

Usage: python backtest/vrp_test.py  → backtest_results/VRP_<date>.md
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from alpha_factory import config as cfg
from alpha_factory.panel import build_panel
from alpha_factory.volmodel import fetch_dvol_daily
from flowsig_test import run_kill, ANCHOR

RESULTS = HERE.parent / "backtest_results"
RV_BARS = 20
NORM_BARS = 365


def main():
    panel = build_panel(HERE / "data")
    idx = panel.close.index
    naive = idx.tz_localize(None) if getattr(idx, "tz", None) is not None else idx
    spot = pd.Series(panel.close[ANCHOR].to_numpy(), index=naive)
    dv = fetch_dvol_daily()
    dv.index = pd.DatetimeIndex(dv.index).tz_localize(None)
    dv = dv.reindex(naive)
    rv = spot.pct_change().rolling(RV_BARS).std() * np.sqrt(cfg.DPY)
    vrp = dv / 100.0 - rv
    norm = vrp.rolling(NORM_BARS, min_periods=NORM_BARS // 2).median()
    sig = np.sign(vrp - norm)
    rows = run_kill(panel, {"vrp_above_norm": sig})

    # redundancy read vs the trend regime
    ma200 = (spot > spot.rolling(200).mean()).astype(float)
    corr = float(pd.concat([sig, ma200], axis=1).dropna().corr().iloc[0, 1])
    cut = int(len(naive) * cfg.OOS_SPLIT)
    v_oos = vrp.iloc[cut:].dropna()

    today = dt.date.today().isoformat()
    p = RESULTS / f"VRP_{today}.md"
    L = [f"# VRP exposure-timer kill test (ledger D3/B1) — {today}", "",
         f"Signal: sign(VRP − trailing-{NORM_BARS}d median), VRP = DVOL/100 − RV{RV_BARS}·√365. "
         f"DVOL span {dv.dropna().index.min().date()} → {dv.dropna().index.max().date()}. "
         "Kill line = leadlag 3 legs verbatim (t ≥ 2, folds agree, train-side overlay beats hold "
         "OOS net of costs). n_trials = 1 signal × 2 horizons.", "",
         "| signal | h | t | diff (pp) | folds agree | OOS overlay SR | hold SR | PASS |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['signal']} | {r['horizon']} | {r['t']:.2f} | {r['diff'] * 100:+.2f} | "
                 f"{'✅' if r['folds_agree'] else '—'} | {r['overlay_sharpe']:.2f} | "
                 f"{r['hold_sharpe']:.2f} | {'✅' if r['passes'] else '❌'} |")
    n_pass = sum(1 for r in rows if r["passes"])
    L += ["", f"## VERDICT: {n_pass}/2 pass",
          "", "## Context (not gates)",
          f"- OOS VRP: mean {v_oos.mean():+.3f}, p10 {v_oos.quantile(.1):+.3f}, "
          f"p90 {v_oos.quantile(.9):+.3f} (positive = implied > realized, the premium exists)",
          f"- corr(signal, over-MA200 regime) = {corr:+.2f} — |corr| > 0.5 = the signal is mostly "
          "the trend filter in disguise (redundancy flag, the stablecoin lesson)",
          "", "Pass → full gauntlet (bootstrap/lag/noise/plateau/PBO/SPA) before any sleeve talk. "
          "Fail → ledger row, VRP stays a context line."]
    p.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote -> {p}")
    for r in rows:
        print(f"h={r['horizon']}: t {r['t']:.2f} folds {r['folds_agree']} overlay {r['overlay_sharpe']:.2f} "
              f"hold {r['hold_sharpe']:.2f} PASS {r['passes']}")
    print(f"corr vs MA200 regime: {corr:+.2f}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
