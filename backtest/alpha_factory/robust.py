"""Robustness gauntlet — stage 1: circular block bootstrap on the net L/S return
series. Point estimates lie; a survivor is only trusted with a CI on its Sharpe and
a worst-plausible drawdown from the resampled paths. Block resampling (not iid)
preserves short-range autocorrelation; blocks wrap circularly so end-of-sample days
are not under-sampled."""
import math
import numpy as np


def _block_len(n):
    """Rule-of-thumb optimal block length ~ n^(1/3) (Hall/Politis-White order)."""
    return max(1, round(n ** (1 / 3)))


def _resample(r, n_boot, rng):
    """(n_boot, n) matrix of circular-block resampled paths of r."""
    n = len(r)
    L = _block_len(n)
    n_blocks = math.ceil(n / L)
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    offs = np.arange(L)
    idx = (starts[:, :, None] + offs[None, None, :]).reshape(n_boot, -1)[:, :n] % n
    return r[idx]


def _maxdd(paths):
    """Max drawdown per path as a POSITIVE fraction of peak equity."""
    eq = np.cumprod(1.0 + paths, axis=1)
    peak = np.maximum.accumulate(eq, axis=1)
    return (1.0 - eq / peak).max(axis=1)


def bootstrap_stats(series, dpy, n_boot, ci, seed):
    """Sharpe CI + drawdown distribution for a net daily return series.
    Returns sharpe_lo/sharpe_hi (central `ci` interval), maxdd_med, maxdd_p95
    (worst-plausible DD — size from this, not the single observed DD)."""
    r = series.dropna().to_numpy(dtype=float)
    if len(r) < 2 or r.std() == 0:
        return dict(sharpe_lo=0.0, sharpe_hi=0.0, maxdd_med=0.0, maxdd_p95=0.0)
    paths = _resample(r, n_boot, np.random.default_rng(seed))
    mu, sd = paths.mean(axis=1), paths.std(axis=1)
    sharpes = np.where(sd > 0, mu / np.where(sd > 0, sd, 1.0) * math.sqrt(dpy), 0.0)
    lo, hi = np.quantile(sharpes, [(1 - ci) / 2, (1 + ci) / 2])
    dd = _maxdd(paths)
    return dict(sharpe_lo=float(lo), sharpe_hi=float(hi),
                maxdd_med=float(np.median(dd)), maxdd_p95=float(np.quantile(dd, 0.95)))


def is_fragile(boot):
    """A survivor whose Sharpe CI does not clear zero is flagged, not trusted."""
    return boot["sharpe_lo"] <= 0
