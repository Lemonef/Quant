"""Robustness gauntlet stage 1: circular block-bootstrap CIs on Sharpe + worst-plausible DD."""
import numpy as np
import pandas as pd
import pytest
from alpha_factory import config as cfg
from alpha_factory.robust import bootstrap_stats


def _series(mu, sigma, n=1000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC")
    return pd.Series(rng.normal(mu, sigma, n), index=idx)


def test_ci_brackets_point_sharpe():
    s = _series(0.001, 0.01)
    out = bootstrap_stats(s, cfg.DPY, n_boot=500, ci=0.90, seed=1, dd_q=cfg.BOOT_DD_Q)
    point = s.mean() / s.std() * np.sqrt(cfg.DPY)
    assert out["sharpe_lo"] < point < out["sharpe_hi"]


def test_strong_edge_ci_excludes_zero():
    s = _series(0.004, 0.01)  # daily Sharpe 0.4 — unambiguous edge
    out = bootstrap_stats(s, cfg.DPY, n_boot=500, ci=0.90, seed=1, dd_q=cfg.BOOT_DD_Q)
    assert out["sharpe_lo"] > 0


def test_pure_noise_ci_spans_zero():
    s = _series(0.0, 0.01)
    out = bootstrap_stats(s, cfg.DPY, n_boot=500, ci=0.90, seed=1, dd_q=cfg.BOOT_DD_Q)
    assert out["sharpe_lo"] < 0 < out["sharpe_hi"]


def test_seed_reproducible():
    s = _series(0.001, 0.01)
    a = bootstrap_stats(s, cfg.DPY, n_boot=200, ci=0.90, seed=7, dd_q=cfg.BOOT_DD_Q)
    b = bootstrap_stats(s, cfg.DPY, n_boot=200, ci=0.90, seed=7, dd_q=cfg.BOOT_DD_Q)
    assert a == b


def test_maxdd_p95_positive_and_plausible():
    s = _series(0.0005, 0.02)
    out = bootstrap_stats(s, cfg.DPY, n_boot=500, ci=0.90, seed=1, dd_q=cfg.BOOT_DD_Q)
    # DD reported as a positive fraction; the 95th-percentile path DD must be at
    # least as deep as the median path DD, and both nonzero for a noisy series
    assert out["maxdd_p95"] >= out["maxdd_med"] > 0


def test_degenerate_constant_series():
    idx = pd.date_range("2023-01-01", periods=300, freq="D", tz="UTC")
    s = pd.Series(0.0, index=idx)
    out = bootstrap_stats(s, cfg.DPY, n_boot=100, ci=0.90, seed=1, dd_q=cfg.BOOT_DD_Q)
    assert out["sharpe_lo"] == out["sharpe_hi"] == 0.0
    assert out["maxdd_p95"] == 0.0


def test_config_tokens_exist():
    assert cfg.BOOT_N >= 100
    assert 0.5 < cfg.BOOT_CI < 1.0


def test_fragile_iff_ci_lower_bound_nonpositive():
    from alpha_factory.robust import is_fragile
    assert is_fragile(dict(sharpe_lo=-0.1, sharpe_hi=1.0))
    assert is_fragile(dict(sharpe_lo=0.0, sharpe_hi=1.0))
    assert not is_fragile(dict(sharpe_lo=0.2, sharpe_hi=1.5))


def test_survivors_carry_bootstrap_columns():
    from alpha_factory.panel import build_synth_panel
    from alpha_factory.zoo import build_zoo, Factor
    from alpha_factory.report import run_factory
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    zoo = build_zoo()[:10] + [Factor("planted", "test", "synthetic", lambda p: planted)]
    df = run_factory(panel, zoo, cfg)
    row = df[df.name == "planted"].iloc[0]
    assert row.verdict == "SURVIVED"
    assert row.sharpe_lo < row.sharpe_hi          # real interval, not a point
    assert row.maxdd_p95 > 0
    # a strong planted signal must not read as fragile
    assert "FRAGILE" not in row.reason
    # rejected rows are not bootstrapped — columns stay NaN
    rej = df[df.verdict == "REJECTED"]
    assert rej.sharpe_lo.isna().all() and rej.maxdd_p95.isna().all()


def test_render_shows_bootstrap_interval(tmp_path):
    from alpha_factory.panel import build_synth_panel
    from alpha_factory.zoo import build_zoo, Factor
    from alpha_factory.report import run_factory, render
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    zoo = build_zoo()[:10] + [Factor("planted", "test", "synthetic", lambda p: planted)]
    df = run_factory(panel, zoo, cfg)
    md, _ = render(df, cfg, tmp_path, "TEST")
    text = md.read_text()
    assert "Sharpe CI" in text and "DD p95" in text
