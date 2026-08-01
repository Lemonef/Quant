"""Perfect-model Track A: meta-labeling the rsi2dip sleeve's entries.
Kill test: does a classifier's bet/no-bet beat the sleeve's base win rate OOS?"""
import numpy as np
import pandas as pd
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel


def test_entry_events_are_dip_in_uptrend_transitions():
    from alpha_factory.meta import entry_events
    from alpha_factory import ops
    panel, _ = build_synth_panel(seed=7, n_days=900)
    ev = entry_events(panel)
    assert len(ev) > 0
    ma200 = panel.close.rolling(200).mean()
    r2 = ops.rsi(panel.close, 2)
    for t, coin in ev[:20]:
        assert panel.close.at[t, coin] > ma200.at[t, coin]       # uptrend at entry
        assert r2.at[t, coin] < 10                                # dip at entry
    # transitions only: no event on consecutive days for the same coin
    by_coin = {}
    for t, coin in ev:
        by_coin.setdefault(coin, []).append(t)
    for coin, ts in by_coin.items():
        d = pd.Series(sorted(ts)).diff().dropna()
        assert (d > pd.Timedelta(days=1)).all()


def test_labels_follow_sleeve_exit_rule():
    from alpha_factory.meta import entry_events, label_events
    panel, _ = build_synth_panel(seed=7, n_days=900)
    ev = entry_events(panel)
    lab = label_events(ev, panel, cfg)
    assert set(lab.columns) >= {"ret", "win", "hold_days"}
    assert len(lab) == len(ev)
    assert lab.hold_days.max() <= cfg.META_TIMEOUT_D
    assert lab.win.isin([True, False]).all()


def test_features_are_causal():
    from alpha_factory.meta import entry_events, event_features
    from alpha_factory.panel import Panel
    panel, _ = build_synth_panel(seed=7, n_days=900)
    ev = entry_events(panel)
    X = event_features(ev, panel)
    assert len(X) == len(ev) and X.shape[1] >= 6
    # truncating the future must not change features of past events
    t_cut = 700
    trunc = Panel(panel.open.iloc[:t_cut], panel.high.iloc[:t_cut],
                  panel.low.iloc[:t_cut], panel.close.iloc[:t_cut],
                  panel.volume.iloc[:t_cut], panel.funding.iloc[:t_cut])
    ev_past = [e for e in ev if e[0] < panel.close.index[t_cut - 1]]
    X2 = event_features(ev_past, trunc)
    pd.testing.assert_frame_equal(X.iloc[:len(ev_past)], X2, atol=1e-10, check_exact=False)


def test_kill_test_reports_the_preregistered_numbers():
    from alpha_factory.meta import kill_test
    # big enough that walk-forward folds clear META_MIN_TRAIN_EVENTS
    panel, _ = build_synth_panel(seed=7, n_days=1500, n_coins=20)
    out = kill_test(panel, cfg)
    for k in ("n_events", "n_oos", "base_win_rate", "bet_precision",
              "bet_fraction", "delta_expectancy_r", "passes"):
        assert k in out, k
    assert 0.0 <= out["base_win_rate"] <= 1.0
    assert isinstance(out["passes"], bool)
    # pure GBM synth has no learnable edge — the kill test must NOT pass on noise
    assert out["passes"] == False  # noqa: E712
