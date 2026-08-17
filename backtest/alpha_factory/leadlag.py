"""Cross-asset lead-lag, TIME-SERIES form. The cross-sectional form (rank coins
by their correlation to gold/EURUSDT signed by the reference's trend — zoo.py's
goldregime_/usdregime_ factors) was already tested dead: 0 survivors. This asks
the strictly weaker question the mechanism actually predicts — dollar-liquidity
and risk-off flows hit the whole crypto complex at once, so the claim is about
BTC ITSELF, not about which coin outperforms. Signal: the sign of the reference
asset's LEADLAG_W-day trend at close t. Target: the anchor's forward return.

Kill line, per reference x horizon, all three legs required: the conditional
mean gap clears |t| >= LEADLAG_T_MIN with the overlap correction applied, its
sign is identical in EVERY purged fold (one lucky regime is not an edge), and a
toy overlay that is long only on the train-chosen favorable sign beats
buy-and-hold on the untouched OOS tail net of costs. Deterministic throughout —
nothing is fitted, so there is no seed and no train/test model leakage beyond
the favorable-sign choice, which is made on the train portion only."""
import numpy as np
import pandas as pd
from .evaluate import purged_folds

# Reference assets carrying the mechanism: gold as the risk-off hedge, EURUSDT as
# the dollar leg. Same pair as zoo.py's cross-asset factors — change together.
REFS = ("PAXGUSDT", "EURUSDT")


def _anchor(panel):
    """The series being predicted; mirrors regime.py's anchor choice."""
    px = panel.close
    return "BTCUSDT" if "BTCUSDT" in px.columns else px.columns[0]


def _sharpe(s, dpy):
    """Mirrors regime._sharpe (short windows report 0.0 rather than a noise ratio)."""
    s = s.dropna()
    return float(s.mean() / s.std() * np.sqrt(dpy)) if len(s) > 30 and s.std() > 0 else 0.0


def leadlag_signals(panel, cfg):
    """Sign of each reference's LEADLAG_W-day trend, decided at close t from
    closes <= t only. References absent from the panel — and a reference that IS
    the anchor, which would make this a self-prediction — are simply not columns."""
    px = panel.close
    anchor = _anchor(panel)
    refs = [r for r in REFS if r in px.columns and r != anchor]
    return pd.DataFrame({r: np.sign(px[r].pct_change(cfg.LEADLAG_W)) for r in refs},
                        index=px.index, columns=refs)


def diff_means_t(target, signal, h):
    """Two-sample difference of conditional means (signal>0 minus signal<0) with a
    pooled SE. h-day forward returns overlap on h-1 days, so the SE uses the
    effective counts n // h — the same overlap correction report.py applies to the
    IC series. Days with signal exactly 0 (flat trend) carry no directional claim
    and are dropped."""
    d = pd.concat([target.rename("y"), signal.rename("s")], axis=1).dropna()
    pos, neg = d.y[d.s > 0], d.y[d.s < 0]
    n_p, n_n = len(pos), len(neg)
    out = dict(n_pos=n_p, n_neg=n_n,
               mean_pos=float(pos.mean()) if n_p else float("nan"),
               mean_neg=float(neg.mean()) if n_n else float("nan"))
    out["diff"] = out["mean_pos"] - out["mean_neg"]
    e_p, e_n = n_p // h, n_n // h
    out["n_eff"] = e_p + e_n
    if e_p < 2 or e_n < 2:              # a variance needs 2 independent obs per side
        out["t"] = float("nan")
        return out
    sp2 = ((n_p - 1) * pos.var(ddof=1) + (n_n - 1) * neg.var(ddof=1)) / (n_p + n_n - 2)
    se = float(np.sqrt(sp2 * (1.0 / e_p + 1.0 / e_n)))
    out["t"] = out["diff"] / se if se > 0 else float("nan")
    return out


def fold_signs(target, signal, folds):
    """Sign of the conditional mean gap inside each purged fold. Nothing is fitted
    here, so fold 0 carries no train contamination and is judged like the rest; a
    fold that never sees both signal signs yields NaN — a sign that cannot be
    observed cannot confirm the effect, so it fails the agreement check."""
    out = []
    for f in folds:
        d = diff_means_t(target.reindex(f), signal.reindex(f), 1)
        out.append(float(np.sign(d["diff"])) if d["n_pos"] and d["n_neg"] else float("nan"))
    return out


def overlay_returns(anchor_ret, signal, favorable, cfg):
    """Toy book: long the anchor on days whose signal carries the favorable sign,
    flat otherwise, decided at close t and earned on t+1. Every flip pays
    fee+slip on the moved notional, exactly as regime.apply_gate charges the gate.
    Warmup NaNs read as not-favorable, i.e. flat."""
    pos = (signal == favorable).astype(float)
    flips = pos.diff().abs().fillna(0.0)
    # cost charged on the EXECUTION bar (t+1), same bar the return is earned — a flip
    # decided at close t pays when it trades (2026-08-18 audit #5 alignment fix)
    return pos.shift(1).fillna(0.0) * anchor_ret - flips.shift(1).fillna(0.0) * (cfg.TAKER_FEE + cfg.SLIPPAGE)


def leadlag_kill(panel, cfg):
    """Run the kill test for every reference present, at every LEADLAG_HORIZONS
    horizon. Top-level `passes` is True only if some reference x horizon survives
    all three legs — the track dies when none does."""
    px = panel.close
    anchor = _anchor(panel)
    sig = leadlag_signals(panel, cfg)
    a_close = px[anchor]
    a_ret = a_close.pct_change()
    folds = purged_folds(px.index, cfg.N_FOLDS, cfg.EMBARGO_DAYS)
    cut = int(len(px.index) * cfg.OOS_SPLIT)
    train, oos = px.index[:cut], px.index[cut:]
    rows = []
    for ref in sig.columns:
        s = sig[ref]
        for h in cfg.LEADLAG_HORIZONS:
            fwd = a_close.pct_change(h).shift(-h)     # close-to-close forward return, evaluate.py convention
            r = dict(ref=ref, horizon=h, **diff_means_t(fwd, s, h))
            fs = fold_signs(fwd, s, folds)
            r["fold_signs"] = fs
            r["folds_agree"] = bool(np.isfinite(r["diff"]) and fs
                                    and all(f == np.sign(r["diff"]) for f in fs))
            # the traded side is chosen on the TRAIN portion only; the OOS tail
            # never informs which sign to be long. A train gap that is NaN (a sign
            # never seen in train) leaves the long-the-up-trend prior in place.
            tr = diff_means_t(fwd.reindex(train), s.reindex(train), h)
            r["favorable_sign"] = -1.0 if tr["diff"] < 0 else 1.0
            ov = overlay_returns(a_ret, s, r["favorable_sign"], cfg).reindex(oos)
            r["n_oos_days"] = int(ov.notna().sum())
            r["overlay_sharpe"] = _sharpe(ov, cfg.DPY)
            r["hold_sharpe"] = _sharpe(a_ret.reindex(oos), cfg.DPY)
            r["passes"] = bool(np.isfinite(r["t"]) and abs(r["t"]) >= cfg.LEADLAG_T_MIN
                               and r["folds_agree"]
                               and r["overlay_sharpe"] > r["hold_sharpe"])
            rows.append(r)
    return dict(anchor=anchor, window=cfg.LEADLAG_W,
                refs_tested=list(sig.columns),
                refs_missing=[r for r in REFS if r not in sig.columns],
                n_days=int(len(px.index)), tests=rows,
                passes=any(r["passes"] for r in rows))
