import numpy as np
import pandas as pd


def test_scaffold_imports():
    import alpha_factory.config as cfg
    assert cfg.FDR_Q == 0.10 and cfg.N_FOLDS == 4


def toy():
    idx = pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC")
    return pd.DataFrame({"A": [1., 2, 3, 4, 5, 6], "B": [6., 5, 4, 3, 2, 1]}, index=idx)


def test_ts_ops():
    from alpha_factory import ops
    df = toy()
    assert ops.ts_mean(df, 2).iloc[-1, 0] == 5.5           # mean of 5,6
    assert ops.delta(df, 3).iloc[-1, 0] == 3.0             # 6-3
    assert ops.ts_rank(df, 3).iloc[-1, 0] == 1.0           # 6 is max of (4,5,6)
    w = np.array([1, 2, 3]) / 6                            # decay weights, newest heaviest
    assert abs(ops.decay(df, 3).iloc[-1, 0] - (4*w[0] + 5*w[1] + 6*w[2])) < 1e-9


def test_cs_ops():
    from alpha_factory import ops
    df = toy()
    r = ops.cs_rank(df)
    assert r.iloc[-1, 0] == 1.0 and r.iloc[-1, 1] == 0.0   # A top, B bottom
    z = ops.cs_z(df)
    assert abs(z.iloc[-1].mean()) < 1e-12                  # zero-mean rows


def test_ts_corr_sign():
    from alpha_factory import ops
    df = toy()
    c = ops.ts_corr(df[["A"]], df[["B"]].rename(columns={"B": "A"}), 4)
    assert c.iloc[-1, 0] < -0.99                           # perfectly anti-correlated
