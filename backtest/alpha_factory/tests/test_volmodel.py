"""Horse race: implied DVOL versus backward-looking volatility forecasts."""
import numpy as np
import pandas as pd

from alpha_factory import config as cfg


def _regime_fixture(n=500):
    """At close t the option market observes the regime driving t+1..t+H."""
    rng = np.random.default_rng(7)
    idx = pd.date_range("2021-04-01", periods=n, freq="D", tz="UTC")
    regime = np.where((np.arange(n) // 50) % 2, 0.055, 0.008)
    shocks = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    shocks /= shocks.std(ddof=1)
    ret = np.zeros(n)
    ret[1:] = regime[:-1] * np.resize(shocks, n - 1)
    close = pd.Series(100 * np.exp(np.cumsum(ret)), index=idx, name="BTCUSDT")
    # The hidden state is observed by the option market at t, with small observation
    # noise, and quoted in Deribit's percentage annualized units.
    dvol = pd.Series(100 * regime * np.sqrt(cfg.DPY) *
                     (1 + 0.02 * rng.standard_normal(n)), index=idx)
    return close, dvol.clip(lower=0.001)


def test_qlike_matches_hand_computation():
    from alpha_factory.volmodel import qlike
    actual = pd.Series([0.2, 0.4])
    forecast = pd.Series([0.1, 0.5])
    expected = np.mean((actual ** 2) / (forecast ** 2) + np.log(forecast ** 2))
    assert abs(qlike(actual, forecast) - expected) < 1e-12


def test_implied_analog_wins_qlike_on_hidden_regimes():
    from alpha_factory.volmodel import forecast_frame, score_forecasts
    close, dvol = _regime_fixture()
    frame = forecast_frame(close, dvol, cfg)
    scores = score_forecasts(frame, cfg)
    assert scores["oos_qlike"]["dvol"] < scores["oos_qlike"]["hist20"]
    assert scores["oos_qlike"]["dvol"] < scores["oos_qlike"]["ewma"]


def test_forecasts_are_causal_under_truncation():
    from alpha_factory.volmodel import forecast_frame
    close, dvol = _regime_fixture()
    cut = 350
    full = forecast_frame(close, dvol, cfg)
    trunc = forecast_frame(close.iloc[:cut], dvol.iloc[:cut], cfg)
    # Targets use the future and are intentionally excluded; every forecast at t is unchanged.
    pd.testing.assert_frame_equal(
        full.iloc[:cut][["hist20", "ewma", "dvol", "blend"]],
        trunc[["hist20", "ewma", "dvol", "blend"]],
    )


def test_constant_returns_are_handled_without_infinities():
    from alpha_factory.volmodel import forecast_frame, qlike, score_forecasts
    idx = pd.date_range("2022-01-01", periods=100, freq="D", tz="UTC")
    close = pd.Series(100.0, index=idx, name="BTCUSDT")
    dvol = pd.Series(0.5, index=idx)
    frame = forecast_frame(close, dvol, cfg)
    scores = score_forecasts(frame, cfg)
    assert np.isfinite(qlike(pd.Series([0.0]), pd.Series([0.0])))
    for metric in ("oos_qlike", "oos_logvol_mse"):
        assert all(np.isfinite(v) for v in scores[metric].values())
