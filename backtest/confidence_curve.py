"""
confidence_curve.py — is the turning-point edge CONCENTRATED at high confidence?

WHY (Zen 2026-09-09, pushing back on the "closed" verdict, correctly): every test so far
traded EVERY signal at p_low > 0.5 with a full-size position, and measured profit against a
detector that was never trained to produce profit. Before declaring the idea dead we should
know whether the edge is uniform across confidence or concentrated in the top slice.

Two numbers per threshold:
  precision  — of bars we called "near a low" at this confidence, what share really were
  fwd_ret    — the MEAN FORWARD RETURN after those bars, net of one round-trip cost

The second matters more than the first and has never been measured here. "Near a low" is a
retrospective zigzag label; it is NOT the same claim as "price rises from here". If precision
climbs with confidence but forward return does not, the label is detectable and still not
tradeable, and the idea really is closed. If BOTH climb, there is headroom the flip machine
was throwing away by trading everything at 0.5.

Pooled across the same 10 assets / daily bars as dailypool_test.py, same per-asset
walk-forward fitting (no cross-asset leakage), same costs.

Usage: python backtest/confidence_curve.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from alpha_factory import config as cfg
from dailypool_test import load_close, oos_probs, ASSETS

THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)
FWD_BARS = (5, 10, 20)          # holding horizons to score the signal against
ROUND_TRIP = cfg.TAKER_FEE + cfg.SLIPPAGE


def main():
    rows = []
    for name in ASSETS:
        try:
            px = load_close(name)
        except Exception as e:
            print(f"{name}: SKIP ({e})", flush=True)
            continue
        p_low, _p_high, y_low = oos_probs(px)
        oos = p_low.notna()
        if not oos.any():
            continue
        fwd = {n: (px.shift(-n) / px - 1.0) for n in FWD_BARS}
        for i in np.flatnonzero(oos.to_numpy()):
            rec = {"p": float(p_low.iloc[i]), "y": bool(y_low.iloc[i])}
            for n in FWD_BARS:
                v = fwd[n].iloc[i]
                rec[f"f{n}"] = float(v) if pd.notna(v) else np.nan
            rows.append(rec)
        print(f"{name}: {int(oos.sum())} oos bars", flush=True)

    df = pd.DataFrame(rows)
    base = float(df["y"].mean())
    print(f"\npooled bars={len(df)}  base rate={base:.3f}\n")

    print(f"{'thr':>5} {'n':>7} {'precision':>10} " +
          " ".join(f"{'fwd'+str(n)+'(net)':>14}" for n in FWD_BARS))
    out_lines = [f"pooled bars={len(df)}, base rate={base:.4f}, "
                 f"round-trip cost={ROUND_TRIP:.4%}", "",
                 "| p_low >= | n | precision | lift vs base | " +
                 " | ".join(f"mean fwd{n} net" for n in FWD_BARS) + " |",
                 "|---|---:|---:|---:|" + "---:|" * len(FWD_BARS)]
    for thr in THRESHOLDS:
        sub = df[df["p"] >= thr]
        if sub.empty:
            continue
        prec = float(sub["y"].mean())
        cells = []
        for n in FWD_BARS:
            m = float(sub[f"f{n}"].mean(skipna=True)) - ROUND_TRIP
            cells.append(m)
        print(f"{thr:>5.2f} {len(sub):>7} {prec:>10.3f} " +
              " ".join(f"{c:>13.4%}" for c in cells))
        out_lines.append(f"| {thr:.2f} | {len(sub)} | {prec:.3f} | "
                         f"{prec / base:.2f}x | " +
                         " | ".join(f"{c:.4%}" for c in cells) + " |")

    verdict = ("READ: if precision AND net forward return both rise with the threshold, the "
               "flip machine was wasting the edge by trading everything at 0.5 and there is "
               "real headroom. If precision rises but net forward return stays <= 0, the label "
               "is detectable and NOT tradeable — the idea is closed on its own evidence.")
    out_lines += ["", verdict]
    p = HERE.parent / "backtest_results" / "CONFIDENCE_CURVE.md"
    p.write_text("\n".join(["# Confidence curve — is the edge concentrated?", ""] + out_lines),
                 encoding="utf-8")
    print(f"\nwrote -> {p}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
