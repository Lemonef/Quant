"""First preregistered options snapshot pass; no VRP and no existing-file edits.

Run from any directory: python backtest/options_factor_test.py
The report contains the frozen preregistration, every trial and exact stdout.
"""
from pathlib import Path
from statistics import NormalDist
import json
import math
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from alpha_factory.leadlag import diff_means_t, _sharpe
from alpha_factory.evaluate import purged_folds
from alpha_factory import config as cfg

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "backtest_results/OPTIONS_FACTORS_2026-10-15.md"
ASOF = pd.Timestamp("2026-10-15", tz="UTC")  # only completed UTC days
HORIZONS = (1, 3, 7)
FACTORS = ("gex", "pcr_all", "pcr_month", "rr25", "iv_percentile", "maxpain_distance")
NORMAL = NormalDist()


def stamp(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def show(value, digits=2):
    return f"{value:.{digits}f}" if np.isfinite(value) else "NA"


def chain_factors():
    paths = sorted((ROOT / "backtest/data/options").glob("BTC_chain_*.csv"))
    if not paths:
        raise FileNotFoundError("No BTC chain snapshots")
    raw = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    raw["ts"] = pd.to_datetime(raw.snap_ts, unit="ms", utc=True)
    raw = raw[raw.ts < ASOF].copy()
    raw["day"] = raw.ts.dt.normalize()
    parts = raw.instrument_name.str.extract(r"^BTC-(\d{1,2}[A-Z]{3}\d{2})-(\d+(?:\.\d+)?)-([CP])$")
    raw["expiry"] = pd.to_datetime(parts[0], format="%d%b%y", utc=True, errors="coerce") + pd.Timedelta(hours=8)
    raw["strike"] = pd.to_numeric(parts[1], errors="coerce")
    raw["side"] = parts[2]
    if raw.expiry.isna().any():
        raise ValueError("Unrecognized BTC instrument name; no silent parsing drops")
    duplicates = int(raw.duplicated(["snap_ts", "instrument_name"]).sum())
    raw = raw.drop_duplicates(["snap_ts", "instrument_name"], keep="last")
    latest = raw.groupby("day").ts.transform("max")
    selected = raw[raw.ts == latest].copy()
    expired = int((selected.expiry <= selected.ts).sum())
    selected = selected[selected.expiry > selected.ts].copy()
    out = []
    for day, g in selected.groupby("day", sort=True):
        g = g.copy()
        if g.open_interest.isna().any() or (g.open_interest < 0).any():
            raise ValueError("Missing or negative open interest")
        spot = float(g.underlying_price.median())
        if not np.isfinite(spot) or spot <= 0:
            raise ValueError("Missing positive snapshot spot proxy")
        tau = (g.expiry - g.ts).dt.total_seconds() / (365 * 86400)
        sigma = g.mark_iv / 100
        valid = (sigma > 0) & (g.underlying_price > 0) & sigma.notna()
        d1 = (np.log(g.underlying_price / g.strike) + 0.5 * sigma**2 * tau) / (sigma * np.sqrt(tau))
        g["delta_abs"] = np.nan
        nd1 = pd.Series([NORMAL.cdf(float(x)) if np.isfinite(x) else np.nan for x in d1], index=g.index)
        g.loc[valid, "delta_abs"] = np.where(g.side[valid] == "C", nd1[valid], 1 - nd1[valid])
        gamma = np.exp(-d1**2 / 2) / (np.sqrt(2 * np.pi) * g.underlying_price * sigma * np.sqrt(tau))
        gex = float((gamma[valid] * g.open_interest[valid] * np.where(g.side[valid] == "C", 1, -1) * spot**2).sum())
        if ((~valid) & (g.open_interest > 0)).any():
            gex = np.nan  # incomplete gamma exposure cannot be called the total
        front = g[g.expiry == g.expiry.min()].copy()
        monthly = g[(g.expiry.dt.weekday == 4) & ((g.expiry + pd.Timedelta(days=7)).dt.month != g.expiry.dt.month)]
        monthly = monthly[monthly.expiry == monthly.expiry.min()]

        def pcr(frame):
            calls = frame.loc[frame.side == "C", "open_interest"].sum()
            return float(frame.loc[frame.side == "P", "open_interest"].sum() / calls) if calls > 0 else np.nan

        def iv25(side):
            a = front[(front.side == side) & (front.mark_iv > 0)].dropna(subset=["delta_abs", "mark_iv"])
            a = a.groupby("delta_abs").mark_iv.mean().sort_index()
            if len(a) < 2 or not a.index.min() <= 0.25 <= a.index.max():
                return np.nan
            return float(np.interp(0.25, a.index.to_numpy(), a.to_numpy()))

        strikes = np.sort(front.strike.unique())
        atm_strike = strikes[np.argmin(np.abs(strikes - spot))]
        atm = front[(front.strike == atm_strike) & (front.mark_iv > 0)].groupby("side").mark_iv.mean()
        atm_iv = float(atm.mean()) if "C" in atm and "P" in atm else np.nan
        k = front.strike.to_numpy()
        oi = front.open_interest.to_numpy()
        calls = (front.side == "C").to_numpy()
        payout = (np.where(calls[None, :], np.maximum(strikes[:, None] - k, 0),
                           np.maximum(k - strikes[:, None], 0)) * oi).sum(axis=1)
        pain = float(strikes[np.argmin(payout)])
        out.append(dict(day=day, snap_ts=g.ts.iloc[0], spot_proxy=spot, gex=gex,
                        gex_sign=np.sign(gex), pcr_all=pcr(g), pcr_month=pcr(monthly),
                        rr25=iv25("C") - iv25("P"), atm_iv=atm_iv,
                        front_expiry=front.expiry.iloc[0], maxpain_strike=pain,
                        maxpain_distance=(spot - pain) / spot,
                        invalid_iv_rows=int((~valid).sum())))
    daily = pd.DataFrame(out).set_index("day").sort_index()
    daily["iv_percentile"] = np.nan
    for i in range(len(daily)):
        prior = daily.atm_iv.iloc[:i].dropna()
        value = daily.atm_iv.iloc[i]
        if len(prior) >= 20 and np.isfinite(value):
            daily.loc[daily.index[i], "iv_percentile"] = float(((prior < value).sum() + 0.5 * (prior == value).sum()) / len(prior))
    calendar = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    return daily.reindex(calendar), dict(files=[p.name for p in paths], rows=len(raw),
                                        duplicates=duplicates, expired=expired,
                                        timestamps=int(raw.snap_ts.nunique()))


def load_closes(first, last):
    path = ROOT / "backtest/data/BTCUSDT_1d.csv"
    local = pd.Series(dtype=float)
    messages = []
    if path.exists():
        df = pd.read_csv(path)
        times = pd.to_datetime(df.open_time, unit="ms", utc=True).dt.normalize()
        local = pd.Series(df.close.to_numpy(dtype=float), index=times).sort_index()
        local = local[~local.index.duplicated(keep="last")]
        local = local[local.index < ASOF]
        messages.append(f"Local BTC closes: {stamp(local.index.min())} to {stamp(local.index.max())}, n={len(local)}.")
    needed = pd.date_range(first, min(last, ASOF - pd.Timedelta(days=1)), freq="D")
    missing = needed.difference(local.dropna().index)
    if len(missing):
        params = dict(symbol="BTCUSDT", interval="1d", startTime=int(missing.min().timestamp() * 1000),
                      endTime=int((missing.max() + pd.Timedelta(days=1)).timestamp() * 1000) - 1, limit=1000)
        url = "https://data-api.binance.vision/api/v3/klines?" + urllib.parse.urlencode(params)
        messages.append(f"Required closes absent locally: {len(missing)} days; permitted fetch attempted: {url}")
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                payload = json.load(response)
            if not isinstance(payload, list):
                raise ValueError(f"Non-kline API response: {str(payload)[:150]}")
            fetched = pd.Series({pd.Timestamp(int(r[0]), unit="ms", tz="UTC").normalize(): float(r[4])
                                 for r in payload if int(r[6]) < int(ASOF.timestamp() * 1000)}, dtype=float)
            local = local.combine_first(fetched)
            messages.append(f"Fetch returned {len(fetched)} completed candles; no data file written.")
        except Exception as exc:
            messages.append(f"FETCH FAILED: {type(exc).__name__}: {exc}")
    if (local.dropna() <= 0).any():
        raise ValueError("BTC closes must be positive")
    return local.reindex(pd.date_range(first, last, freq="D")), messages


def sharpe(series):
    # Preserve the precedent's length restriction, but show NA rather than its
    # 0.0 sentinel, which is misleading on this short tail.
    if series.isna().any() or len(series) <= 30 or series.std() <= 0:
        return np.nan
    return _sharpe(series, cfg.DPY)


def overlay_tail(closes, decision, side, tail):
    returns = closes.pct_change(fill_method=None).reindex(tail)
    pos = (decision.shift(1).reindex(tail) == side).astype(float)
    turnover = pos.diff().abs()
    turnover.iloc[0] = pos.iloc[0]  # book starts flat; charge initial entry
    cost = cfg.TAKER_FEE + cfg.SLIPPAGE
    ov = pos * returns - turnover * cost
    ov.iloc[-1] -= pos.iloc[-1] * cost
    hold = returns.copy()
    hold.iloc[0] -= cost
    hold.iloc[-1] -= cost
    return sharpe(ov), sharpe(hold), float(turnover.sum() + pos.iloc[-1])


def main():
    # Freeze/read the preregistration before even loading factor or price data.
    prereg = REPORT.read_text(encoding="utf-8").split("\n## Data coverage", 1)[0].rstrip()
    if "PRE-REGISTRATION" not in prereg or "n_trials = 18" not in prereg:
        raise RuntimeError("Frozen preregistration missing; refusing to compute")
    REPORT.write_text(prereg + "\n", encoding="utf-8")
    daily, meta = chain_factors()
    first, last = daily.index.min(), daily.index.max()
    closes, price_notes = load_closes(first, last + pd.Timedelta(days=8))
    dates = daily.index
    cut = int(len(dates) * cfg.OOS_SPLIT)
    boundary = dates[cut] + pd.Timedelta(days=1)  # decision day boundary
    tail = pd.date_range(boundary + pd.Timedelta(days=1), min(last + pd.Timedelta(days=2), ASOF - pd.Timedelta(days=1)), freq="D")
    signals = pd.DataFrame(index=dates)
    for name in FACTORS:
        value = daily[name]
        if name in ("gex", "maxpain_distance"):
            signals[name] = np.sign(value)
        elif name == "iv_percentile":
            signals[name] = np.sign(value - 0.5)
        else:
            median = value.shift(1).rolling(20, min_periods=10).median()
            signals[name] = np.sign(value - median)
    folds = purged_folds(dates, cfg.N_FOLDS, cfg.EMBARGO_DAYS)
    blocks = np.array_split(np.arange(len(dates)), cfg.N_FOLDS)
    rows = []
    for name in FACTORS:
        signal = signals[name]
        decision = signal.copy()
        decision.index = decision.index + pd.Timedelta(days=1)
        decision = decision.reindex(closes.index)
        for h in HORIZONS:
            target = np.log(closes.shift(-(h + 1)) / closes.shift(-1)).reindex(dates)
            stat = diff_means_t(target, signal, h)
            fs = []
            fold_n = []
            for f, block in zip(folds, blocks):
                end = dates[block[-1]] + pd.Timedelta(days=1)
                f = f[f + pd.Timedelta(days=1 + h) <= end]
                gap = diff_means_t(target.reindex(f), signal.reindex(f), h)
                fold_n.append(gap["n_pos"] + gap["n_neg"])
                fs.append(float(np.sign(gap["diff"])) if gap["n_pos"] and gap["n_neg"] else np.nan)
            agree = bool(np.isfinite(stat["diff"]) and stat["diff"] != 0 and
                         all(np.isfinite(x) and x == np.sign(stat["diff"]) for x in fs))
            train = dates[(dates < dates[cut]) & (dates + pd.Timedelta(days=h + 1) < boundary)]
            tr = diff_means_t(target.reindex(train), signal.reindex(train), h)
            side = np.sign(tr["diff"]) if np.isfinite(tr["diff"]) else np.nan
            ov, hold, turnover = overlay_tail(closes, decision, side, tail)
            if not np.isfinite(side) or side == 0:
                ov = np.nan
            passed = bool(np.isfinite(stat["t"]) and abs(stat["t"]) >= cfg.LEADLAG_T_MIN and agree
                          and np.isfinite(ov) and np.isfinite(hold) and ov > hold)
            rows.append(dict(factor=name, h=h, **stat, folds=fs, fold_n=fold_n,
                             agree=agree, overlay=ov, hold=hold, passed=passed,
                             train_side=side, turnover=turnover))

    lines = [f"Snapshot coverage: {stamp(first)} to {stamp(last)}; {daily.snap_ts.notna().sum()} observed days / {len(dates)} calendar days.",
             f"Snapshots={meta['timestamps']}; instrument rows={meta['rows']}; duplicate rows={meta['duplicates']}; expired rows excluded={meta['expired']}.",
             "Snapshot gaps: " + (", ".join(stamp(x) for x in dates[daily.snap_ts.isna()]) or "none"),
             *price_notes,
             f"Usable BTC closes in requested window: {closes.notna().sum()}/{len(closes)}; OOS {stamp(tail.min())} to {stamp(tail.max())}, {len(tail)} daily bars, {closes.pct_change(fill_method=None).reindex(tail).notna().sum()} valid returns.",
             "Gamma and delta: Black-76 derived; underlying_price is a forward/spot proxy, mark_iv is percent; 1 BTC contract size, rate zero.",
             "Factor coverage (raw n / usable nonzero sign n; first to last raw observation; missing calendar days):"]
    for name in FACTORS:
        valid = daily[name].dropna()
        sig_n = int((signals[name].notna() & signals[name].ne(0)).sum())
        span = f"{stamp(valid.index.min())} to {stamp(valid.index.max())}" if len(valid) else "NA"
        gaps = ", ".join(stamp(x) for x in dates[daily[name].isna()]) or "none"
        lines.append(f"  {name}: {len(valid)} / {sig_n}; {span}; missing={gaps}")
        lines.append(f"    Decision signs: positive={int(signals[name].gt(0).sum())}, negative={int(signals[name].lt(0).sum())}, zero={int(signals[name].eq(0).sum())}, unavailable={int(signals[name].isna().sum())}.")
    lines.append(f"Invalid IV rows in selected live snapshots: {int(daily.invalid_iv_rows.sum())}.")
    if not (signals.gex.gt(0).any() and signals.gex.lt(0).any()):
        lines.append("GEX lacks both signs in this sample: its conditional gap cannot be tested even if missing closes are recovered.")
    if len(tail) <= 30:
        lines.append(f"The {len(tail)}-bar completed OOS tail is below the precedent's >30-bar Sharpe requirement: the trading gate is unavailable even if closes are recovered.")
    lines += ["", "factor | h | n | n_eff | t | folds agree | OOS overlay SR | hold SR | PASS"]
    for r in rows:
        lines.append(f"{r['factor']} | {r['h']} | {r['n_pos'] + r['n_neg']} | {r['n_eff']} | {show(r['t'])} | {'yes' if r['agree'] else 'no'} | {show(r['overlay'])} | {show(r['hold'])} | {'YES' if r['passed'] else 'NO'}")
    lines += ["", "Fold sign / fold observation count / train favorable side / OOS turnover:"]
    for r in rows:
        lines.append(f"  {r['factor']} h={r['h']}: {','.join(show(x, 0) for x in r['folds'])} / {r['fold_n']} / {show(r['train_side'], 0)} / {show(r['turnover'], 0)}")
    z = NORMAL.inv_cdf(0.975)
    zb = NORMAL.inv_cdf(1 - 0.05 / (2 * len(rows)))
    zp = NORMAL.inv_cdf(0.8)
    lines += ["", "80% power MDE (standardized conditional gap, optimistic balanced-group normal approximation):"]
    for h in HORIZONS:
        eff = 70 // h
        nominal, adjusted = (z + zp) * 2 / np.sqrt(eff), (zb + zp) * 2 / np.sqrt(eff)
        power = 1 - NORMAL.cdf(z - 0.5 * np.sqrt(eff) / 2) + NORMAL.cdf(-z - 0.5 * np.sqrt(eff) / 2)
        lines.append(f"  At n=70, h={h}, n_eff~{eff}: nominal MDE={nominal:.2f} SD, Bonferroni MDE={adjusted:.2f} SD; nominal power for d=0.5: {power:.1%}.")
    lines += ["Actual-row MDE (nominal / Bonferroni); NA means no evaluable targets:"]
    for r in rows:
        ep, en = r['n_pos'] // r['h'], r['n_neg'] // r['h']
        scale = np.sqrt(1 / ep + 1 / en) if min(ep, en) >= 2 else np.nan
        lines.append(f"  {r['factor']} h={r['h']}: {show((z + zp) * scale)} / {show((zb + zp) * scale)} SD")
    passes = sum(r['passed'] for r in rows)
    targets = sum(r['n_pos'] + r['n_neg'] for r in rows)
    verdict = f"VERDICT: {passes}/18 PASS — UNDERPOWERED — cannot conclude."
    if not targets:
        verdict += " No evaluable BTC spot targets; all trials UNTESTABLE, not DEAD."
    elif passes:
        verdict += " Passing rows are provisional candidates only; multiplicity and short-tail limits remain."
    else:
        verdict += " No factor is DEAD on this sample."
    lines += ["", verdict]
    needed_eff = math.ceil(((zb + zp) * 2 / 0.5)**2)
    plan = "; ".join(f"h={h}: ~{needed_eff*h} usable days (~{max(0, needed_eff*h - int(daily.snap_ts.notna().sum()))} more than current snapshots, before warmup/imbalance)" for h in HORIZONS)
    lines += [f"What would make this conclusive: recover matched completed BTC spot closes, then accrue {plan}; >=31 valid untouched OOS bars, both signs in all purged folds, and independent replication. This targets 80% power for d=0.5 at Bonferroni alpha; no fixed n guarantees a pass.",
              "18 tests: expected nominal false positives ~0.9; independence reference P(any)~60.3%; a single nominal pass is unsurprising.",
              "VRP was not retested. No existing files or live_bot files modified."]
    printed = "\n".join(lines)
    table = ["| factor | h | n | t | folds agree | OOS overlay SR | hold SR | PASS |",
             "|---|---:|---:|---:|---|---:|---:|---|"]
    for r in rows:
        table.append(f"| {r['factor']} | {r['h']} | {r['n_pos']+r['n_neg']} | {show(r['t'])} | {'yes' if r['agree'] else 'no'} | {show(r['overlay'])} | {show(r['hold'])} | {'YES' if r['passed'] else 'NO'} |")
    observed = daily[daily.snap_ts.notna()]
    levels = ["| snapshot date | GEX level | GEX sign | PCR all | PCR month | RR25 pp | ATM IV % | IV percentile | max-pain strike | max-pain distance |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for day, row in observed.iterrows():
        values = [show(row.gex), show(row.gex_sign, 0), show(row.pcr_all, 4), show(row.pcr_month, 4),
                  show(row.rr25, 4), show(row.atm_iv, 4), show(row.iv_percentile, 4),
                  show(row.maxpain_strike), show(row.maxpain_distance, 6)]
        levels.append(f"| {stamp(day)} | " + " | ".join(values) + " |")
    report = (prereg + "\n\n## Data coverage and real printed output\n\n```text\n" + printed +
              "\n```\n\n## Results\n\n" + "\n".join(table) +
              "\n\nNA is unavailable, not a zero Sharpe or zero t. No targets are substituted or imputed. "
              "Bonferroni is a reference for power/multiplicity, not an extra retroactive kill gate. "
              "Fold counts and actual MDEs appear in stdout above. Statistical t can also be unavailable when either effective group has <2 observations.\n\n"
              "## Daily factor levels\n\n" + "\n".join(levels) +
              f"\n\n## Power and verdict\n\n{verdict}\n\n" + lines[-3] +
              "\n\nThe power estimates are optimistic: serial dependence of signals, overlapping returns, "
              "group imbalance, four-fold sign agreement and the trading gate further reduce power. "
              "Failure here does not establish structural cost drag or a population wrong-sign effect.\n")
    REPORT.write_text(report, encoding="utf-8")
    print(printed)


if __name__ == "__main__":
    main()
