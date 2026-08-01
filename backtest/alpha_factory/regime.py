"""PM-QUANT Track C — learned regime gate over the incumbent book. The book's
edges are time-series (trend/carry class); the question is WHEN to be exposed.
A shallow classifier reads the anchor's regime state (vol structure, trend
bits including the 50/150 SMA finding, breadth, funding, dispersion) and
predicts the sign of the next REGIME_H-day book return; exposure goes flat on a
bad call, paying round-trip switch costs on every gate flip. Kill line: pooled
OOS gated Sharpe > ungated AND gated maxDD no worse — a gate that only
de-risks by luck fails one of the two."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from .bench import incumbent_sleeves, ensemble
from .evaluate import purged_folds


def book_series(panel, cfg):
    return ensemble(incumbent_sleeves(panel, cfg))


def regime_features(panel):
    """Daily anchor/breadth state, all inputs <= t."""
    px = panel.close
    anchor = "BTCUSDT" if "BTCUSDT" in px.columns else px.columns[0]
    a = px[anchor]
    aret = a.pct_change()
    ma50, ma150, ma200 = a.rolling(50).mean(), a.rolling(150).mean(), a.rolling(200).mean()
    vol20, vol63 = aret.rolling(20).std(), aret.rolling(63).std()
    mom28 = px.pct_change(28)
    return pd.DataFrame({
        "a_ret5": a.pct_change(5),
        "a_ret28": a.pct_change(28),
        "a_over_ma200": (a > ma200).astype(float),
        "a_5050": (ma50 > ma150).astype(float),   # the 50/150 regime bit (ledger free-upgrade)
        "a_volratio": vol20 / vol63.replace(0, np.nan),
        "breadth": (px.gt(px.rolling(200).mean())).mean(axis=1),
        "dispersion": mom28.std(axis=1),
        "funding3": panel.funding.reindex(columns=px.columns).fillna(0.0)
                    .mean(axis=1).rolling(3).mean(),
        "a_dd63": a / a.rolling(63).max() - 1,
    })


def apply_gate(book, gate, cfg):
    """gate_t (0/1, decided at close t) scales the book's t+1 return; every gate
    flip pays fee+slip per side on the moved notional (whole book on/off)."""
    g = gate.reindex(book.index).ffill().fillna(1.0)
    switch = g.diff().abs().fillna(0.0)
    out = book * g.shift(1).fillna(1.0) - switch * (cfg.TAKER_FEE + cfg.SLIPPAGE)
    out.name = book.name
    return out


def _maxdd(s):
    eq = (1 + s.fillna(0.0)).cumprod()
    return float((eq / eq.cummax() - 1).min())


def _sharpe(s, dpy):
    s = s.dropna()
    return float(s.mean() / s.std() * np.sqrt(dpy)) if len(s) > 30 and s.std() > 0 else 0.0


def track_c_kill(panel, cfg):
    """Walk-forward gate; kill line = pooled-OOS Sharpe improves AND maxDD does
    not worsen. n_trials = 1 (single model, no variant grid)."""
    book = book_series(panel, cfg)
    X = regime_features(panel)
    y = (book.rolling(cfg.REGIME_H).sum().shift(-cfg.REGIME_H) > 0)
    folds = purged_folds(book.index, cfg.N_FOLDS, cfg.EMBARGO_DAYS)
    gate = pd.Series(np.nan, index=book.index)
    for i in range(1, cfg.N_FOLDS):
        cut = folds[i][0] - pd.Timedelta(days=cfg.REGIME_H + cfg.EMBARGO_DAYS)
        tr = book.index[(book.index <= cut)]
        tr = tr[X.loc[tr].notna().all(axis=1) & y.loc[tr].notna()]
        if len(tr) < cfg.ML_MIN_TRAIN_DAYS:
            continue
        m = HistGradientBoostingClassifier(
            max_iter=cfg.ML_MAX_ITER, learning_rate=cfg.ML_LEARNING_RATE,
            max_depth=cfg.ML_MAX_DEPTH, random_state=cfg.BOOT_SEED)
        m.fit(X.loc[tr], y.loc[tr].astype(bool))
        te = folds[i][X.loc[folds[i]].notna().all(axis=1)]
        if len(te):
            gate.loc[te] = m.predict_proba(X.loc[te])[:, 1] > 0.5
    oos = gate.notna()
    if not oos.any():
        return dict(ungated_sharpe=0.0, gated_sharpe=0.0, ungated_maxdd=0.0,
                    gated_maxdd=0.0, n_oos_days=0, flat_fraction=0.0, passes=False)
    b = book[oos]
    g = apply_gate(book, gate.astype(float), cfg)[oos]
    out = dict(ungated_sharpe=_sharpe(b, cfg.DPY), gated_sharpe=_sharpe(g, cfg.DPY),
               ungated_maxdd=_maxdd(b), gated_maxdd=_maxdd(g),
               n_oos_days=int(oos.sum()),
               flat_fraction=float(1 - gate[oos].mean()))
    # relative improvement alone is gameable: on a losing book "always flat" wins
    # the comparison while trading nothing. The gate must beat the book, be
    # ABSOLUTELY profitable, and actually participate.
    out["passes"] = bool(out["gated_sharpe"] > max(out["ungated_sharpe"], 0.0)
                         and out["gated_maxdd"] >= out["ungated_maxdd"]
                         and out["flat_fraction"] < 1.0)
    return out
