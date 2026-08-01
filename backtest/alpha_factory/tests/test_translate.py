"""Track B: turnover-aware translation of proven-but-untradable scores."""
import numpy as np
import pandas as pd
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel
from alpha_factory.evaluate import ls_returns


def _panel_and_scores(seed=11, strength=0.6):
    panel, planted = build_synth_panel(seed=seed, signal_strength=strength)
    return panel, planted


def test_smoothing_cuts_turnover():
    from alpha_factory.translate import smooth, turnover_of
    panel, score = _panel_and_scores()
    raw_t = turnover_of(score, cfg.K_FRAC)
    sm_t = turnover_of(smooth(score, cfg.SMOOTH_HALFLIVES[-1]), cfg.K_FRAC)
    assert sm_t < 0.5 * raw_t


def test_banded_positions_hold_until_exit_band():
    from alpha_factory.translate import banded_weights
    idx = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")
    cols = list("ABCDE")
    # A starts on top, then decays to rank 3 of 5 — with k=1 and exit multiple 3
    # it must STAY long through rank 3 and drop only at rank 4
    f = pd.DataFrame([[5, 4, 3, 2, 1],
                      [3, 5, 4, 2, 1],      # A rank 3: inside exit band, hold
                      [2, 5, 4, 3, 1],      # A rank 4: outside, drop; B is the new top
                      [2, 5, 4, 3, 1]],
                     index=idx, columns=cols, dtype=float)
    w = banded_weights(f, k_frac=0.2, exit_mult=cfg.BAND_EXIT_MULT)
    assert w.at[idx[0], "A"] > 0
    assert w.at[idx[1], "A"] > 0          # held inside the band
    assert w.at[idx[2], "A"] == 0.0       # dropped past the exit band
    assert w.at[idx[2], "B"] > 0


def test_banded_turnover_below_raw():
    from alpha_factory.translate import banded_weights
    panel, score = _panel_and_scores()
    w = banded_weights(score, cfg.K_FRAC, cfg.BAND_EXIT_MULT)
    band_turn = float(w.diff().abs().sum(axis=1).mean())
    # like-for-like raw L/S book (top-K minus bottom-K, re-ranked daily)
    rk = score.rank(axis=1, ascending=False)
    n = score.count(axis=1)
    k = np.maximum(2, (n * cfg.K_FRAC).astype(int))
    wl = rk.le(k, axis=0).astype(float)
    ws = rk.gt(n - k, axis=0).astype(float)
    wl = wl.div(wl.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    ws = ws.div(ws.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    raw_turn = float((wl - ws).diff().abs().sum(axis=1).mean())
    assert band_turn < raw_turn


def test_track_b_kill_reports_variants_and_fails_on_noise():
    from alpha_factory.translate import track_b_kill
    panel, _ = build_synth_panel(seed=29, signal_strength=0.0)
    rng = np.random.default_rng(4)
    noise_score = pd.DataFrame(rng.standard_normal(panel.close.shape),
                               index=panel.close.index, columns=panel.close.columns)
    out = track_b_kill(noise_score, panel, cfg)
    assert set(out["variants"]) == {"raw", "smooth_5", "smooth_20", "band", "smooth_20_band"}
    for v, r in out["variants"].items():
        assert set(r) >= {"net_sharpe", "fold_sharpes", "passes"}
    assert out["n_trials_added"] == 4                  # raw is reference, not a trial
    assert not any(r["passes"] for r in out["variants"].values())
