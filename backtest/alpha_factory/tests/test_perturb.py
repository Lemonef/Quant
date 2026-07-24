"""Robustness gauntlet stage 2: lag (t+2) and price-noise perturbation of survivors."""
import numpy as np
import pandas as pd
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel
from alpha_factory.zoo import build_zoo, Factor
from alpha_factory.evaluate import ls_returns


def _planted():
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    return panel, planted


def test_ls_returns_delay_default_unchanged():
    panel, planted = _planted()
    base = ls_returns(planted, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                      cfg.BORROW_ANNUAL, cfg.DPY)
    explicit = ls_returns(planted, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                          cfg.BORROW_ANNUAL, cfg.DPY, delay=1)
    pd.testing.assert_series_equal(base, explicit)


def test_delay_two_kills_next_day_only_signal():
    # the synthetic planted score moves ONLY the next day's return: executing t+2
    # must forfeit essentially all of the edge
    panel, planted = _planted()
    base = ls_returns(planted, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                      cfg.BORROW_ANNUAL, cfg.DPY, delay=1)
    lag = ls_returns(planted, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                     cfg.BORROW_ANNUAL, cfg.DPY, delay=2)
    assert base.mean() > 0
    assert lag.mean() < 0.5 * base.mean()


def test_perturbation_stats_planted_survives_noise():
    from alpha_factory.robust import perturbation_stats
    panel, planted = _planted()
    out = perturbation_stats(lambda p: planted, panel, cfg, rebalance=1)
    assert set(out) == {"sharpe_lag", "sharpe_noise"}
    # 5bp price noise must not kill a signal_strength=0.6 planted edge
    assert out["sharpe_noise"] > 0


def test_perturbation_stats_noise_is_seeded():
    from alpha_factory.robust import perturbation_stats
    panel, planted = _planted()
    a = perturbation_stats(lambda p: planted, panel, cfg, rebalance=1)
    b = perturbation_stats(lambda p: planted, panel, cfg, rebalance=1)
    assert a == b


def test_perturb_notes():
    from alpha_factory.robust import perturb_notes
    assert perturb_notes(dict(sharpe_lag=-0.1, sharpe_noise=1.0)) == ["LAG-FRAIL"]
    assert perturb_notes(dict(sharpe_lag=1.0, sharpe_noise=0.0)) == ["NOISE-FRAIL"]
    assert perturb_notes(dict(sharpe_lag=1.0, sharpe_noise=1.0)) == []


def test_survivors_carry_perturbation_columns():
    from alpha_factory.report import run_factory
    panel, planted = _planted()
    zoo = build_zoo()[:10] + [Factor("planted", "test", "synthetic", lambda p: planted)]
    df = run_factory(panel, zoo, cfg)
    row = df[df.name == "planted"].iloc[0]
    assert row.verdict == "SURVIVED"
    assert np.isfinite(row.sharpe_lag) and np.isfinite(row.sharpe_noise)
    rej = df[df.verdict == "REJECTED"]
    assert rej.sharpe_lag.isna().all() and rej.sharpe_noise.isna().all()
