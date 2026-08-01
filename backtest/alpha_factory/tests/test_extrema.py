"""PM-QUANT Track D: turning-point extrema — labels, confirmation lag, kill test."""
import numpy as np
import pandas as pd
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel


def _vee():
    """Deterministic series: down to an obvious low at i=30, up to a high at i=70,
    then down again. Vol is tiny vs the swings, so the zigzag must find both."""
    idx = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    px = np.concatenate([np.linspace(100, 60, 31),          # low at index 30
                         np.linspace(60, 140, 40)[1:],      # high at index 69
                         np.linspace(140, 100, 31)[1:]])
    return pd.Series(px, index=idx)


def test_zigzag_finds_the_obvious_extremes():
    from alpha_factory.extrema import zigzag_extrema
    s = _vee()
    ext = zigzag_extrema(s, cfg.EXTREMA_K)
    lows = ext[ext.kind == "low"]
    highs = ext[ext.kind == "high"]
    assert len(lows) >= 1 and len(highs) >= 1
    assert lows.iloc[0].name == s.index[30]
    assert s.index[69] in highs.index          # the real peak (start-boundary artifact high may precede it)
    # confirmation strictly AFTER the extremum — the lag the embargo must cover
    assert (ext.confirmed > ext.index).all()


def test_near_low_labels_window():
    from alpha_factory.extrema import zigzag_extrema, near_labels
    s = _vee()
    ext = zigzag_extrema(s, cfg.EXTREMA_K)
    y = near_labels(s.index, ext, "low", cfg.EXTREMA_Z)
    lo = s.index.get_loc(ext[ext.kind == "low"].index[0])
    assert y.iloc[lo]                                       # the low itself
    assert y.iloc[lo - cfg.EXTREMA_Z] and y.iloc[lo + cfg.EXTREMA_Z]
    assert not y.iloc[lo - cfg.EXTREMA_Z - 1] and not y.iloc[lo + cfg.EXTREMA_Z + 1]


def test_track_d_kill_reports_and_fails_on_noise():
    from alpha_factory.extrema import track_d_kill
    panel, _ = build_synth_panel(seed=37, n_days=1500, n_coins=8)
    out = track_d_kill(panel, cfg)
    for k in ("n_oos_days", "low_base_rate", "low_precision", "low_z",
              "overlay_sharpe", "hold_sharpe", "passes"):
        assert k in out, k
    assert isinstance(out["passes"], bool)
    # a GBM anchor has no predictable turning points net of costs
    assert out["passes"] == False  # noqa: E712


def _swingy(n=4000, seed=13, amp=0.08, period=60):
    """Sine-swing price with noise: real intermediate swings a flip machine should ride."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    t = np.arange(n)
    px = 100 * np.exp(amp * np.sin(2 * np.pi * t / period) + np.cumsum(rng.normal(0, 0.002, n)))
    return pd.Series(px, index=idx)


def test_bars_per_year_is_self_measured():
    from alpha_factory.extrema import bars_per_year
    hourly = _swingy(100)
    assert abs(bars_per_year(hourly.index) - 8760) < 30
    daily = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    assert abs(bars_per_year(daily) - 365) < 2


def test_flip_overlay_state_machine():
    from alpha_factory.extrema import flip_positions
    idx = pd.date_range("2024-01-01", periods=6, freq="h", tz="UTC")
    p_low = pd.Series([0.9, 0.2, 0.1, 0.2, 0.9, 0.2], index=idx)
    p_high = pd.Series([0.1, 0.2, 0.9, 0.2, 0.1, 0.2], index=idx)
    pos = flip_positions(p_low, p_high)
    assert list(pos) == [1, 1, -1, -1, 1, 1]      # long from low-call, flip short at high-call


def test_track_d2_kill_on_swingy_series_passes_and_noise_fails():
    from alpha_factory.extrema import track_d2_kill
    swing = _swingy()
    out = track_d2_kill(swing, cfg)
    for k in ("n_oos_bars", "low_z", "flip_sharpe", "flip_sharpe_lo", "hold_sharpe", "passes"):
        assert k in out, k
    # engineered swings are the it-works fixture: the machine must catch them
    assert out["passes"] == True  # noqa: E712
    rng = np.random.default_rng(41)
    idx = pd.date_range("2024-01-01", periods=4000, freq="h", tz="UTC")
    gbm = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.004, 4000))), index=idx)
    out2 = track_d2_kill(gbm, cfg)
    assert out2["passes"] == False  # noqa: E712
