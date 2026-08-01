"""ML ranker: GBM on the factor panel, expanding-window purged walk-forward.
The ranker's OOS predictions are just another factor candidate — same gauntlet."""
import numpy as np
import pandas as pd
from alpha_factory import config as cfg
from alpha_factory.panel import build_synth_panel
from alpha_factory.zoo import Factor


def _tiny_zoo(planted):
    """Planted signal + noise features — enough for the GBM to find the real one."""
    rng = np.random.default_rng(2)
    noise = [pd.DataFrame(rng.standard_normal(planted.shape), index=planted.index,
                          columns=planted.columns) for _ in range(4)]
    return ([Factor("planted_sig", "test", "synthetic", lambda p, s=planted: s)] +
            [Factor(f"noise_{i}", "test", "synthetic", lambda p, x=x: x)
             for i, x in enumerate(noise)])


def test_dataset_target_is_forward_rank_and_tail_is_nan():
    from alpha_factory.ranker import build_dataset
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    X, y = build_dataset(panel, _tiny_zoo(planted), horizon=1)
    days = X.index.get_level_values(0)
    last_day = panel.close.index[-1]
    # no target can exist for the final `horizon` days
    assert y[days == last_day].isna().all()
    # target = cross-sectional rank of the NEXT-day return, in [0, 1]
    t = panel.close.index[100]
    fwd = panel.close.pct_change(1).shift(-1).loc[t]
    expect = fwd.rank(pct=True)
    got = y.xs(t, level=0)
    pd.testing.assert_series_equal(got.sort_index(), expect.sort_index(),
                                   check_names=False)


def test_first_fold_has_no_predictions():
    from alpha_factory.ranker import ranker_factor
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    pred = ranker_factor(panel, _tiny_zoo(planted), cfg, horizon=1)
    folds_len = len(panel.close.index) // cfg.N_FOLDS
    assert pred.iloc[:folds_len].isna().all().all()      # nothing to train on yet
    assert pred.notna().any().any()                      # later folds are populated


def test_ranker_recovers_planted_signal_oos():
    from alpha_factory.ranker import ranker_factor
    from alpha_factory.evaluate import daily_ic
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    pred = ranker_factor(panel, _tiny_zoo(planted), cfg, horizon=1)
    fwd = panel.close.pct_change(1).shift(-1)
    ic = daily_ic(pred, fwd).dropna()
    assert ic.mean() > 0.05                              # OOS IC clearly positive


def test_ranker_no_leakage_on_pure_noise():
    from alpha_factory.ranker import ranker_factor
    from alpha_factory.evaluate import daily_ic
    panel, _ = build_synth_panel(seed=23, signal_strength=0.0)
    rng = np.random.default_rng(3)
    fake = pd.DataFrame(rng.standard_normal(panel.close.shape),
                        index=panel.close.index, columns=panel.close.columns)
    pred = ranker_factor(panel, _tiny_zoo(fake), cfg, horizon=1)
    fwd = panel.close.pct_change(1).shift(-1)
    ic = daily_ic(pred, fwd).dropna()
    # any label leakage through the fold boundaries would show up as a fat IC here
    assert abs(ic.mean()) < 0.05


def test_config_tokens_exist():
    assert cfg.ML_MAX_ITER >= 50
    assert 0 < cfg.ML_LEARNING_RATE < 1
    assert cfg.ML_MIN_TRAIN_DAYS >= 100


def test_ml_factors_one_candidate_per_horizon():
    from alpha_factory.ranker import ml_factors
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    base = _tiny_zoo(planted)
    fs = ml_factors(base, cfg)
    assert [f.name for f in fs] == [f"ml_ranker_{h}" for h in cfg.HORIZONS]
    assert all(f.family == "ml" for f in fs)


def test_ranker_judged_by_the_gauntlet():
    from alpha_factory.report import run_factory
    from alpha_factory.ranker import ranker_factor
    panel, planted = build_synth_panel(seed=11, signal_strength=0.6)
    base = _tiny_zoo(planted)
    zoo = base + [Factor("ml_ranker_1", "ml", "sklearn HistGB walk-forward",
                         lambda p: ranker_factor(p, base, cfg, 1))]
    df = run_factory(panel, zoo, cfg)
    row = df[df.name == "ml_ranker_1"].iloc[0]
    assert row.verdict in ("SURVIVED", "REJECTED")
    assert row.n_days > 0                      # predictions actually reached the scorer
