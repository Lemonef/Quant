"""Multiple-testing control: p-values, Benjamini-Hochberg FDR, deflated Sharpe
(Bailey & Lopez de Prado). Metric conventions cross-checked against the open
GS-Quant timeseries module. stdlib NormalDist — no scipy dependency."""
import math
from statistics import NormalDist

N = NormalDist()


def ic_pvalue(ic_mean, ic_std_daily, n_days):
    """Two-sided p for mean daily IC != 0 (normal approx of the t-stat)."""
    if not (ic_std_daily > 0) or n_days < 2:   # not-> also catches NaN std (e.g. a 1-obs IC series)
        return 1.0
    t = ic_mean / ic_std_daily * math.sqrt(n_days)
    return 2 * (1 - N.cdf(abs(t)))


def bh_fdr(pvals, q):
    """Benjamini-Hochberg: True where the hypothesis survives at FDR q.
    Tracks the passing RANK (not the threshold value) so a p-value of exactly 0.0
    still passes — 'threshold is 0.0' must not read as 'nothing passed'."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    k_star = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            k_star = rank
    if k_star == 0:
        return [False] * m
    thresh = pvals[order[k_star - 1]]
    return [p <= thresh for p in pvals]


def deflated_sharpe_prob(sr_annual, n_days, dpy, skew, kurt_excess, n_trials):
    """P(true SR > 0) given best-of-n_trials selection bias. Daily-unit SR internally."""
    if n_days < 30:
        return 0.0
    sr = sr_annual / math.sqrt(dpy)
    e = 0.5772156649015329  # Euler-Mascheroni
    if n_trials > 1:
        z1 = N.inv_cdf(1 - 1.0 / n_trials)
        z2 = N.inv_cdf(1 - 1.0 / (n_trials * math.e))
        sr0 = math.sqrt(1.0 / n_days) * ((1 - e) * z1 + e * z2)
    else:
        sr0 = 0.0
    denom = math.sqrt(max(1e-12, 1 - skew * sr + kurt_excess / 4.0 * sr * sr))
    return N.cdf((sr - sr0) * math.sqrt(n_days - 1) / denom)


def verdict(row, cfg):
    """row keys: n_days, pval_pass, fold_sharpes, ic_base, ic_decay, dsr_prob."""
    if row["n_days"] < cfg.MIN_OBS_DAYS:
        return "REJECTED", f"too few observations ({row['n_days']})"
    if not row["pval_pass"]:
        return "REJECTED", "failed FDR"
    if min(row["fold_sharpes"]) <= 0:
        return "REJECTED", "negative OOS fold"
    # decay gate: signal must still be alive at the next-higher horizon. None => no higher
    # horizon exists (traded at the max speed), so nothing to decay into — gate passes.
    if row["ic_decay"] is not None:
        same_sign = row["ic_base"] * row["ic_decay"] > 0
        if not (same_sign and abs(row["ic_decay"]) >= cfg.DECAY_MIN_RATIO * abs(row["ic_base"])):
            return "REJECTED", "signal decays too fast"
    if row["dsr_prob"] < cfg.DSR_MIN_PROB:
        return "REJECTED", f"deflated Sharpe prob {row['dsr_prob']:.2f}"
    return "SURVIVED", "passed FDR + all folds + decay + DSR"
