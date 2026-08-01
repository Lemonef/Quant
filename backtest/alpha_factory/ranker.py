"""ML ranker — phase-2 first ML deliverable: a gradient-boosted model over the
whole factor zoo, judged as ONE MORE factor candidate by the existing gauntlet.
Model: sklearn HistGradientBoostingRegressor (the LightGBM-class histogram GBM;
chosen over lightgbm itself because the wheel needs no host OpenMP install).
Features are per-day cross-sectional ranks of every zoo factor (scale-free,
outlier-proof); the target is the cross-sectional rank of the forward
`horizon`-day return. Training is expanding-window over the same purged folds
as the factory: predict fold i from a model fit on folds 0..i-1 with the
trailing `horizon` days dropped from the train set — a label at day t reads
returns through t+horizon, and those days would otherwise leak across the
boundary (the fold's own leading embargo handles the feature side)."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from .evaluate import purged_folds
from .zoo import Factor


def build_dataset(panel, zoo, horizon):
    """(X, y) in long form indexed (day, coin): X = cs-ranked factor values,
    y = cs-rank of the forward horizon-day return (NaN where no future exists)."""
    feats = {f.name: f.fn(panel).rank(axis=1, pct=True).stack(future_stack=True) for f in zoo}
    X = pd.DataFrame(feats)
    fwd = panel.close.pct_change(horizon).shift(-horizon)
    y = fwd.rank(axis=1, pct=True).stack(future_stack=True).reindex(X.index)
    return X, y


def ranker_factor(panel, zoo, cfg, horizon):
    """Day x coin DataFrame of OOS predictions (higher = more attractive long).
    Fold 0 and under-trained folds stay NaN — the factor's natural warmup."""
    X, y = build_dataset(panel, zoo, horizon)
    days = panel.close.index
    folds = purged_folds(days, cfg.N_FOLDS, cfg.EMBARGO_DAYS)
    pred = pd.DataFrame(np.nan, index=days, columns=panel.close.columns)
    day_level = X.index.get_level_values(0)
    for i in range(1, len(folds)):
        train_days = days[days < folds[i][0]][:-horizon]   # drop label-overlap tail
        if len(train_days) < cfg.ML_MIN_TRAIN_DAYS:
            continue
        tr = day_level.isin(train_days)
        te = day_level.isin(folds[i])
        ok = tr & y.notna().to_numpy() & X.notna().any(axis=1).to_numpy()
        if not ok.any():
            continue
        model = HistGradientBoostingRegressor(
            max_iter=cfg.ML_MAX_ITER, learning_rate=cfg.ML_LEARNING_RATE,
            max_depth=cfg.ML_MAX_DEPTH, random_state=cfg.BOOT_SEED)
        model.fit(X[ok], y[ok])
        out = pd.Series(model.predict(X[te]), index=X.index[te])
        pred.loc[folds[i]] = out.unstack().reindex(index=folds[i],
                                                   columns=pred.columns)
    return pred


def ml_factors(zoo, cfg):
    """One ranker candidate per horizon, each trained on the given zoo's features
    and judged by the factory exactly like any hand-written factor."""
    return [Factor(f"ml_ranker_{h}", "ml", "sklearn HistGB walk-forward",
                   lambda p, h=h: ranker_factor(p, zoo, cfg, h))
            for h in cfg.HORIZONS]
