"""
flipgate_test.py — swing-size-GATED flip machine: the declared PM-QUANT D2 reopen trigger.

D2 (2026-08-01) found turning points DETECTABLE (near-low z up to 50.7 on 15m/1h) but the
flip overlay lost to costs: swings between turns were smaller than the round-trip cost.
Its banked reopen triggers: (a) near-zero-cost venue, (b) bigger-swing regime filter,
(c) options/GEX. This is (b), the cheapest — SAME detector, SAME flip logic, ONE gate:

    active[t] = vol_short[t] >= q * rolling-median(vol_short over the trailing year)

i.e. only run the flip machine when the market's realized swing size (short-window vol)
sits in the upper half of its own trailing distribution — flat when swings are small.
q = 1.0 (median = the sign boundary, not fitted). Costs, folds, model, labels: verbatim
extrema.track_d2_kill via its helpers. Kill line = D2's: near-low z >= META_Z AND gated-flip
bootstrap Sharpe CI lower > 0 AND gated-flip Sharpe > buy-and-hold. ALSO reported: the
UNGATED flip on the same bars (the D2 number, for the paired read) and the share of bars
active. n_trials = 2 series (BTC 1h, BTC 4h) x 1 gate = 2, all shown.

Usage: python backtest/flipgate_test.py
Output: backtest_results/FLIPGATE_<date>.md
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
GATE_Q = 1.0                 # median of trailing-year short-vol = the sign boundary
VOL_SHORT_BARS = 20          # = extrema's vol20 window (structural, shared)
SERIES = (("BTCUSDT_1h", "1h"), ("BTCUSDT_4h", "4h"))


def load_close(name):
    p = HERE / "data" / f"{name}.csv"
    df = pd.read_csv(p)
    df["dt"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.set_index("dt")["close"].astype(float)


def oos_probs(px):
    """D2's walk-forward near-low/near-high probabilities (verbatim protocol)."""
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
    vol_s = ret.rolling(VOL_SHORT_BARS).std()
    year_bars = int(round(bpy))
    gate = (vol_s >= GATE_Q * vol_s.rolling(year_bars, min_periods=year_bars // 4).median())
    gate = gate.fillna(False)
    pos = flip_positions(p_low.fillna(0.0), p_high.fillna(0.0))
    if gated:
        pos = pos.where(gate, 0.0)          # flat when swings are small (decided at t)
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
    p = RESULTS / f"FLIPGATE_{today}.md"
    L = [f"# Swing-gated flip machine (D2 reopen trigger b) — {today}", "",
         f"Gate: short-vol(20 bars) >= {GATE_Q}× its trailing-year median (sign boundary, not fitted). "
         "Detector/labels/folds/costs = extrema.track_d2_kill verbatim. Kill line = D2's 3 legs. "
         "n_trials = 2 series × 1 gate; ungated rows = the D2 baseline for the paired read.", "",
         "| series | gated | OOS bars | near-low z | flip Sharpe | CI lo | hold Sharpe | active | flips/yr | worst-DD p95 | PASS |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['series']} | {'YES' if r['gated'] else 'no'} | {r['n_oos']} | {r['z']:.1f} | "
                 f"{r['sharpe']:.2f} | {r['sharpe_lo']:.2f} | {r['hold']:.2f} | {r['active']:.0%} | "
                 f"{r['flips_py']:.0f} | {r['maxdd_p95']:.1%} | {'✅' if r['passes'] else '❌'} |")
    n_pass = sum(1 for r in rows if r["gated"] and r["passes"])
    L += ["", f"## VERDICT: {n_pass}/2 gated rows pass",
          "", "Read: if the gate lifts flip Sharpe above hold with CI lo > 0, swing-size WAS the "
          "missing condition and this becomes a prereg candidate. If gating just reduces exposure "
          "and Sharpe stays ≤ hold, the turning-point machine remains detectable-not-monetizable "
          "at these costs; remaining doors = zero-cost venue, GEX."]
    p.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote -> {p}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
