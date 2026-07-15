"""Orchestration + scoreboard rendering."""
from pathlib import Path
import numpy as np, pandas as pd
from . import config as _cfg
from .evaluate import ic_stats, ls_returns, purged_folds, fold_sharpes, daily_ic
from .stats import ic_pvalue, bh_fdr, deflated_sharpe_prob, verdict
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
                         turnover=float(np.nan_to_num(lsr.abs().mean())), _lsr=lsr))
    return rows

def _finalize(rows, panel, cfg):
    """Pool the given rows through one BH-FDR, then verdict + incumbent-improvement each."""
    keep = bh_fdr([r["pval"] for r in rows], cfg.FDR_Q)
    sleeves = incumbent_sleeves(panel, cfg)
    for r, k in zip(rows, keep):
        r["pval_pass"] = bool(k)
        r["verdict"], r["reason"] = verdict(r, cfg)
        if r["verdict"] == "SURVIVED":
            imp = improvement(r.pop("_lsr"), sleeves, cfg)
            r.update(max_corr=imp["max_corr"], delta_sharpe=round(imp["delta_sharpe"], 3),
                     delta_maxdd=round(imp["delta_maxdd"], 3), improves_book=imp["improves"])
            if imp["redundant"]:
                r["reason"] += " (REDUNDANT vs incumbent sleeve)"
        else:
            r.pop("_lsr"); r.update(max_corr=np.nan, delta_sharpe=np.nan,
                                    delta_maxdd=np.nan, improves_book=False)
    return pd.DataFrame(rows).sort_values(["verdict", "dsr_prob"], ascending=[False, False]).reset_index(drop=True)

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
    lines = [f"# Alpha Factory scoreboard — {stamp}", "",
             f"> {cfg.SURVIVORSHIP_CAVEAT}", "", f"Config: `{cfg_dump}`",
             f"Factors tested: {len(df)} · SURVIVED: {len(surv)} · REJECTED: {len(df) - len(surv)}", "",
             "## SURVIVED (sorted by deflated-Sharpe probability)", "",
             "| factor | family | rebal | prov | IC1 | ICIR1 | LS Sharpe | folds | DSRp | maxCorr | ΔSharpe | ΔDD | IMPROVES BOOK |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in surv.iterrows():
        folds = "/".join(f"{x:.1f}" for x in r.fold_sharpes)
        lines.append(f"| {r['name']} | {r.family} | {r.rebal} | {r.provenance.split()[0]} | {r.ic_1:.3f} | {r.icir_1:.1f} | "
                     f"{r.ls_sharpe:.2f} | {folds} | {r.dsr_prob:.2f} | {r.max_corr:.2f} | "
                     f"{r.delta_sharpe:+.3f} | {r.delta_maxdd:+.3f} | {'YES' if r.improves_book else 'no'} |")
    lines += ["", "## REJECTED — count by reason", ""]
    for reason, n in df[df.verdict == "REJECTED"].reason.value_counts().items():
        lines.append(f"- {n:4d} × {reason}")
    lines += ["", f"Full per-factor table: `{csv.name}`", ""]
    md.write_text("\n".join(lines))
    return md, csv
