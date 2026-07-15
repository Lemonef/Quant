"""Per-factor evaluation: cross-sectional IC + decay, net quantile L/S, purged folds."""
import numpy as np
import pandas as pd


def daily_ic(factor, fwd):
    """Per-day cross-sectional Spearman IC (rank both sides, then row-wise Pearson)."""
    fr = factor.rank(axis=1)
    rr = fwd.rank(axis=1)
    return fr.corrwith(rr, axis=1)


def ic_stats(factor, close, horizons):
    out = {}
    for h in horizons:
        fwd = close.pct_change(h).shift(-h)          # forward h-day return
        ic = daily_ic(factor, fwd).dropna()
        out[f"ic_{h}"] = float(ic.mean())
        out[f"icir_{h}"] = float(ic.mean() / ic.std() * np.sqrt(len(ic))) if ic.std() > 0 else 0.0
        out["n_days"] = int(len(ic))
    return out


def ls_returns(factor, ret, k_frac, fee, slip, borrow_annual, dpy, rebalance=1):
    """Dollar-neutral top-K/bottom-K L/S, executed next day, net of fee+slippage on
    turnover and borrow on the short leg. rebalance>1 re-ranks only every R-th row
    and holds weights in between (equal-weight-at-rebalance; intra-period drift not
    modeled). All cost lines are functions of the HELD weights — borrow in particular
    must not be charged while the held book is empty (e.g. a factor's NaN warmup)."""
    n = factor.count(axis=1)
    k = np.maximum(2, (n * k_frac).astype(int))
    rk = factor.rank(axis=1, ascending=False)
    wl = rk.le(k, axis=0).astype(float)
    ws = rk.gt((n - k), axis=0).astype(float)
    wl = wl.div(wl.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    ws = ws.div(ws.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    w = wl - ws
    if rebalance > 1:  # re-rank only every R-th row, forward-fill the held weights between
        mask = pd.Series(np.arange(len(w)) % rebalance == 0, index=w.index)
        w = w.where(mask).ffill().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    gross = (w.shift(1).fillna(0.0) * ret).sum(axis=1)
    short = w.clip(upper=0.0).abs().sum(axis=1)   # short leg of the HELD book, not the daily re-rank
    return gross - turn * (fee + slip) - short.shift(1).fillna(0.0) * borrow_annual / dpy


def purged_folds(index, n_folds, embargo_days):
    """Contiguous OOS folds with an embargo gap dropped at each boundary."""
    blocks = np.array_split(np.arange(len(index)), n_folds)
    folds = []
    for i, b in enumerate(blocks):
        s = b[embargo_days:] if i > 0 else b        # drop embargo at the leading edge
        folds.append(index[s])
    return folds


def fold_sharpes(series, folds, dpy):
    out = []
    for f in folds:
        s = series.reindex(f).dropna()
        out.append(float(s.mean() / s.std() * np.sqrt(dpy)) if len(s) > 30 and s.std() > 0 else 0.0)
    return out
