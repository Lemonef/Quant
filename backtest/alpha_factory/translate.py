"""Track B — turnover-aware translation. The IC class is proven (ml_ranker OOS
IC 0.04-0.09; 77 FDR-passing factors on 2026-07-15) and dies ONLY on trading
costs, so the lever is the score->position mapping, not the model: (a) EWMA
score smoothing, (b) hysteresis bands — enter the top K, HOLD until the name
decays past a wider exit rank, so ranks may churn while positions do not.
Kill line (cheap screen): net Sharpe > 0 on every OOS fold. Survivors then face
the FULL gauntlet with n_trials honestly incremented per variant tried."""
import numpy as np
import pandas as pd
from .evaluate import ls_returns, purged_folds, fold_sharpes


def smooth(score, halflife):
    """EWMA over time per coin — scores churn daily, positions should not."""
    return score.ewm(halflife=halflife, min_periods=1).mean().where(score.notna())


def turnover_of(score, k_frac):
    """Mean daily one-sided turnover of the plain top-K long book of `score`."""
    rk = score.rank(axis=1, ascending=False)
    n = score.count(axis=1)
    k = np.maximum(2, (n * k_frac).astype(int))
    w = rk.le(k, axis=0).astype(float)
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return float(w.diff().abs().sum(axis=1).mean())


def banded_weights(score, k_frac, exit_mult):
    """Hysteresis long/short book: enter when rank <= K (long) / >= n-K (short),
    exit only when rank decays past K*exit_mult (mirrored for shorts). Row loop —
    position state at t depends on the held book at t-1."""
    rk = score.rank(axis=1, ascending=False)
    n = score.count(axis=1)
    k = np.maximum(2, (n * k_frac).astype(int))
    long_state = pd.Series(False, index=score.columns)
    short_state = pd.Series(False, index=score.columns)
    rows = []
    for t in score.index:
        r, nn, kk = rk.loc[t], n.at[t], k.at[t]
        if nn < 2:
            rows.append(pd.Series(0.0, index=score.columns)); continue
        enter_l, keep_l = r <= kk, r <= kk * exit_mult
        enter_s, keep_s = r > nn - kk, r > nn - kk * exit_mult
        long_state = (long_state & keep_l) | enter_l
        short_state = (short_state & keep_s) | enter_s
        wl = long_state.astype(float); ws = short_state.astype(float)
        wl = wl / wl.sum() if wl.sum() else wl
        ws = ws / ws.sum() if ws.sum() else ws
        rows.append(wl - ws)
    return pd.DataFrame(rows, index=score.index).fillna(0.0)


def _banded_net(score, panel, cfg):
    w = banded_weights(score, cfg.K_FRAC, cfg.BAND_EXIT_MULT)
    turn = w.diff().abs().sum(axis=1).fillna(0.0)
    gross = (w.shift(1).fillna(0.0) * panel.ret).sum(axis=1)
    short = w.clip(upper=0.0).abs().sum(axis=1)
    return (gross - turn * (cfg.TAKER_FEE + cfg.SLIPPAGE)
            - short.shift(1).fillna(0.0) * cfg.BORROW_ANNUAL / cfg.DPY)


def track_b_kill(score, panel, cfg):
    """Run the preregistered variant set over one score frame. raw = reference
    only; the 4 translations are the trials."""
    folds = purged_folds(panel.close.index, cfg.N_FOLDS, cfg.EMBARGO_DAYS)

    def _ls(s):
        return ls_returns(s, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                          cfg.BORROW_ANNUAL, cfg.DPY)

    h_fast, h_slow = cfg.SMOOTH_HALFLIVES
    series = {
        "raw": _ls(score),
        f"smooth_{h_fast}": _ls(smooth(score, h_fast)),
        f"smooth_{h_slow}": _ls(smooth(score, h_slow)),
        "band": _banded_net(score, panel, cfg),
        f"smooth_{h_slow}_band": _banded_net(smooth(score, h_slow), panel, cfg),
    }
    variants = {}
    for name, s in series.items():
        fs = fold_sharpes(s, folds, cfg.DPY)
        sr = float(s.mean() / s.std() * np.sqrt(cfg.DPY)) if s.std() > 0 else 0.0
        variants[name] = dict(net_sharpe=sr, fold_sharpes=fs,
                              passes=bool(name != "raw" and min(fs) > 0))
    return dict(variants=variants, n_trials_added=len(series) - 1)
