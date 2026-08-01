"""PM-QUANT Track C: learned regime gate over the incumbent book."""
import numpy as np
import pandas as pd
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel, Panel


def test_regime_features_are_causal_and_daily():
    from alpha_factory.regime import regime_features
    panel, _ = build_synth_panel(seed=7, n_days=900)
    X = regime_features(panel)
    assert X.index.equals(panel.close.index) and X.shape[1] >= 6
    cut = 700
    trunc = Panel(panel.open.iloc[:cut], panel.high.iloc[:cut], panel.low.iloc[:cut],
                  panel.close.iloc[:cut], panel.volume.iloc[:cut], panel.funding.iloc[:cut])
    X2 = regime_features(trunc)
    pd.testing.assert_frame_equal(X.iloc[:cut], X2, atol=1e-10, check_exact=False)


def test_gate_of_ones_reproduces_ungated_book():
    from alpha_factory.regime import apply_gate, book_series
    panel, _ = build_synth_panel(seed=7, n_days=600)
    book = book_series(panel, cfg)
    gate = pd.Series(1.0, index=book.index)
    gated = apply_gate(book, gate, cfg)
    pd.testing.assert_series_equal(gated, book)          # always-on gate = no switches, no cost


def test_gate_switch_pays_cost():
    from alpha_factory.regime import apply_gate
    idx = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    book = pd.Series(0.01, index=idx)
    gate = pd.Series([1, 1, 0, 0, 1, 1], index=idx, dtype=float)
    gated = apply_gate(book, gate, cfg)
    assert gated.iloc[1] == book.iloc[1]                  # on, no switch
    assert gated.iloc[3] == 0.0                           # flat day earns nothing
    # switch days are charged fee+slip on the moved notional
    assert abs(gated.iloc[2] - (book.iloc[2] - (cfg.TAKER_FEE + cfg.SLIPPAGE))) < 1e-12
    assert gated.iloc[4] < book.iloc[4]


def test_track_c_kill_reports_and_fails_on_noise():
    from alpha_factory.regime import track_c_kill
    panel, _ = build_synth_panel(seed=31, n_days=1200, n_coins=12)
    out = track_c_kill(panel, cfg)
    for k in ("ungated_sharpe", "gated_sharpe", "ungated_maxdd", "gated_maxdd",
              "n_oos_days", "flat_fraction", "passes"):
        assert k in out, k
    assert isinstance(out["passes"], bool)
    # GBM noise: the gate cannot beat the ungated book both on Sharpe AND DD
    assert out["passes"] == False  # noqa: E712
