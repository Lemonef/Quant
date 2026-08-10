"""Bounded BTC volatility horse race: historical, EWMA, DVOL, and one blend."""
from pathlib import Path
import json
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from .evaluate import purged_folds
from .regime import book_series


DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"


def fetch_dvol_daily(cfg=None, cache_path=None):
    """Fetch complete daily BTC DVOL closes, paginating by the last returned day."""
    if cfg is None:
        from . import config as cfg
    path = Path(cache_path) if cache_path else Path(__file__).parents[1] / "data/options/BTC_dvol_daily.csv"
    if path.exists() and time.time() - path.stat().st_mtime < cfg.VOLMODEL_CACHE_DAYS * 86400:
        return _read_dvol(path)

    start = int(pd.Timestamp(cfg.VOLMODEL_DVOL_START, tz="UTC").timestamp() * 1000)
    end = int(pd.Timestamp.now(tz="UTC").normalize().timestamp() * 1000)
    rows = []
    page_end = end
    seen = set()
    while page_end is not None and page_end not in seen:
        seen.add(page_end)
        params = urllib.parse.urlencode({
            "currency": "BTC", "resolution": 86400,
            "start_timestamp": start, "end_timestamp": page_end,
        })
        with urllib.request.urlopen(f"{DVOL_URL}?{params}", timeout=30) as response:
            payload = json.load(response)
        result = payload.get("result", {})
        batch = result.get("data", [])
        rows.extend(batch)
        page_end = result.get("continuation")

    if not rows:
        raise RuntimeError("Deribit returned no BTC DVOL observations")
    raw = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    out = pd.DataFrame({
        "date": pd.to_datetime(raw["timestamp"], unit="ms", utc=True),
        "dvol": pd.to_numeric(raw["close"], errors="coerce"),
    }).dropna().drop_duplicates("date").sort_values("date")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out.set_index("date")["dvol"]


def _read_dvol(path):
    frame = pd.read_csv(path)
    date_col = "date" if "date" in frame else frame.columns[0]
    value_col = "dvol" if "dvol" in frame else frame.columns[-1]
    idx = pd.to_datetime(frame[date_col], utc=True)
    return pd.Series(pd.to_numeric(frame[value_col], errors="coerce").values,
                     index=idx, name="dvol").dropna().sort_index()


def forecast_frame(close, dvol, cfg):
    """Forecasts known at close t and realized volatility over returns t+1..t+H."""
    close = close.astype(float).sort_index()
    ret = close.pct_change()
    annualizer = np.sqrt(cfg.DPY)
    target = ret.rolling(cfg.VOLMODEL_H).std().shift(-cfg.VOLMODEL_H) * annualizer
    hist = ret.rolling(cfg.VOLMODEL_HIST_DAYS).std() * annualizer
    ewma = ret.pow(2).ewm(alpha=1 - cfg.VOLMODEL_EWMA_LAMBDA, adjust=False).mean().pow(0.5) * annualizer
    implied = pd.Series(dvol, copy=False).astype(float).reindex(close.index) / 100.0
    return pd.DataFrame({"target": target, "hist20": hist, "ewma": ewma,
                         "dvol": implied, "blend": (hist + implied) / 2})


def qlike(actual, forecast, eps=1e-12):
    """QLIKE on variance, with a numerical floor so zero-vol samples are valid."""
    a, f = pd.Series(actual).align(pd.Series(forecast), join="inner")
    av = np.maximum(a.to_numpy(dtype=float) ** 2, eps)
    fv = np.maximum(f.to_numpy(dtype=float) ** 2, eps)
    valid = np.isfinite(av) & np.isfinite(fv)
    return float(np.mean(av[valid] / fv[valid] + np.log(fv[valid]))) if valid.any() else 0.0


def _logvol_mse(actual, forecast, eps):
    a = np.maximum(actual.to_numpy(dtype=float), eps)
    f = np.maximum(forecast.to_numpy(dtype=float), eps)
    valid = np.isfinite(a) & np.isfinite(f)
    return float(np.mean((np.log(a[valid]) - np.log(f[valid])) ** 2)) if valid.any() else 0.0


def score_forecasts(frame, cfg):
    names = ["hist20", "ewma", "dvol", "blend"]
    overlap = frame.dropna(subset=["target"] + names)
    split = int(len(overlap) * cfg.OOS_SPLIT)
    oos = overlap.iloc[split:]
    oq = {name: qlike(oos.target, oos[name], cfg.VOLMODEL_EPS) for name in names}
    om = {name: _logvol_mse(oos.target, oos[name], cfg.VOLMODEL_EPS) for name in names}
    fold_qlike = []
    fold_ranks = []
    for fold in purged_folds(overlap.index, cfg.N_FOLDS, cfg.EMBARGO_DAYS):
        sample = overlap.reindex(fold).dropna()
        losses = {name: qlike(sample.target, sample[name], cfg.VOLMODEL_EPS) for name in names}
        fold_qlike.append(losses)
        fold_ranks.append(list(sorted(losses, key=losses.get)))
    consistency = float(np.mean([x["dvol"] < x["hist20"] for x in fold_qlike])) if fold_qlike else 0.0
    return {"oos_qlike": oq, "oos_logvol_mse": om, "fold_qlike": fold_qlike,
            "fold_ranking": fold_ranks, "dvol_beats_hist_fold_fraction": consistency,
            "n_overlap": int(len(overlap)), "n_oos": int(len(oos))}


def _sharpe(series, dpy):
    s = series.dropna()
    return float(s.mean() / s.std() * np.sqrt(dpy)) if len(s) > 30 and s.std() > 0 else 0.0


def _maxdd(series):
    equity = (1 + series.fillna(0.0)).cumprod()
    return float((equity / equity.cummax() - 1).min()) if len(equity) else 0.0


def volmodel_kill(panel, cfg, dvol=None):
    """Run the single horse race and its incumbent-book application kill line."""
    close = panel.close["BTCUSDT"]
    dvol = fetch_dvol_daily(cfg) if dvol is None else dvol
    frame = forecast_frame(close, dvol, cfg)
    scores = score_forecasts(frame, cfg)
    overlap = frame.dropna()
    oos_index = overlap.index[int(len(overlap) * cfg.OOS_SPLIT):]
    book = book_series(panel, cfg).reindex(frame.index)
    raw = book.reindex(oos_index).dropna()
    application = {"unscaled": {"sharpe": _sharpe(raw, cfg.DPY), "maxdd": _maxdd(raw)}}
    # Claude-audit fix: the original scaling (book vol target / BTC-vol forecast)
    # parked the book at ~6% exposure — the DD "cut" was cash, the Sharpe tie was
    # scale invariance, and the kill line passed on an artifact. Fair form: unit-
    # MEAN exposure per forecaster, so only the TIMING differs between models.
    for name in ("hist20", "ewma", "dvol", "blend"):
        f = frame[name].clip(lower=cfg.VOLMODEL_EPS)
        scale = (float(f.reindex(oos_index).mean()) / f).clip(upper=cfg.VOLMODEL_LEVERAGE_CAP)
        scaled = (book * scale.shift(1)).reindex(oos_index).dropna()
        application[name] = {"sharpe": _sharpe(scaled, cfg.DPY), "maxdd": _maxdd(scaled),
                             "avg_exposure": float(scale.reindex(oos_index).mean())}
    winners = []
    for name in ("dvol", "blend"):
        if (scores["oos_qlike"][name] < scores["oos_qlike"]["hist20"]
                and application[name]["sharpe"] > application["unscaled"]["sharpe"]
                and application[name]["maxdd"] >= application["unscaled"]["maxdd"]):
            winners.append(name)
    # forecast_win is reported separately: the INPUT question (implied beats
    # historical as a vol forecaster) can be true while timing this book adds nothing
    forecast_win = scores["oos_qlike"]["dvol"] < scores["oos_qlike"]["hist20"]
    return {**scores, "application": application, "forecast_win_dvol": bool(forecast_win),
            "winning_models": winners, "passes": bool(winners)}
