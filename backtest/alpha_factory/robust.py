"""Robustness gauntlet — post-verdict probes run on survivors only.
Stage 1: circular block bootstrap on the net L/S return series. Point estimates
lie; a survivor is only trusted with a CI on its Sharpe and a worst-plausible
drawdown from the resampled paths. Block resampling (not iid) preserves
short-range autocorrelation; blocks wrap circularly so end-of-sample days are
not under-sampled.
Stage 2: lag + price-noise perturbation. Execute t+2 instead of t+1, and re-run
on prices jittered at the slippage scale — a real edge degrades gracefully,
an artifact of exact timing or exact prices dies."""
import math
from itertools import combinations
import numpy as np
from .evaluate import ls_returns
from .panel import Panel


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


def _ann_sharpe(s, dpy):
    s = s.dropna()
    return float(s.mean() / s.std() * math.sqrt(dpy)) if len(s) > 1 and s.std() > 0 else 0.0


def _noisy_panel(panel, sigma, rng):
    """Panel with multiplicative price noise: one jitter factor per (day, coin),
    applied to all four price fields so OHLC stays coherent. Volume/funding as-is."""
    eps = 1.0 + rng.normal(0.0, sigma, panel.close.shape)
    j = lambda df: df * eps
    return Panel(j(panel.open), j(panel.high), j(panel.low), j(panel.close),
                 panel.volume, panel.funding)


def perturbation_stats(fn, panel, cfg, rebalance):
    """Annualized net Sharpe under (a) t+2 execution and (b) price noise at the
    SLIPPAGE scale (the factor is recomputed on the noisy panel — signals built
    from exact prices must survive execution-sized uncertainty). Noise Sharpe is
    the median over NOISE_N seeded re-runs so one draw cannot decide."""
    fac = fn(panel)
    lag = ls_returns(fac, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                     cfg.BORROW_ANNUAL, cfg.DPY, rebalance=rebalance, delay=2)
    noise = []
    for i in range(cfg.NOISE_N):
        noisy = _noisy_panel(panel, cfg.SLIPPAGE, np.random.default_rng(cfg.BOOT_SEED + i))
        nl = ls_returns(fn(noisy), noisy.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                        cfg.BORROW_ANNUAL, cfg.DPY, rebalance=rebalance)
        noise.append(_ann_sharpe(nl, cfg.DPY))
    return dict(sharpe_lag=_ann_sharpe(lag, cfg.DPY), sharpe_noise=float(np.median(noise)))


def perturb_notes(pert):
    """Tags for perturbations that killed the edge (Sharpe driven to <= 0)."""
    notes = []
    if pert["sharpe_lag"] <= 0:
        notes.append("LAG-FRAIL")
    if pert["sharpe_noise"] <= 0:
        notes.append("NOISE-FRAIL")
    return notes


def pbo_cscv(matrix, n_blocks):
    """Probability of backtest overfitting via CSCV (Bailey, Borwein, Lopez de
    Prado, Zhu 2017). matrix: days x strategies of net daily returns. Time is cut
    into n_blocks contiguous blocks; for every balanced IS/OOS block split the
    IS-best strategy's OOS relative rank feeds a logit; PBO = share of splits
    where the IS winner lands at or below the OOS median. Selection metric is
    daily Sharpe (annualization cancels in ranks). Deterministic — no resampling.
    Block sums/sum-of-squares are precomputed so the C(n_blocks, n_blocks/2)
    combinations cost matrix algebra, not passes over the data."""
    M = np.asarray(matrix, dtype=float)
    n, s = M.shape
    if s < 2 or n < n_blocks:
        return float("nan")
    blocks = np.array_split(np.arange(n), n_blocks)
    bsum = np.array([M[b].sum(axis=0) for b in blocks])
    bsq = np.array([(M[b] ** 2).sum(axis=0) for b in blocks])
    bn = np.array([len(b) for b in blocks], dtype=float)

    def _sharpe(mask):
        cnt = bn[mask].sum()
        mu = bsum[mask].sum(axis=0) / cnt
        var = bsq[mask].sum(axis=0) / cnt - mu ** 2
        return mu / np.sqrt(np.maximum(var, 1e-18))

    lam = []
    for c in combinations(range(n_blocks), n_blocks // 2):
        mask = np.zeros(n_blocks, dtype=bool)
        mask[list(c)] = True
        si, so = _sharpe(mask), _sharpe(~mask)
        best = int(np.argmax(si))
        w = np.sum(so <= so[best]) / (s + 1)   # OOS relative rank of the IS winner, in (0,1)
        lam.append(math.log(w / (1 - w)))
    return float(np.mean(np.array(lam) <= 0))


def param_key(name):
    """(stem, params) from the zoo naming convention `<stem>_<int>[_<int>...]`.
    params is None for parameter-free factors (no trailing integer parts)."""
    parts = name.split("_")
    nums = []
    while parts and parts[-1].isdigit():
        nums.append(int(parts.pop()))
    return "_".join(parts), (tuple(reversed(nums)) or None)


def plateau_check(name, rebal, rows):
    """Parameter-plateau probe using rows ALREADY scored in this run: the zoo's
    window grids (mom_5..252, lowvol_10/21/63, ...) are the neighbor set, so no
    factor is recomputed. The adjacent lower and higher sibling (same stem, same
    trading speed, ordered by parameter tuple) must both keep Sharpe > 0 — a
    performance cliff one notch away marks a curve-fit peak, a plateau marks a
    robust region. Returns True/False, or None when no sibling exists."""
    stem, params = param_key(name)
    if params is None:
        return None
    sibs = []
    for r in rows:
        s, p = param_key(r["name"])
        if s == stem and p is not None and r["rebal"] == rebal and p != params:
            sibs.append((p, r["ls_sharpe"]))
    lower = [x for x in sibs if x[0] < params]
    higher = [x for x in sibs if x[0] > params]
    neighbors = ([max(lower)] if lower else []) + ([min(higher)] if higher else [])
    if not neighbors:
        return None
    return all(sharpe > 0 for _, sharpe in neighbors)
