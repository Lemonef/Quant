import numpy as np


def test_bh_fdr_known_case():
    from alpha_factory.stats import bh_fdr
    pv = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    # hand-check: thresholds q*k/m = .005,.010,.015,... -> largest k with p(k)<=q*k/m is k=2
    keep = bh_fdr(pv, 0.05)
    assert keep == [True, True, False, False, False, False, False, False, False, False]
    # and a case where a later rank rescues earlier ones (step-up property)
    pv2 = [0.010, 0.012, 0.014, 0.9]
    assert bh_fdr(pv2, 0.05) == [True, True, True, False]  # k=3: 0.014 <= 0.0375
    # regression: an exact p=0.0 (t-stat underflow) must SURVIVE, not nuke the batch
    assert bh_fdr([0.0, 0.5, 0.9], 0.10) == [True, False, False]
    assert bh_fdr([0.9, 0.8, 0.7], 0.10) == [False, False, False]  # nothing passes


def test_ic_pvalue_scales():
    from alpha_factory.stats import ic_pvalue
    assert ic_pvalue(0.05, 0.2, 900) < 0.01          # strong, long sample
    assert ic_pvalue(0.01, 0.2, 100) > 0.5           # weak, short sample


def test_deflated_sharpe_punishes_trials():
    from alpha_factory.stats import deflated_sharpe_prob
    hi = deflated_sharpe_prob(1.5, 900, 365, 0.0, 0.0, n_trials=1)
    lo = deflated_sharpe_prob(1.5, 900, 365, 0.0, 0.0, n_trials=150)
    assert hi > lo and lo < 0.99


def test_noise_zoo_fdr_bound():
    """~200 pure-noise factors: survivors must be rare (FDR holds)."""
    import pandas as pd
    from alpha_factory.panel import build_synth_panel
    from alpha_factory.stats import ic_pvalue, bh_fdr
    panel, _ = build_synth_panel(seed=42, signal_strength=0.0)
    rng = np.random.default_rng(1)
    fwd = panel.close.pct_change().shift(-1)
    fwd_rank = fwd.rank(axis=1)
    pvals = []
    for i in range(200):
        f = pd.DataFrame(rng.standard_normal(panel.close.shape),
                         index=panel.close.index, columns=panel.close.columns)
        ic = f.rank(axis=1).corrwith(fwd_rank, axis=1).dropna()
        pvals.append(ic_pvalue(ic.mean(), ic.std(), len(ic)))
    survivors = sum(bh_fdr(pvals, 0.10))
    assert survivors <= 6   # generous statistical bound for q=0.10 under the null


def test_verdict_reasons():
    from alpha_factory.stats import verdict
    from alpha_factory import config as cfg
    good = dict(n_days=900, pval_pass=True, fold_sharpes=[1.0, 0.8, 1.2, 0.6],
                ic_base=0.05, ic_decay=0.03, dsr_prob=0.9)
    v, r = verdict(good, cfg)
    assert v == "SURVIVED"
    bad = dict(good, fold_sharpes=[1.0, -0.1, 1.2, 0.6])
    v, r = verdict(bad, cfg)
    assert v == "REJECTED" and "fold" in r
    fast = dict(good, ic_decay=0.001)   # R=1: dies before it can be traded slower
    v, r = verdict(fast, cfg)
    assert v == "REJECTED" and "decay" in r
    top = dict(good, ic_decay=None)     # traded at the top speed: no higher horizon to decay into
    v, r = verdict(top, cfg)
    assert v == "SURVIVED"
