"""Robustness gauntlet stage 4: CSCV probability of backtest overfitting (Bailey et al.)."""
import numpy as np
import pandas as pd
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel
from alpha_factory.zoo import build_zoo, Factor


def _noise_matrix(n_days=720, n_strat=50, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n_days, freq="D", tz="UTC")
    return pd.DataFrame(rng.normal(0.0, 0.01, (n_days, n_strat)), index=idx)


def test_pbo_noise_universe_is_coinflip():
    from alpha_factory.robust import pbo_cscv
    # among pure-noise strategies the IS winner has no edge OOS: its OOS rank is
    # uniform, so PBO concentrates near 0.5
    pbo = pbo_cscv(_noise_matrix(), cfg.CSCV_BLOCKS)
    assert 0.25 < pbo < 0.75


def test_pbo_low_when_one_strategy_is_genuinely_best():
    from alpha_factory.robust import pbo_cscv
    m = _noise_matrix()
    m[0] = m[0] + 0.01          # daily Sharpe ~1: dominates IS and OOS alike
    pbo = pbo_cscv(m, cfg.CSCV_BLOCKS)
    assert pbo < 0.2


def test_pbo_rejects_odd_block_count():
    import pytest
    from alpha_factory.robust import pbo_cscv
    with pytest.raises(ValueError):
        pbo_cscv(_noise_matrix(), 11)


def test_pbo_degenerate_inputs():
    from alpha_factory.robust import pbo_cscv
    assert np.isnan(pbo_cscv(_noise_matrix(n_strat=1), cfg.CSCV_BLOCKS))
    assert np.isnan(pbo_cscv(_noise_matrix(n_days=cfg.CSCV_BLOCKS - 1), cfg.CSCV_BLOCKS))


def test_factory_reports_run_level_pbo(tmp_path):
    from alpha_factory.report import run_factory, render
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    zoo = build_zoo()[:10] + [Factor("planted", "test", "synthetic", lambda p: planted)]
    df = run_factory(panel, zoo, cfg)
    assert 0.0 <= df.attrs["pbo"] <= 1.0
    md, _ = render(df, cfg, tmp_path, "TEST")
    assert "PBO" in md.read_text()
