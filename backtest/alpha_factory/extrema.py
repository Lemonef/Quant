"""PM-QUANT Track D — turning-point extrema: the owner's direct ask ("long near
low / short near high of every move"). Swing lows/highs come from a zigzag
whose reversal threshold derives from realized vol (EXTREMA_K x vol20 — swings
must clear noise, no fixed-percent magic number). An extremum is only CONFIRMED
once price has traveled the threshold away from it; every label carries its
confirmation date, and training discards samples not yet confirmed at the
train cutoff — hindsight labels never leak. Kill test is two-legged (both must
pass): near-low precision beats base by >= META_Z standard errors, AND a toy
long-at-predicted-low / exit-at-predicted-high overlay beats buy-and-hold net
of costs. Either leg failing kills the track."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from .regime import regime_features


def zigzag_extrema(series, k):
    """Confirmed swing extrema of a price series. Reversal threshold at time t =
    k x vol20_t (fraction of price). Returns a DataFrame indexed by extremum
    date with columns kind ('low'/'high') and confirmed (the date the reversal
    cleared the threshold)."""
    s = series.dropna()
    vol = s.pct_change().rolling(20).std().bfill().fillna(0.0)
    rows = []
    ext_i, ext_p = 0, float(s.iloc[0])
    direction = 0                       # +1 hunting a high, -1 hunting a low
    for i in range(1, len(s)):
        p = float(s.iloc[i])
        thr = k * float(vol.iloc[i]) * ext_p
        if direction >= 0:
            if p > ext_p:
                ext_i, ext_p = i, p
            if direction == 0 and p < ext_p - thr:
                direction = -1; ext_i, ext_p = (ext_i, ext_p)
                rows.append((s.index[ext_i], "high", s.index[i])); ext_i, ext_p = i, p
            elif direction > 0 and p < ext_p - thr:
                rows.append((s.index[ext_i], "high", s.index[i]))
                direction = -1; ext_i, ext_p = i, p
        if direction <= 0:
            if p < ext_p:
                ext_i, ext_p = i, p
            if direction == 0 and p > ext_p + thr:
                direction = 1
                rows.append((s.index[ext_i], "low", s.index[i])); ext_i, ext_p = i, p
            elif direction < 0 and p > ext_p + thr:
                rows.append((s.index[ext_i], "low", s.index[i]))
                direction = 1; ext_i, ext_p = i, p
    out = pd.DataFrame(rows, columns=["date", "kind", "confirmed"]).set_index("date")
    return out[~out.index.duplicated(keep="first")]


def near_labels(index, ext, kind, z):
    """Boolean: day is within z days (either side) of a confirmed `kind` extremum."""
    y = pd.Series(False, index=index)
    pos = {d: i for i, d in enumerate(index)}
    for d in ext[ext.kind == kind].index:
        if d in pos:
            i = pos[d]
            y.iloc[max(0, i - z):i + z + 1] = True
    return y


def track_d_kill(panel, cfg):
    """Anchor-series extrema classifier + toy overlay, walk-forward."""
    px = panel.close["BTCUSDT"] if "BTCUSDT" in panel.close.columns else panel.close.iloc[:, 0]
    ext = zigzag_extrema(px, cfg.EXTREMA_K)
    X = regime_features(panel)
    stretch = pd.DataFrame({
        "dist_low63": px / px.rolling(63).min() - 1,
        "dist_high63": px / px.rolling(63).max() - 1,
        "downrun": (px.pct_change() < 0).astype(float)
                   .groupby((px.pct_change() >= 0).cumsum()).cumsum(),
        "volvol": px.pct_change().rolling(5).std().rolling(20).std(),
    })
    X = pd.concat([X, stretch], axis=1)
    y_low = near_labels(px.index, ext, "low", cfg.EXTREMA_Z)
    y_high = near_labels(px.index, ext, "high", cfg.EXTREMA_Z)
    conf = pd.Series(pd.NaT, index=px.index)
    for d, row in ext.iterrows():
        if d in conf.index:
            conf.loc[d] = row.confirmed
    n = len(px)
    folds = np.array_split(np.arange(n), cfg.N_FOLDS)
    p_low = pd.Series(np.nan, index=px.index)
    p_high = pd.Series(np.nan, index=px.index)
    for i in range(1, cfg.N_FOLDS):
        cutoff = px.index[folds[i][0]]
        tr_mask = (px.index < cutoff) & X.notna().all(axis=1).to_numpy()
        # discard train days whose nearest extremum was not yet confirmed at the cutoff
        near_unconf = pd.Series(False, index=px.index)
        for d, row in ext.iterrows():
            if row.confirmed >= cutoff:
                j = px.index.get_loc(d)
                near_unconf.iloc[max(0, j - cfg.EXTREMA_Z):j + cfg.EXTREMA_Z + 1] = True
        tr_mask &= ~near_unconf.to_numpy()
        if tr_mask.sum() < cfg.ML_MIN_TRAIN_DAYS:
            continue
        te = folds[i][X.iloc[folds[i]].notna().all(axis=1).to_numpy()]
        for target, sink in ((y_low, p_low), (y_high, p_high)):
            m = HistGradientBoostingClassifier(
                max_iter=cfg.ML_MAX_ITER, learning_rate=cfg.ML_LEARNING_RATE,
                max_depth=cfg.ML_MAX_DEPTH, random_state=cfg.BOOT_SEED)
            m.fit(X[tr_mask], target[tr_mask])
            if len(te):
                sink.iloc[te] = m.predict_proba(X.iloc[te])[:, 1]
    oos = p_low.notna()
    n_oos = int(oos.sum())
    if not n_oos:
        return dict(n_oos_days=0, low_base_rate=float("nan"), low_precision=float("nan"),
                    low_z=float("nan"), overlay_sharpe=0.0, hold_sharpe=0.0, passes=False)
    base = float(y_low[oos].mean())
    bet = oos & (p_low > 0.5)
    prec = float(y_low[bet].mean()) if bet.any() else float("nan")
    z = ((prec - base) / np.sqrt(base * (1 - base) / int(bet.sum()))
         if bet.any() and 0 < base < 1 else float("nan"))
    # toy overlay: long from predicted low until predicted high, fee+slip per flip
    state = ((p_low > 0.5).astype(float) - (p_high > 0.5).astype(float))
    pos = state.replace(0.0, np.nan).ffill().clip(lower=0.0).fillna(0.0)
    flips = pos.diff().abs().fillna(0.0)
    ret = px.pct_change().fillna(0.0)
    overlay = (pos.shift(1).fillna(0.0) * ret - flips * (cfg.TAKER_FEE + cfg.SLIPPAGE))[oos]
    hold = ret[oos]

    def _sh(s):
        return float(s.mean() / s.std() * np.sqrt(cfg.DPY)) if s.std() > 0 else 0.0

    out = dict(n_oos_days=n_oos, low_base_rate=base, low_precision=prec,
               low_z=float(z), overlay_sharpe=_sh(overlay), hold_sharpe=_sh(hold))
    out["passes"] = bool(not np.isnan(z) and z >= cfg.META_Z
                         and out["overlay_sharpe"] > out["hold_sharpe"])
    return out
