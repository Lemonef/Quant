"""Robustness gauntlet stage 5: Hansen (2005) SPA test — is the best row real given the search."""
import numpy as np
import pandas as pd
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel
from alpha_factory.zoo import build_zoo, Factor


def _noise_matrix(n_days=720, n_strat=40, seed=9):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n_days, freq="D", tz="UTC")
    return pd.DataFrame(rng.normal(0.0, 0.01, (n_days, n_strat)), index=idx)


def test_spa_noise_universe_not_significant():
    from alpha_factory.robust import spa_pvalue
    p = spa_pvalue(_noise_matrix(), n_boot=300, seed=1)
    assert p > 0.10


def test_spa_detects_a_real_winner():
    from alpha_factory.robust import spa_pvalue
    m = _noise_matrix()
    m[0] = m[0] + 0.01              # daily Sharpe ~1 — unambiguous vs zero benchmark
    p = spa_pvalue(m, n_boot=300, seed=1)
    assert p < 0.05


def test_spa_seeded_deterministic():
    from alpha_factory.robust import spa_pvalue
    m = _noise_matrix()
    assert spa_pvalue(m, n_boot=200, seed=4) == spa_pvalue(m, n_boot=200, seed=4)


def test_spa_degenerate_inputs():
    from alpha_factory.robust import spa_pvalue
    assert np.isnan(spa_pvalue(_noise_matrix(n_days=20), n_boot=100, seed=1))


def test_factory_reports_run_level_spa(tmp_path):
    from alpha_factory.report import run_factory, render
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    zoo = build_zoo()[:10] + [Factor("planted", "test", "synthetic", lambda p: planted)]
    df = run_factory(panel, zoo, cfg)
    assert 0.0 <= df.attrs["spa_p"] <= 1.0
    # a planted signal this strong must register as a real winner over the search
    assert df.attrs["spa_p"] < 0.10
    md, _ = render(df, cfg, tmp_path, "TEST")
    assert "SPA" in md.read_text()
