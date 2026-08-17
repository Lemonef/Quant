"""
flowsig_test.py — REVEALED-POSITIONING / FLOW time-series signals vs BTC: the kill test.

The mechanism class (owner 2026-08-10, "money showing true expectations before price"):
stablecoin supply = dry powder entering the system; futures open interest and long/short
ratios = leverage and crowd positioning; quarterly basis = the price of leverage. Each is
a DAILY external series with real history (DefiLlama 2017-, Binance Vision metrics 2021-,
quarterly klines 2020-), so unlike the options/GEX family nothing here waits on accrual.

DISCIPLINE — everything reuses the already-audited leadlag machinery and its constants;
NOTHING new is tunable:
  - Signal convention, ALL candidates: sign of the LEADLAG_W(=28)-day change, decided at
    close t from data <= t. One convention, zero per-signal parameters.
  - Kill line per signal x horizon = leadlag.py's three legs verbatim: (1) conditional
    mean gap |t| >= LEADLAG_T_MIN with the overlap correction, (2) identical gap sign in
    EVERY purged fold, (3) train-chosen-side overlay beats buy-and-hold on the untouched
    OOS tail net of taker fee + slippage.
  - n_trials = n_signals(5) x n_horizons(2) = 10, all declared here, all reported.
  - PIT: external series are published same-day (stablecoins EOD, Vision T+1 dumps,
    basis from daily closes). Signals at close t therefore use data <= t; the ONE
    exception is Vision metrics' T+1 publication lag, handled by lagging those signals
    ONE extra day (signal at t uses metrics through t-1) — declared, not optional.

Usage:
    python backtest/flowsig_test.py            # real data -> report
    python backtest/flowsig_test.py selftest   # planted + noise synthetic checks
Output: backtest_results/FLOWSIG_<date>.md
"""
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from alpha_factory import config as cfg
from alpha_factory.panel import build_panel
from alpha_factory.evaluate import purged_folds
from alpha_factory.leadlag import diff_means_t, fold_signs, overlay_returns, _sharpe

DATA = HERE / "data"
OPT = DATA / "options"
RESULTS = HERE.parent / "backtest_results"
ANCHOR = "BTCUSDT"
METRICS_LAG_D = 1              # Vision dumps publish T+1 — metrics signals lag one day
BASIS_CSV = OPT / "btc_quarterly_basis_daily.csv"
FAPI = "https://fapi.binance.com/fapi/v1/continuousKlines"


# ── data legs ────────────────────────────────────────────────────────────────
def load_stablecoins():
    df = pd.read_csv(OPT / "stablecoin_supply_daily.csv", parse_dates=["date"])
    return df.set_index("date")["pegged_usd_circulating"].astype(float)


def load_metrics(sym="BTCUSDT"):
    df = pd.read_csv(OPT / f"{sym}_metrics_daily.csv", parse_dates=["date"])
    return df.set_index("date").astype(float)


def fetch_basis(force=False):
    """Daily quarterly-vs-spot basis from fapi continuousKlines (CURRENT_QUARTER).
    Works from a non-US IP (the 451 geo-block hits GitHub runners, not this machine).
    Cached to CSV; paginated 1500 bars/call from 2020-01-01."""
    if BASIS_CSV.exists() and not force:
        df = pd.read_csv(BASIS_CSV, parse_dates=["date"])
        return df.set_index("date")["quarterly_close"].astype(float)
    rows, start = [], int(dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    while True:
        url = (f"{FAPI}?pair=BTCUSDT&contractType=CURRENT_QUARTER&interval=1d"
               f"&limit=1500&startTime={start}")
        with urllib.request.urlopen(url, timeout=30) as r:
            batch = json.load(r)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 1500:
            break
        start = batch[-1][0] + 86_400_000
        time.sleep(0.3)
    df = pd.DataFrame({"date": pd.to_datetime([b[0] for b in rows], unit="ms"),
                       "quarterly_close": [float(b[4]) for b in rows]})
    df = df.drop_duplicates("date").sort_values("date")
    df.to_csv(BASIS_CSV, index=False)
    return df.set_index("date")["quarterly_close"]


def build_signals(panel):
    """All candidate signals on the panel's (naive-date) index. Sign of the 28d change."""
    idx = panel.close.index
    naive = idx.tz_localize(None) if getattr(idx, "tz", None) is not None else idx
    spot = pd.Series(panel.close[ANCHOR].to_numpy(), index=naive)

    def on_idx(s):
        return s.reindex(naive)

    W = cfg.LEADLAG_W
    sigs, spans = {}, {}

    stab = load_stablecoins()
    # audit #6: same-day EOD availability unverified — lag 1d like the metrics legs
    sigs["stable_flow"] = np.sign(on_idx(stab).pct_change(W)).shift(1)

    met = load_metrics("BTCUSDT")
    for name, col in (("oi_flow", "sum_open_interest"),
                      ("toptrader_flow", "toptrader_ls_ratio"),
                      ("taker_flow", "taker_ls_vol_ratio")):
        s = np.sign(on_idx(met[col]).pct_change(W)).shift(METRICS_LAG_D)
        sigs[name] = s

    q = on_idx(fetch_basis())
    basis = q / spot - 1.0
    sigs["basis_flow"] = np.sign(basis.diff(W))

    # GRAVEYARD REVIVAL (owner 2026-08-18 "revisit some graves"): implied vol as the
    # regime carrier — PM-QUANT's declared reopen trigger is the options data class, and
    # the standing rule prefers implied over historical vol. Deribit DVOL daily history
    # via the audited volmodel fetch (cached CSV). Same 28d-change-sign convention.
    try:
        from alpha_factory.volmodel import fetch_dvol_daily
        dv = fetch_dvol_daily()
        dv.index = pd.DatetimeIndex(dv.index).tz_localize(None)
        sigs["dvol_flow"] = np.sign(on_idx(dv).pct_change(W)).shift(METRICS_LAG_D)
    except Exception as e:
        print(f"WARN dvol_flow unavailable: {e}")

    for k, v in sigs.items():
        nz = v.dropna()
        spans[k] = (str(nz.index.min().date()) if len(nz) else "-",
                    str(nz.index.max().date()) if len(nz) else "-", int(len(nz)))
    return sigs, spans, spot


# ── the kill test (leadlag_kill's exact protocol, external signals) ──────────
def run_kill(panel, sigs):
    idx = panel.close.index
    naive = idx.tz_localize(None) if getattr(idx, "tz", None) is not None else idx
    a_close = pd.Series(panel.close[ANCHOR].to_numpy(), index=naive)
    a_ret = a_close.pct_change()
    folds = purged_folds(naive, cfg.N_FOLDS, cfg.EMBARGO_DAYS)
    folds = [f.tz_localize(None) if getattr(f, "tz", None) is not None else f for f in folds]
    cut = int(len(naive) * cfg.OOS_SPLIT)
    train, oos = naive[:cut], naive[cut:]
    rows = []
    for name, s in sigs.items():
        for h in cfg.LEADLAG_HORIZONS:
            fwd = a_close.pct_change(h).shift(-h)
            r = dict(signal=name, horizon=h, **diff_means_t(fwd, s, h))
            fs = fold_signs(fwd, s, folds)
            r["fold_signs"] = fs
            r["folds_agree"] = bool(np.isfinite(r["diff"]) and fs
                                    and all(f == np.sign(r["diff"]) for f in fs))
            # audit #1: the last h train rows have forward returns crossing into OOS —
            # they may not inform the traded-side choice
            tr = diff_means_t(fwd.reindex(train[:-h]), s.reindex(train[:-h]), h)
            r["favorable_sign"] = -1.0 if (tr["diff"] < 0) else 1.0
            ov = overlay_returns(a_ret, s, r["favorable_sign"], cfg).reindex(oos)
            r["n_oos_days"] = int(ov.notna().sum())
            r["overlay_sharpe"] = _sharpe(ov, cfg.DPY)
            r["hold_sharpe"] = _sharpe(a_ret.reindex(oos), cfg.DPY)
            r["passes"] = bool(np.isfinite(r["t"]) and abs(r["t"]) >= cfg.LEADLAG_T_MIN
                               and r["folds_agree"]
                               and r["overlay_sharpe"] > r["hold_sharpe"])
            rows.append(r)
    return rows


def write_report(rows, spans, n_days):
    today = dt.date.today().isoformat()
    p = RESULTS / f"FLOWSIG_{today}.md"
    L = [f"# FLOWSIG kill test — {today}",
         "", f"Anchor {ANCHOR} · window {cfg.LEADLAG_W}d change-sign (one convention, "
         f"zero per-signal parameters) · horizons {cfg.LEADLAG_HORIZONS} · "
         f"t floor {cfg.LEADLAG_T_MIN} · n_trials = {len(rows)} (all shown) · "
         f"panel days {n_days}", "",
         "Kill line per row (leadlag.py verbatim): |t|>=floor AND every purged fold "
         "agrees on the gap sign AND the train-side overlay beats buy-and-hold on the "
         "untouched OOS tail net of costs. Metrics signals carry a declared +1d "
         "publication lag.", "",
         "| signal | span (n) | h | t | diff (pp) | folds agree | OOS overlay SR | hold SR | PASS |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        sp = spans.get(r["signal"], ("-", "-", 0))
        L.append(f"| {r['signal']} | {sp[0]}→{sp[1]} ({sp[2]}) | {r['horizon']} | "
                 f"{r['t']:.2f} | {r['diff'] * 100:+.2f} | "
                 f"{'✅' if r['folds_agree'] else '—'} | {r['overlay_sharpe']:.2f} | "
                 f"{r['hold_sharpe']:.2f} | {'✅' if r['passes'] else '❌'} |")
    n_pass = sum(1 for r in rows if r["passes"])
    L += ["", f"## VERDICT: {n_pass}/{len(rows)} pass",
          "", "A pass here is a CANDIDATE for the full robust gauntlet "
          "(bootstrap/perturbation/plateau/CSCV/SPA), never an adoption. Zero passes = "
          "the family dies at the cheap test, as designed."]
    p.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote -> {p}")
    return n_pass


def selftest():
    """Planted signal must pass legs 1-2; pure noise must not pass anything."""
    rng = np.random.default_rng(7)
    n = 1200
    idx = pd.date_range("2021-01-01", periods=n, freq="D")
    ret = pd.Series(rng.normal(0.0005, 0.02, n), index=idx)
    close = (1 + ret).cumprod() * 30000

    class P:                                          # minimal stand-in panel
        pass
    p = P(); p.close = pd.DataFrame({ANCHOR: close})
    # planted: signal literally knows the next day's sign 60% of the time
    know = rng.random(n) < 0.60
    planted = pd.Series(np.where(know, np.sign(ret.shift(-1)), rng.choice([-1, 1], n)),
                        index=idx)
    noise = pd.Series(rng.choice([-1.0, 1.0], n), index=idx)
    rows = run_kill(p, {"planted": planted, "noise": noise})
    pl = [r for r in rows if r["signal"] == "planted" and r["horizon"] == 1][0]
    nz = [r for r in rows if r["signal"] == "noise"]
    assert abs(pl["t"]) >= cfg.LEADLAG_T_MIN and pl["folds_agree"], pl
    assert all(not r["passes"] for r in nz), nz
    print("selftest OK: planted separates, noise dies")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "selftest" in sys.argv:
        selftest()
    else:
        panel = build_panel(DATA)
        sigs, spans, _ = build_signals(panel)
        rows = run_kill(panel, sigs)
        write_report(rows, spans, len(panel.close.index))
