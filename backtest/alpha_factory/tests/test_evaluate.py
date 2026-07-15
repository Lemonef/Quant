import numpy as np
import pandas as pd
from alpha_factory.panel import build_synth_panel
from alpha_factory import config as cfg


def test_planted_signal_has_positive_ic_and_noise_does_not():
    from alpha_factory.evaluate import ic_stats
    panel, planted = build_synth_panel(seed=11, signal_strength=0.5)
    s = ic_stats(planted, panel.close, (1, 5))
    assert s["ic_1"] > 0.10 and s["icir_1"] > 1.0
    rng = np.random.default_rng(0)
    noise = pd.DataFrame(rng.standard_normal(panel.close.shape),
                         index=panel.close.index, columns=panel.close.columns)
    sn = ic_stats(noise, panel.close, (1,))
    assert abs(sn["ic_1"]) < 0.05


def test_lookahead_factor_is_neutralized_by_shift():
    """A cheating factor (= same-day return) must show ~no NET edge once execution is shift(1)."""
    from alpha_factory.evaluate import ls_returns
    panel, _ = build_synth_panel(seed=5, signal_strength=0.0)
    cheat = panel.ret  # knows today's return "in advance"
    lsr = ls_returns(cheat, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE, cfg.BORROW_ANNUAL, cfg.DPY)
    sh = lsr.mean() / lsr.std() * np.sqrt(cfg.DPY)
    assert sh < 0.5  # no edge survives the one-day execution lag on iid noise


def test_planted_signal_makes_money_net_of_costs():
    from alpha_factory.evaluate import ls_returns
    panel, planted = build_synth_panel(seed=11, signal_strength=0.5)
    lsr = ls_returns(planted, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE, cfg.BORROW_ANNUAL, cfg.DPY)
    assert lsr.mean() / lsr.std() * np.sqrt(cfg.DPY) > 1.0


def _weights(factor, k_frac):
    """Mirror ls_returns' weight construction (the pre-hold w), for use as a test oracle."""
    n = factor.count(axis=1)
    k = np.maximum(2, (n * k_frac).astype(int))
    rk = factor.rank(axis=1, ascending=False)
    wl = rk.le(k, axis=0).astype(float)
    ws = rk.gt((n - k), axis=0).astype(float)
    wl = wl.div(wl.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    ws = ws.div(ws.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    return wl - ws


def test_rebalance_holds_weights_between_rebalances():
    """rebalance=5: with a factor whose daily ranks change every day, weights are re-ranked
    only every 5th row and held in between, so turnover (and its cost) is zero on hold days."""
    from alpha_factory.evaluate import ls_returns
    panel, _ = build_synth_panel(seed=3, signal_strength=0.0)
    rng = np.random.default_rng(9)
    fac = pd.DataFrame(rng.standard_normal(panel.close.shape),
                       index=panel.close.index, columns=panel.close.columns)  # ranks reshuffle daily
    R = 5
    w = _weights(fac, cfg.K_FRAC)
    mask = pd.Series(np.arange(len(w)) % R == 0, index=w.index)
    held = w.where(mask).ffill().fillna(0.0)
    turn = held.diff().abs().sum(axis=1).fillna(0.0)
    hold_rows = ~mask.values
    assert (turn.values[hold_rows] == 0).all()          # no trading between rebalances
    assert (turn.values[mask.values][1:] > 0).any()     # but it does trade on rebalance days
    # net on hold days equals gross-minus-borrow (turnover cost is exactly zero there)
    lsr = ls_returns(fac, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                     cfg.BORROW_ANNUAL, cfg.DPY, rebalance=R)
    gross = (held.shift(1).fillna(0.0) * panel.ret).sum(axis=1)
    ws = held.clip(upper=0.0).abs()
    borrow = ws.shift(1).fillna(0.0).sum(axis=1) * cfg.BORROW_ANNUAL / cfg.DPY
    expect_hold = (gross - borrow)[hold_rows]
    assert np.allclose(lsr.values[hold_rows], expect_hold.values)


def test_no_borrow_charged_while_held_book_is_empty():
    """Regression: a factor with a NaN warmup that straddles a rebalance grid point leaves
    the HELD book empty for a stretch while the daily re-rank is already live — those days
    must return exactly 0.0 (no positions => no P&L, borrow included)."""
    from alpha_factory.evaluate import ls_returns
    panel, _ = build_synth_panel(seed=7, signal_strength=0.0)
    rng = np.random.default_rng(2)
    fac = pd.DataFrame(rng.standard_normal(panel.close.shape),
                       index=panel.close.index, columns=panel.close.columns)
    warmup = 23                                  # deliberately not a multiple of R
    fac.iloc[:warmup] = np.nan
    R = 20
    lsr = ls_returns(fac, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE,
                     cfg.BORROW_ANNUAL, cfg.DPY, rebalance=R)
    w = _weights(fac, cfg.K_FRAC)
    mask = pd.Series(np.arange(len(w)) % R == 0, index=w.index)
    held = w.where(mask).ffill().fillna(0.0)
    exposure = held.abs().sum(axis=1)
    flat = (exposure.shift(1).fillna(0.0) == 0) & (exposure == 0)   # no positions AND no trade today
    assert flat.iloc[:warmup].any()              # scenario actually occurs
    assert (lsr[flat] == 0.0).all()              # and costs nothing (the old code charged borrow here)


def test_rebalance_one_matches_daily_and_trades_most_days():
    """rebalance=1 is the daily path: identical to the no-rebalance reference, and a
    daily-reshuffling factor incurs nonzero turnover on most days."""
    from alpha_factory.evaluate import ls_returns
    panel, _ = build_synth_panel(seed=4, signal_strength=0.0)
    rng = np.random.default_rng(8)
    fac = pd.DataFrame(rng.standard_normal(panel.close.shape),
                       index=panel.close.index, columns=panel.close.columns)
    a = ls_returns(fac, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE, cfg.BORROW_ANNUAL, cfg.DPY)
    b = ls_returns(fac, panel.ret, cfg.K_FRAC, cfg.TAKER_FEE, cfg.SLIPPAGE, cfg.BORROW_ANNUAL, cfg.DPY, rebalance=1)
    assert a.equals(b)                                   # default is exactly rebalance=1
    turn = _weights(fac, cfg.K_FRAC).diff().abs().sum(axis=1).fillna(0.0)
    assert (turn > 0).mean() > 0.9                       # trades nearly every day


def test_purged_folds_disjoint_with_embargo():
    from alpha_factory.evaluate import purged_folds
    idx = pd.date_range("2023-01-01", periods=400, freq="D", tz="UTC")
    folds = purged_folds(idx, 4, 10)
    assert len(folds) == 4
    for a, b in zip(folds, folds[1:]):
        assert (b[0] - a[-1]).days > 10   # embargo gap
    assert sum(len(f) for f in folds) <= 400 - 3 * 10
