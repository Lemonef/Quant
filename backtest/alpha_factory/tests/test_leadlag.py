"""Cross-asset lead-lag, TIME-SERIES form: does a reference asset's trend sign
condition the anchor's own forward return?"""
import numpy as np
import pandas as pd
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel, Panel


def _rename(panel, mapping):
    """Same column rename across every frame — the panel's frames must stay aligned."""
    return Panel(*[f.rename(columns=mapping) for f in
                   (panel.open, panel.high, panel.low, panel.close, panel.volume, panel.funding)])


def _with_ref(panel, ref):
    """Plant `ref` as the SECOND column so the first column stays the anchor."""
    cols = list(panel.close.columns)
    return _rename(panel, {cols[1]: ref})


def _planted_panel(n_days=1200, seed=11, edge=0.004, ref_period=180):
    """Panel whose ref genuinely leads the anchor: the anchor's next-day return is
    edge * sign(ref's LEADLAG_W-day trend) plus noise. The ref itself is a slow
    oscillation so its trend sign flips several times inside every purged fold."""
    panel, _ = build_synth_panel(n_days=n_days, seed=seed)
    panel = _with_ref(panel, "PAXGUSDT")
    idx = panel.close.index
    rng = np.random.default_rng(seed)
    t = np.arange(n_days)
    ref_ret = 0.01 * np.sin(2 * np.pi * t / ref_period) + rng.standard_normal(n_days) * 0.005
    ref_close = pd.Series(100 * np.cumprod(1 + ref_ret), index=idx)
    sign = np.sign(ref_close.pct_change(cfg.LEADLAG_W)).shift(1).fillna(0.0).to_numpy()
    anchor_ret = edge * sign + rng.standard_normal(n_days) * 0.02
    anchor_close = pd.Series(100 * np.cumprod(1 + anchor_ret), index=idx)
    cols = list(panel.close.columns)
    close = panel.close.copy()
    close[cols[0]] = anchor_close
    close["PAXGUSDT"] = ref_close
    return Panel(panel.open, panel.high, panel.low, close, panel.volume, panel.funding), cols[0]


def test_signals_are_causal():
    from alpha_factory.leadlag import leadlag_signals
    panel, _ = _planted_panel()
    sig = leadlag_signals(panel, cfg)
    assert list(sig.columns) == ["PAXGUSDT"] and sig.index.equals(panel.close.index)
    cut = 900
    trunc = Panel(panel.open.iloc[:cut], panel.high.iloc[:cut], panel.low.iloc[:cut],
                  panel.close.iloc[:cut], panel.volume.iloc[:cut], panel.funding.iloc[:cut])
    sig2 = leadlag_signals(trunc, cfg)
    pd.testing.assert_frame_equal(sig.iloc[:cut], sig2, atol=1e-10, check_exact=False)


def test_planted_leadlag_passes():
    from alpha_factory.leadlag import leadlag_kill
    panel, anchor = _planted_panel()
    out = leadlag_kill(panel, cfg)
    assert out["anchor"] == anchor
    assert out["refs_tested"] == ["PAXGUSDT"] and out["refs_missing"] == ["EURUSDT"]
    assert len(out["tests"]) == len(cfg.LEADLAG_HORIZONS)
    for r in out["tests"]:
        for k in ("ref", "horizon", "n_pos", "n_neg", "mean_pos", "mean_neg", "diff", "t",
                  "fold_signs", "folds_agree", "favorable_sign", "overlay_sharpe",
                  "hold_sharpe", "n_oos_days", "passes"):
            assert k in r, k
    one = [r for r in out["tests"] if r["horizon"] == 1][0]
    assert one["diff"] > 0 and one["t"] >= cfg.LEADLAG_T_MIN
    assert one["folds_agree"] and one["favorable_sign"] == 1.0
    assert one["overlay_sharpe"] > one["hold_sharpe"]
    assert one["passes"] is True
    assert out["passes"] is True


def test_pure_noise_fails():
    from alpha_factory.leadlag import leadlag_kill
    panel, _ = build_synth_panel(seed=31, n_days=1200, n_coins=12)
    out = leadlag_kill(_with_ref(panel, "PAXGUSDT"), cfg)
    assert out["refs_tested"] == ["PAXGUSDT"]
    # independent GBM: no ref trend sign can clear t, fold agreement AND the overlay
    assert all(r["passes"] is False for r in out["tests"])
    assert out["passes"] is False


def test_missing_refs_are_skipped_gracefully():
    from alpha_factory.leadlag import leadlag_kill
    panel, _ = build_synth_panel(seed=7, n_days=800)
    out = leadlag_kill(panel, cfg)
    assert out["refs_tested"] == [] and out["refs_missing"] == list(("PAXGUSDT", "EURUSDT"))
    assert out["tests"] == [] and out["passes"] is False


def test_overlay_charges_a_flip_and_holds_favorable_days():
    from alpha_factory.leadlag import overlay_returns
    idx = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    ret = pd.Series(0.01, index=idx)
    sig = pd.Series([1.0, 1.0, -1.0, -1.0, 1.0, 1.0], index=idx)
    ov = overlay_returns(ret, sig, 1.0, cfg)
    assert ov.iloc[1] == ret.iloc[1]                       # held long, no flip
    assert ov.iloc[3] == 0.0                               # flat day earns nothing
    assert abs(ov.iloc[2] - (ret.iloc[2] - (cfg.TAKER_FEE + cfg.SLIPPAGE))) < 1e-12
    assert ov.iloc[4] < ret.iloc[4]                        # re-entry pays the flip


def test_diff_means_t_applies_the_overlap_correction():
    from alpha_factory.leadlag import diff_means_t
    idx = pd.date_range("2024-01-01", periods=200, freq="D", tz="UTC")
    sig = pd.Series(np.where(np.arange(200) % 2 == 0, 1.0, -1.0), index=idx)
    # within-group spread (both signs see both wiggles) so the pooled SE is non-zero
    y = pd.Series(np.where(np.arange(200) % 2 == 0, 0.02, -0.02), index=idx) \
        + pd.Series(np.tile([0.01, 0.005, -0.01, -0.005], 50), index=idx)
    t1 = diff_means_t(y, sig, 1)["t"]
    t5 = diff_means_t(y, sig, 5)["t"]
    assert t1 > 0 and abs(t5 - t1 / np.sqrt(5)) < 0.2 * t1  # n_eff = n // h shrinks t by ~sqrt(h)
