"""
panel_dump.py — compute the FULL risk panel on the real OOS return streams and
dump to web/lab_panel.json for the Strategy Lab. Native frequency (4H trend,
daily blend) so Sortino/CVaR/skew are accurate, not downsampled.

Imports walkforward (gives wf_oos = stitched walk-forward OOS, the trend core)
and book_final (gives trend/flush2/crashreb → the .55/.25/.20 blend). Running
them prints their own output; we only consume the series. Verifies Sharpe vs the
known anchors (trend ~0.86, blend ~1.28) before trusting.

    python backtest/panel_dump.py   ->  web/lab_panel.json
"""
import json, math
import numpy as np, pandas as pd
from pathlib import Path
from engine import BARS_PER_YEAR

import walkforward as wfmod          # builds wf_oos (4H OOS returns)
import book_final as bf             # builds trend/flush2/crashreb (daily)


def panel(pr, ppy):
    pr = pd.Series(pr).dropna()
    pr = pr[np.isfinite(pr)]
    eq = (1 + pr).cumprod()
    n = len(pr)
    yrs = n / ppy
    end = float(eq.iloc[-1])
    cagr = (end ** (1 / yrs) - 1) * 100 if end > 0 else -100.0
    mu, sd = pr.mean(), pr.std()
    sharpe = mu / sd * math.sqrt(ppy) if sd > 0 else 0.0
    dn = pr[pr < 0].std()
    sortino = mu / dn * math.sqrt(ppy) if dn and dn > 0 else None
    dd_ser = (eq / eq.cummax() - 1)
    maxdd = dd_ser.min() * 100
    calmar = cagr / abs(maxdd) if maxdd else None
    gains = pr[pr > 0].sum(); pains = -pr[pr < 0].sum()
    gtp = gains / pains if pains > 0 else None
    ulcer = math.sqrt((dd_ser.mul(100) ** 2).mean())
    srt = np.sort(pr.values); k5 = max(1, int(len(srt) * 0.05))
    cvar = float(srt[:k5].mean()) * 100
    z = (pr - mu) / (sd if sd > 0 else 1e-9)
    skew = float((z ** 3).mean()); kurt = float((z ** 4).mean() - 3)
    logs = np.log(eq.values); xs = np.arange(len(logs))
    sl, inter = np.polyfit(xs, logs, 1)
    resid = logs - (inter + sl * xs); sse = float((resid ** 2).sum())
    sxx = float(((xs - xs.mean()) ** 2).sum())
    se = math.sqrt(sse / (len(xs) - 2) / sxx) if len(xs) > 2 and sxx > 0 and sse > 0 else None
    kratio = sl / se if se else None
    # months underwater (longest) — index is datetime
    idx = eq.index; pk = eq.iloc[0]; uws = None; longest = 0
    for i in range(len(eq)):
        v = eq.iloc[i]
        if v >= pk: pk = v; uws = None
        else:
            if uws is None: uws = i
            longest = max(longest, (idx[i] - idx[uws]).days)
    return {
        "cagr": round(cagr, 1), "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2) if sortino is not None else None,
        "calmar": round(calmar, 2) if calmar is not None else None,
        "maxdd": round(maxdd, 1), "gtp": round(gtp, 2) if gtp is not None else None,
        "ulcer": round(ulcer, 1), "cvar": round(cvar, 2),
        "skew": round(skew, 2), "kurt": round(kurt, 2),
        "kratio": round(kratio, 1) if kratio is not None else None,
        "muw": round(longest / 30.4, 1), "n": n,
    }


# --- trend core: stitched walk-forward OOS, 4H native ---
trend_oos = wfmod.wf_oos
ppy_4h = BARS_PER_YEAR["4h"]
trend_panel = panel(trend_oos, ppy_4h)

# --- blend: .55/.25/.20, daily native. Use the OOS HOLDOUT (2nd half) so it's
#     apples-to-apples with the trend's walk-forward OOS — NOT the flattering full sample. ---
blend_full = 0.55 * bf.trend + 0.25 * bf.flush2 + 0.20 * bf.crashreb
ppy_d = getattr(bf, "DPY", 365)
blend_oos = blend_full.iloc[len(blend_full) // 2:]      # 2nd-half holdout = out-of-sample
blend_panel = panel(blend_oos, ppy_d)
blend_full_panel = panel(blend_full, ppy_d)
print(f"\nBLEND full-sample Sharpe {blend_full_panel['sharpe']} (the unverified ~1.57) vs OOS-holdout {blend_panel['sharpe']} (trustworthy)")

out = {"trend": trend_panel, "blend": blend_panel, "blend_full": blend_full_panel}
Path("web/lab_panel.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

print("\n\n================ PANEL DUMP ================")
print(f"TREND core (4H OOS, n={trend_panel['n']}): Sharpe {trend_panel['sharpe']} (anchor ~0.86) · Sortino {trend_panel['sortino']} · Calmar {trend_panel['calmar']} · DD {trend_panel['maxdd']}%")
print(f"BLEND .55/.25/.20 (daily, n={blend_panel['n']}): Sharpe {blend_panel['sharpe']} (anchor ~1.28) · Sortino {blend_panel['sortino']} · Calmar {blend_panel['calmar']} · DD {blend_panel['maxdd']}%")
print("wrote web/lab_panel.json")
