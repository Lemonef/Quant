"""Orchestration + scoreboard rendering."""
from pathlib import Path
import numpy as np, pandas as pd
from . import config as _cfg
from .evaluate import ic_stats, ls_returns, purged_folds, fold_sharpes, daily_ic
from .stats import ic_pvalue, bh_fdr, deflated_sharpe_prob, verdict
from .robust import (bootstrap_stats, is_fragile, perturbation_stats, perturb_notes,
                     plateau_check, pbo_cscv, spa_pvalue)
from .bench import incumbent_sleeves, improvement

def _next_horizon(h, horizons):
    """Next-higher horizon above h in the configured ladder, or None if h is the top."""
    higher = [x for x in sorted(horizons) if x > h]
    return higher[0] if higher else None

def _score_rows(panel, zoo, cfg, rebalance, n_trials):
    """Score every factor at trading speed R=rebalance: p-value from the R-day IC series,
    L/S net return held R days, decay measured into the next-higher horizon. Returns the
    raw row dicts (each keeping `_lsr`). R=1 reproduces the single-speed behavior exactly."""
    R = rebalance
    folds = purged_folds(panel.close.index, cfg.N_FOLDS, cfg.EMBARGO_DAYS)
    ic_next = _next_horizon(R, cfg.HORIZONS)
    rows = []
    for f in zoo:
        fac = f.fn(panel)
        s = ic_stats(fac, panel.close, cfg.HORIZONS)
        fwd = panel.close.pct_change(R).shift(-R)          # R-day forward return
        icR = daily_ic(fac, fwd).dropna()
        n_eff = len(icR) // R                              # overlap correction: R-day returns overlap, so ~len/R independent obs (conservative; ic_pvalue guards n<2)
        lsr = ls_returns(fac, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                         cfg.BORROW_ANNUAL, cfg.DPY, rebalance=R)
        fs = fold_sharpes(lsr, folds, cfg.DPY)
        sr = float(lsr.mean() / lsr.std() * np.sqrt(cfg.DPY)) if lsr.std() > 0 else 0.0
        rows.append(dict(name=f.name, family=f.family, provenance=f.provenance, rebal=R,
                         ic_1=s.get("ic_1", 0.0), icir_1=s.get("icir_1", 0.0),
                         ic_5=s.get("ic_5", 0.0), ic_20=s.get("ic_20", 0.0),
                         ic_base=s[f"ic_{R}"],                         # IC at the traded horizon (KeyError = R not in HORIZONS: fail loudly, never auto-reject on a silent 0.0)
                         ic_decay=(s[f"ic_{ic_next}"] if ic_next else None),  # next horizon, or None at the top speed
                         n_days=s.get("n_days", 0), ls_sharpe=sr, fold_sharpes=fs,
                         pval=ic_pvalue(float(icR.mean()), float(icR.std()), n_eff),
                         dsr_prob=deflated_sharpe_prob(sr, len(lsr.dropna()), cfg.DPY,
                                                       float(lsr.skew() or 0), float(lsr.kurt() or 0), n_trials),
                         turnover=float(np.nan_to_num(lsr.abs().mean())), _lsr=lsr, _fn=f.fn))
    return rows

def _finalize(rows, panel, cfg):
    """Pool the given rows through one BH-FDR, then verdict + incumbent-improvement each."""
    keep = bh_fdr([r["pval"] for r in rows], cfg.FDR_Q)
    sleeves = incumbent_sleeves(panel, cfg)
    # run-level probes over the WHOLE candidate panel (warmup NaNs read as flat days)
    lsr_panel = pd.DataFrame({f"{r['name']}|{r['rebal']}": r["_lsr"] for r in rows}).fillna(0.0)
    pbo = pbo_cscv(lsr_panel, cfg.CSCV_BLOCKS)
    spa_p = spa_pvalue(lsr_panel, cfg.BOOT_N, cfg.BOOT_SEED)
    for r, k in zip(rows, keep):
        r["pval_pass"] = bool(k)
        r["verdict"], r["reason"] = verdict(r, cfg)
        if r["verdict"] == "SURVIVED":
            lsr = r.pop("_lsr")
            imp = improvement(lsr, sleeves, cfg)
            r.update(max_corr=imp["max_corr"], delta_sharpe=round(imp["delta_sharpe"], 3),
                     delta_maxdd=round(imp["delta_maxdd"], 3), improves_book=imp["improves"])
            if imp["redundant"]:
                r["reason"] += " (REDUNDANT vs incumbent sleeve)"
            boot = bootstrap_stats(lsr, cfg.DPY, cfg.BOOT_N, cfg.BOOT_CI, cfg.BOOT_SEED,
                                   cfg.BOOT_DD_Q)
            r.update(**boot)
            if is_fragile(boot):
                r["reason"] += " (FRAGILE: Sharpe CI spans 0)"
            pert = perturbation_stats(r.pop("_fn"), panel, cfg, r["rebal"])
            r.update(**pert)
            for tag in perturb_notes(pert):
                r["reason"] += f" ({tag})"
            plateau = plateau_check(r["name"], r["rebal"], rows)
            r["plateau_pass"] = np.nan if plateau is None else plateau
            if plateau is False:
                r["reason"] += " (CLIFF: adjacent-parameter sibling dies)"
        else:
            r.pop("_lsr"); r.pop("_fn")
            r.update(max_corr=np.nan, delta_sharpe=np.nan,
                     delta_maxdd=np.nan, improves_book=False,
                     sharpe_lo=np.nan, sharpe_hi=np.nan,
                     maxdd_med=np.nan, maxdd_p95=np.nan,
                     sharpe_lag=np.nan, sharpe_noise=np.nan, plateau_pass=np.nan)
    df = pd.DataFrame(rows).sort_values(["verdict", "dsr_prob"], ascending=[False, False]).reset_index(drop=True)
    df.attrs["pbo"] = pbo
    df.attrs["spa_p"] = spa_p
    return df

def run_factory(panel, zoo, cfg=_cfg, n_trials=None, rebalance=1):
    """Single-speed run (default rebalance=1). Default args reproduce the pre-variant output."""
    n_trials = n_trials or len(zoo)
    return _finalize(_score_rows(panel, zoo, cfg, rebalance, n_trials), panel, cfg)

def run_speeds(panel, zoo, cfg=_cfg):
    """Score every factor at every rebalance speed and pool ALL rows through a single
    BH-FDR — the honest multiplicity control across every factor×speed pair."""
    n_trials = len(zoo) * len(cfg.REBALANCE_PERIODS)
    rows = []
    for R in cfg.REBALANCE_PERIODS:
        rows += _score_rows(panel, zoo, cfg, R, n_trials)
    return _finalize(rows, panel, cfg)

def render(df, cfg, out_dir, stamp):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    md, csv = out_dir / f"ALPHA_FACTORY_{stamp}.md", out_dir / f"ALPHA_FACTORY_{stamp}.csv"
    df.drop(columns=[c for c in df.columns if c.startswith("_")], errors="ignore").to_csv(csv, index=False)
    surv = df[df.verdict == "SURVIVED"]
    cfg_dump = {k: getattr(cfg, k) for k in dir(cfg) if k.isupper() and k != "SURVIVORSHIP_CAVEAT"}
    pbo = df.attrs.get("pbo")
    pbo_line = (f"Run-level PBO (CSCV, {cfg.CSCV_BLOCKS} blocks): {pbo:.2f} — "
                "probability the best in-sample pick underperforms the OOS median"
                if pbo is not None and not np.isnan(pbo) else "Run-level PBO: n/a")
    spa = df.attrs.get("spa_p")
    spa_line = (f"Hansen SPA p (best row vs zero, whole search): {spa:.3f}"
                if spa is not None and not np.isnan(spa) else "Hansen SPA p: n/a")
    lines = [f"# Alpha Factory scoreboard — {stamp}", "",
             f"> {cfg.SURVIVORSHIP_CAVEAT}", "", f"Config: `{cfg_dump}`",
             f"Factors tested: {len(df)} · SURVIVED: {len(surv)} · REJECTED: {len(df) - len(surv)}",
             pbo_line, spa_line, "",
             "## SURVIVED (sorted by deflated-Sharpe probability)", "",
             "| factor | family | rebal | prov | IC1 | ICIR1 | LS Sharpe | Sharpe CI | DD p95 | folds | DSRp | maxCorr | ΔSharpe | ΔDD | IMPROVES BOOK |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in surv.iterrows():
        folds = "/".join(f"{x:.1f}" for x in r.fold_sharpes)
        lines.append(f"| {r['name']} | {r.family} | {r.rebal} | {r.provenance.split()[0]} | {r.ic_1:.3f} | {r.icir_1:.1f} | "
                     f"{r.ls_sharpe:.2f} | [{r.sharpe_lo:.2f}, {r.sharpe_hi:.2f}] | {r.maxdd_p95:.0%} | "
                     f"{folds} | {r.dsr_prob:.2f} | {r.max_corr:.2f} | "
                     f"{r.delta_sharpe:+.3f} | {r.delta_maxdd:+.3f} | {'YES' if r.improves_book else 'no'} |")
    lines += ["", "## REJECTED — count by reason", ""]
    for reason, n in df[df.verdict == "REJECTED"].reason.value_counts().items():
        lines.append(f"- {n:4d} × {reason}")
    lines += ["", f"Full per-factor table: `{csv.name}`", ""]
    md.write_text("\n".join(lines))
    return md, csv
