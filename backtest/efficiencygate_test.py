"""
efficiencygate_test.py — trend-PERSISTENCE-gated flip machine: D2 reopen trigger (b),
second attempt with a different mechanism than the already-killed version.

The plain swing-SIZE gate (flipgate_test.py, 2026-08-19) is DEAD: gating on raw
volatility magnitude (short-vol >= trailing-year median) made things WORSE, not
better (flips 67->188/yr, Sharpe -0.84->-1.16 on 1h). Diagnosis: high volatility
is not the same thing as a real trending swing — a choppy/whipsaw regime can have
LARGE volatility with near-zero net directional progress, and that's exactly the
regime the flip machine bleeds hardest in (lots of triggered flips, no follow-through).
Gating on size alone lets more of that regime through, not less.

This gate uses Kaufman's EFFICIENCY RATIO instead: net directional distance over a
trailing window divided by the total path length traveled (sum of absolute bar-to-bar
moves) over the same window:

    ER[t] = |px[t] - px[t-n]| / sum(|px[i] - px[i-1]| for i in t-n+1..t)

ER -> 1 means the window was a straight, efficient trend (every bar moved the position
forward); ER -> 0 means the window round-tripped on itself (chop/whipsaw) regardless of
how large the individual bar-to-bar moves were. This is the "not just size, does it
persist" distinction the size-only gate couldn't make. Owner's own framing (2026-08-31):
"maybe derivative or some weird math thing... it normally dies because of sideways
market, attack that problem" — ER is exactly a directness-of-motion measure, not an
amplitude one.

Q = 0.5 (ER >= 0.5 = more than half the path length was net progress, a genuine
regime split not a fitted number) at ER_WINDOW = 20 bars (same window as extrema's
vol20 / flipgate's VOL_SHORT_BARS, for a fair paired comparison). Detector, labels,
folds, costs = extrema.track_d2_kill verbatim, identical to flipgate_test.py's method.
Kill line = D2's 3 legs (same as flipgate_test.py). ALSO reports the ungated D2 baseline
and flipgate's SIZE-gated result inline for a 3-way paired read on the same bars.

Usage: python backtest/efficiencygate_test.py
Output: backtest_results/EFFICIENCYGATE_<date>.md
"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from alpha_factory import config as cfg
from alpha_factory.extrema import (zigzag_extrema, near_labels, _series_features,
                                   flip_positions, bars_per_year)
from alpha_factory.robust import bootstrap_stats
from sklearn.ensemble import HistGradientBoostingClassifier

RESULTS = HERE.parent / "backtest_results"
ER_Q = 0.5              # efficiency-ratio threshold: net progress >= half the path length
ER_WINDOW = 20           # bars — matches extrema's vol20 / flipgate's VOL_SHORT_BARS
SERIES = (("BTCUSDT_1h", "1h"), ("BTCUSDT_4h", "4h"))


def load_close(name):
    p = HERE / "data" / f"{name}.csv"
    df = pd.read_csv(p)
    df["dt"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.set_index("dt")["close"].astype(float)


def efficiency_ratio(px, window):
    """Kaufman ER: |net move| / sum(|bar-to-bar moves|) over a trailing window.
    1.0 = straight trend, ~0 = round-tripped chop, regardless of move size."""
    net = (px - px.shift(window)).abs()
    path = px.diff().abs().rolling(window).sum()
    return (net / path.replace(0, np.nan)).fillna(0.0)


def oos_probs(px):
    """D2's walk-forward near-low/near-high probabilities (verbatim protocol,
    identical to flipgate_test.py's oos_probs)."""
    ext = zigzag_extrema(px, cfg.EXTREMA_K)
    X = _series_features(px)
    y_low = near_labels(px.index, ext, "low", cfg.EXTREMA_Z)
    y_high = near_labels(px.index, ext, "high", cfg.EXTREMA_Z)
    n = len(px)
    folds = np.array_split(np.arange(n), cfg.N_FOLDS)
    p_low = pd.Series(np.nan, index=px.index); p_high = pd.Series(np.nan, index=px.index)
    for i in range(1, cfg.N_FOLDS):
        cutoff = px.index[folds[i][0]]
        tr = (px.index < cutoff) & X.notna().all(axis=1).to_numpy()
        near_unconf = pd.Series(False, index=px.index)
        for d, row in ext.iterrows():
            if row.confirmed >= cutoff:
                j = px.index.get_loc(d)
                near_unconf.iloc[max(0, j - cfg.EXTREMA_Z):j + cfg.EXTREMA_Z + 1] = True
        tr &= ~near_unconf.to_numpy()
        if tr.sum() < cfg.ML_MIN_TRAIN_DAYS:
            continue
        te = folds[i][X.iloc[folds[i]].notna().all(axis=1).to_numpy()]
        for tgt, sink in ((y_low, p_low), (y_high, p_high)):
            m = HistGradientBoostingClassifier(max_iter=cfg.ML_MAX_ITER,
                                               learning_rate=cfg.ML_LEARNING_RATE,
                                               max_depth=cfg.ML_MAX_DEPTH,
                                               random_state=cfg.BOOT_SEED)
            m.fit(X[tr], tgt[tr])
            if len(te):
                sink.iloc[te] = m.predict_proba(X.iloc[te])[:, 1]
    return p_low, p_high, y_low


def evaluate(px, gated):
    p_low, p_high, y_low = oos_probs(px)
    bpy = bars_per_year(px.index)
    oos = p_low.notna()
    ret = px.pct_change().fillna(0.0)
    er = efficiency_ratio(px, ER_WINDOW)
    gate = (er >= ER_Q).fillna(False)
    pos = flip_positions(p_low.fillna(0.0), p_high.fillna(0.0))
    if gated:
        pos = pos.where(gate, 0.0)          # flat when the recent path is inefficient/choppy
    flips = pos.diff().abs().fillna(0.0)
    fr = (pos.shift(1).fillna(0.0) * ret - flips.shift(1).fillna(0.0) * (cfg.TAKER_FEE + cfg.SLIPPAGE))[oos]
    hold = ret[oos]
    boot = bootstrap_stats(fr, bpy, cfg.BOOT_N, cfg.BOOT_CI, cfg.BOOT_SEED, cfg.BOOT_DD_Q)
    sh = lambda s: float(s.mean() / s.std() * np.sqrt(bpy)) if s.std() > 0 else 0.0
    base = float(y_low[oos].mean()); bet = oos & (p_low > 0.5)
    prec = float(y_low[bet].mean()) if bet.any() else float("nan")
    z = ((prec - base) / np.sqrt(base * (1 - base) / int(bet.sum()))
         if bet.any() and 0 < base < 1 else float("nan"))
    return dict(n_oos=int(oos.sum()), z=float(z), sharpe=sh(fr), sharpe_lo=boot["sharpe_lo"],
                hold=sh(hold), active=float(gate[oos].mean()) if gated else 1.0,
                flips_py=float(flips[oos].sum() / 2 / (oos.sum() / bpy)),
                maxdd_p95=boot["maxdd_p95"],
                passes=bool(np.isfinite(z) and z >= cfg.META_Z and boot["sharpe_lo"] > 0
                            and sh(fr) > sh(hold)))


def main():
    rows = []
    for name, tf in SERIES:
        px = load_close(name)
        for gated in (False, True):
            r = evaluate(px, gated)
            r.update(series=name, tf=tf, gated=gated)
            rows.append(r)
            print(f"{name} gated={gated}: z {r['z']:.1f} · Sharpe {r['sharpe']:.2f} "
                  f"(lo {r['sharpe_lo']:.2f}) vs hold {r['hold']:.2f} · active {r['active']:.0%} "
                  f"· flips/yr {r['flips_py']:.0f} · PASS {r['passes']}", flush=True)
    today = dt.date.today().isoformat()
    p = RESULTS / f"EFFICIENCYGATE_{today}.md"
    L = [f"# Trend-efficiency-gated flip machine (D2 reopen trigger b, 2nd mechanism) — {today}", "",
         f"Gate: Kaufman efficiency ratio(20 bars) >= {ER_Q} (net progress >= half the path "
         "length traveled — chop has large path length but small net progress, so this "
         "differs from a raw volatility-SIZE gate). Detector/labels/folds/costs = "
         "extrema.track_d2_kill verbatim. Kill line = D2's 3 legs. n_trials = 2 series x 1 "
         "gate; ungated rows = the D2 baseline for the paired read.", "",
         "**Context: the plain SIZE gate (flipgate_test.py, 2026-08-19) already failed** — "
         "gating on raw vol magnitude made flips WORSE (67->188/yr, Sharpe -0.84->-1.16 on "
         "1h) because big-but-choppy periods passed the gate too. This test asks a different "
         "question: does gating on DIRECTIONAL PERSISTENCE (not size) behave differently?",
         "",
         "| series | gated | OOS bars | near-low z | flip Sharpe | CI lo | hold Sharpe | active | flips/yr | worst-DD p95 | PASS |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['series']} | {'YES' if r['gated'] else 'no'} | {r['n_oos']} | {r['z']:.1f} | "
                 f"{r['sharpe']:.2f} | {r['sharpe_lo']:.2f} | {r['hold']:.2f} | {r['active']:.0%} | "
                 f"{r['flips_py']:.0f} | {r['maxdd_p95']:.1%} | {'✅' if r['passes'] else '❌'} |")
    n_pass = sum(1 for r in rows if r["gated"] and r["passes"])
    L += ["", f"## VERDICT: {n_pass}/2 gated rows pass",
          "", "Read: if the efficiency gate lifts flip Sharpe above hold with CI lo > 0 AND "
          "reduces (not increases) flip frequency vs the ungated baseline, trend-persistence "
          "(not swing size) was the missing condition. If it also fails, both mechanisms of "
          "the 'bigger-swing regime filter' reopen trigger are exhausted; remaining doors = "
          "zero-cost venue, options/GEX data."]
    p.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote -> {p}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
