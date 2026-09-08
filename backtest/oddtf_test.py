"""ODD-vs-ROUND timeframe sweep for the turning-point flip machine.

Resamples the same hourly closes to each requested UTC-aligned bar width.  Fits
remain walk-forward and per asset; only the near-low detection statistic pools
assets.  Usage: python backtest/oddtf_test.py
"""
import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from alpha_factory import config as cfg
from alpha_factory.extrema import (zigzag_extrema, near_labels, _series_features,
                                   flip_positions, bars_per_year)
from alpha_factory.robust import bootstrap_stats

RESULTS = HERE.parent / "backtest_results"
ASSETS = ("ADAUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
          "ETHUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT", "XRPUSDT")
TIMEFRAMES = ((24, "round"), (48, "round"), (72, "round"),
              (23, "odd"), (36, "odd"), (46, "odd"), (60, "odd"))
FEATURE_WARMUP = 200


def load_close(name, hours):
    """UTC bins; last observed hourly close only, with no fabricated gap bars."""
    df = pd.read_csv(HERE / "data" / f"{name}_1h.csv")
    df["dt"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    close = df.set_index("dt")["close"].astype(float).sort_index()
    return close.resample(f"{hours}h").last().dropna()


def feature_matrix(px):
    """Keep every structural lookback unavailable until its full warm-up elapsed."""
    X = _series_features(px)
    # Boolean comparisons otherwise coerce the MA-200's initial NaNs to False.
    X.iloc[:FEATURE_WARMUP] = np.nan
    return X


def oos_probs(px):
    """D2's walk-forward protocol, verbatim, PER ASSET."""
    ext = zigzag_extrema(px, cfg.EXTREMA_K)
    X = feature_matrix(px)
    y_low = near_labels(px.index, ext, "low", cfg.EXTREMA_Z)
    y_high = near_labels(px.index, ext, "high", cfg.EXTREMA_Z)
    folds = np.array_split(np.arange(len(px)), cfg.N_FOLDS)
    p_low = pd.Series(np.nan, index=px.index)
    p_high = pd.Series(np.nan, index=px.index)
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


def viability(hours):
    """Check the unmodified walk-forward protocol before fitting either arm."""
    checks = []
    for name in ASSETS:
        px = load_close(name, hours)
        X = feature_matrix(px)
        ext = zigzag_extrema(px, cfg.EXTREMA_K)
        valid_train = []
        for i in range(1, cfg.N_FOLDS):
            folds = np.array_split(np.arange(len(px)), cfg.N_FOLDS)
            cutoff = px.index[folds[i][0]]
            tr = (px.index < cutoff) & X.notna().all(axis=1).to_numpy()
            near_unconf = pd.Series(False, index=px.index)
            for d, row in ext.iterrows():
                if row.confirmed >= cutoff:
                    j = px.index.get_loc(d)
                    near_unconf.iloc[max(0, j - cfg.EXTREMA_Z):j + cfg.EXTREMA_Z + 1] = True
            valid_train.append(int((tr & ~near_unconf.to_numpy()).sum()))
        checks.append((name, len(px), max(valid_train, default=0)))
    failed = [x for x in checks if x[2] < cfg.ML_MIN_TRAIN_DAYS]
    # The predetermined pooled test is viable only if every asset has an OOS fold.
    if failed:
        bars = min(x[1] for x in checks)
        best = min(x[2] for x in failed)
        return False, bars, (f"{bars} bars; no fold has {cfg.ML_MIN_TRAIN_DAYS} valid "
                             f"training bars (best {best}) after the 200-bar feature warm-up")
    return True, min(x[1] for x in checks), ""


def run_arm(hours, group, long_only):
    pooled_y, pooled_bet = [], []
    flip_legs, hold_legs, flips_py = {}, {}, []
    for name in ASSETS:
        px = load_close(name, hours)
        p_low, p_high, y_low = oos_probs(px)
        oos = p_low.notna()
        if not oos.any():
            raise RuntimeError(f"{hours}h {name}: no OOS predictions")
        bpy = bars_per_year(px.index)
        ret = px.pct_change().fillna(0.0)
        pos = flip_positions(p_low.fillna(0.0), p_high.fillna(0.0))
        if long_only:
            pos = pos.clip(lower=0.0)
        flips = pos.diff().abs().fillna(0.0)
        fr = (pos.shift(1).fillna(0.0) * ret
              - flips.shift(1).fillna(0.0) * (cfg.TAKER_FEE + cfg.SLIPPAGE))[oos]
        hold = ret[oos]
        bet = oos & (p_low > 0.5)
        pooled_y.append(y_low[bet].to_numpy())
        pooled_bet.append(y_low[oos].to_numpy())
        flip_legs[name], hold_legs[name] = fr, hold
        flips_py.append(float(flips[oos].sum() / 2 / (oos.sum() / bpy)))

    hits, allb = np.concatenate(pooled_y), np.concatenate(pooled_bet)
    base, prec, n_bet = float(allb.mean()), float(hits.mean()), len(hits)
    z = ((prec - base) / np.sqrt(base * (1 - base) / n_bet)
         if 0 < base < 1 and n_bet else float("nan"))
    port_flip = pd.DataFrame(flip_legs).dropna(how="all").mean(axis=1).dropna()
    port_hold = pd.DataFrame(hold_legs).dropna(how="all").mean(axis=1).dropna()
    bpy = bars_per_year(port_flip.index)
    sh = lambda s: float(s.mean() / s.std() * np.sqrt(bpy)) if s.std() > 0 else 0.0
    boot = bootstrap_stats(port_flip, bpy, cfg.BOOT_N, cfg.BOOT_CI,
                           cfg.BOOT_SEED, cfg.BOOT_DD_Q)
    passes = bool(np.isfinite(z) and z >= cfg.META_Z and boot["sharpe_lo"] > 0
                  and sh(port_flip) > sh(port_hold))
    arm = "long-only" if long_only else "symmetric"
    out = dict(hours=hours, group=group, arm=arm, z=z, flip=sh(port_flip),
               lo=boot["sharpe_lo"], hold=sh(port_hold),
               flips_py=float(np.mean(flips_py)), passes=passes,
               base=base, prec=prec, n_bet=n_bet, bpy=bpy)
    if not all(np.isfinite(out[k]) for k in ("z", "flip", "lo", "hold", "flips_py")):
        raise RuntimeError(f"{hours}h {arm}: non-finite result")
    print(f"{hours:>2}h {group:>5} {arm:>9}: z={z:+.2f}, flip={out['flip']:+.2f}, "
          f"CI={out['lo']:+.2f}, hold={out['hold']:+.2f}, flips/yr={out['flips_py']:.1f}",
          flush=True)
    return out


def group_read(rows, arm):
    r = [x for x in rows if x["arm"] == arm and x["group"] == "round"]
    o = [x for x in rows if x["arm"] == arm and x["group"] == "odd"]
    if not r or not o:
        return (f"{arm}: comparison unavailable: ROUND n={len(r)}, ODD n={len(o)} "
                "among viable timeframes.")
    def mean(key, xs): return float(np.mean([x[key] for x in xs]))
    return (f"{arm}: ROUND mean z {mean('z', r):+.2f}, flip Sharpe {mean('flip', r):+.2f}; "
            f"ODD mean z {mean('z', o):+.2f}, flip Sharpe {mean('flip', o):+.2f}.")


def main():
    rows, skipped = [], []
    for hours, group in TIMEFRAMES:
        ok, bars, reason = viability(hours)
        if not ok:
            skipped.append(dict(hours=hours, group=group, bars=bars, reason=reason))
            print(f"{hours:>2}h {group:>5}: SKIPPED — {reason}", flush=True)
            continue
        for long_only in (False, True):
            rows.append(run_arm(hours, group, long_only))
    today = dt.date.today().isoformat()
    p = RESULTS / f"ODDTF_{today}.md"
    L = [f"# ODD-vs-ROUND turning-point flip sweep — {today}", "",
         "Hourly closes were resampled in UTC with pandas `last().dropna()`. The detector, "
         "walk-forward fitting, costs, pooling rule, and equal-weight portfolios are otherwise "
         "the DAILYPOOL procedure. Training remains per asset. Annualization is self-measured "
         "from each resampled portfolio index.", "",
         "| timeframe | hours | round/odd | arm | pooled z | flip Sharpe | CI lo | hold Sharpe | flips/yr | PASS |",
         "|---|---:|---|---|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        L.append(f"| {r['hours']}h | {r['hours']} | {r['group']} | {r['arm']} | "
                 f"{r['z']:.2f} | {r['flip']:+.2f} | {r['lo']:+.2f} | "
                 f"{r['hold']:+.2f} | {r['flips_py']:.1f} | {'YES' if r['passes'] else 'NO'} |")
    for s in skipped:
        L.append(f"| {s['hours']}h | {s['hours']} | {s['group']} | SKIPPED | — | — | — | — | — | {s['reason']} |")
    L += ["", "## Round versus odd", "", group_read(rows, "symmetric"), "",
          group_read(rows, "long-only"), "",
          "The comparison uses only the timeframes that survived the unchanged methodology. "
          "It is descriptive, not independent evidence; if either group is small or unbalanced, "
          "no round-versus-odd claim is supported.", "",
          "## Data ceiling", "",
          f"The unchanged protocol has a 200-bar feature warm-up and requires at least "
          f"{cfg.ML_MIN_TRAIN_DAYS} valid training bars. With four walk-forward folds, the "
          "latest available training cutoff is three-quarters through the sample, so at least "
          f"{math.ceil((FEATURE_WARMUP + cfg.ML_MIN_TRAIN_DAYS) * cfg.N_FOLDS / (cfg.N_FOLDS - 1))} "
          "resampled bars are needed even before the "
          "confirmation purge. The timeframes marked SKIPPED therefore could not be tested "
          "with available history. This caps how far the higher-timeframe idea can be pushed.", "",
          "## 24h sanity check", "",
          "The 24h UTC-resampled row is compared below in the run report to DAILYPOOL_2026-09-09. "
          "It need not match exactly because that file uses native daily bars with different "
          "session boundaries, but it should be in the same neighbourhood."]
    p.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote -> {p}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
