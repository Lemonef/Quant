"""Preregistered COIN-M inverse quarterly carry; only new task artifacts are written.

Run: python -B backtest/basis_coinm_test.py
Rules follow basis_carry_v2; accounting uses BTC inverse PnL, not linear PnL.
Daily last-trade highs are a conservative MARK proxy, not actual mark observations.
The dated report contains assumptions, source links, coverage and printed output.
"""
import datetime as dt
import io
import json
import math
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from alpha_factory import config as cfg

ASOF = dt.date(2026, 10, 15)
DATA = HERE / "data" / "basis_cm"
REPORT = HERE.parent / "backtest_results" / "BASIS_COINM_2026-10-15.md"
BASE = "https://data.binance.vision/data/futures/cm/monthly/klines"
EXIT_DTES = (3, 5, 7, 10)
LEVS = (1.0, 1.5, 2.0)
MIN_DTE_ENTRY, PARTIAL_DTE = 20, 60
MIN_NET_ANN, CASH_YIELD, TERM_BASIS_ALLOW = .05, .045, .005
FACE = 100.0
CM_TAKER = .0005  # frozen regular-user COIN-M taker assumption, no discounts
FUT_COST = 2 * (CM_TAKER + cfg.SLIPPAGE)
SPOT_COST = cfg.TAKER_FEE + cfg.SLIPPAGE
ROUND_TRIP = 2 * (FUT_COST + SPOT_COST)
# Frozen published quarterly BTC brackets, NOT a historical account-specific feed.
# BTC position value (contracts * FACE / mark), cumulative/tax-bracket maintenance.
TIERS = ((10., .004), (20., .005), (30., .01), (50., .025),
         (100., .05), (200., .10), (400., .125), (1000., .15), (math.inf, .25))
SPEC = "https://www.binance.bh/en-AE/support/faq/detail/d33f37e2c7fe4da3b35ffc904e8fbab5"
FEES = "https://www.binance.com/en-NZ/support/faq/detail/360033544231"
SCHEDULE = "https://www.binance.com/en/fee/deliveryFee"
BRACKETS = "https://www.binance.com/en/support/announcement/detail/7c000aa897f74e59bf285ca05dccb1a6"
MARGIN = "https://www.binance.com/en-AU/support/faq/detail/be2c7d9d95b04a7e8044ed02dd7dfe5c"

PREREG = f"""# COIN-M inverse quarterly basis carry — 2026-10-15

## Preregistration (declared before downloading / calculating results)

Hypothesis: BTC collateral and an inverse BTCUSD quarterly short with USD face
N = Q * F_entry remove the separate USDT margin capital drag, survive at 1x,
and earn the basis on capital Q * S_entry. This is a basis/liquidity risk premium.

Kill line, identical to v2: FULL contracts, worst-of-exit-family mean annualized
net > MIN_NET_ANN (5%) AND >=80% positive at DTE5 AND DTE5 contract-bootstrap
CI lower bound >0 AND leave-one-delivery-year-out means all >0. Additional gate:
worst-of-family USD return ON CAPITAL beats 4.5% cash, and no observed 1x
liquidation. Missing exit-family evidence fails the test.

Universe: last-Friday quarterly deliveries from 2021 through 2026, settled at
least seven days before fixed as-of 2026-10-15 (same universe rule as v2).
Signal: first close t with DTE >=21 and
(F_close/S_close - 1 - 0.5% terminal allowance - {ROUND_TRIP:.2%} cost allowance)
*365/DTE >5%. Fill both legs at the NEXT CALENDAR DAY open, entry DTE >=20.
No signal retuning after observing results. DTE exits 3/5/7/10 and hold (DTE0).
Annualization is simple net*365/actual days, contract-equal mean, 10,000
contract bootstrap draws (seed {cfg.BOOT_SEED}), LOYO and pre/post-2024 split.
These are trade-period rates, not a compounded portfolio CAGR; no idle-cash
return, reinvestment or simultaneous-contract portfolio is claimed.

FULL requires first common spot/future bar at least DTE60 AND uninterrupted
daily data from that bar through delivery. Missing or late coverage is PARTIAL;
never interpolate, forward-fill, or move a fill to a later available bar.
PARTIAL results are descriptive only and unknown liquidation paths stay unknown.

Costs: spot inherits [v2's cost configuration](../backtest/alpha_factory/config.py)
and [cost model](../backtest/basis_carry_v2.py): assumed 0.06% fee +0.05% slippage, 0.11% per leg;
this is the repository cost assumption, not a verified regular-user spot tier.
COIN-M taker 0.05% +0.05% slippage, doubled together to 0.20% per futures leg,
following v2's 2x haircut convention. No maker rebate, VIP/BNB discount, funding
or borrowing. Fees/slippage are cash haircuts, not additional fill-price shifts.
Use a frozen fee assumption across history; no historical fee ledger available.
The [official calculation example]({FEES}) supports BTC fee = N/F * rate and
0.05% taker; the [current schedule]({SCHEDULE}) did not expose populated rows
to the browser, so an account-specific current/historical rate is unverified.

Mechanics: [Binance quarterly specifications]({SPEC}) give $100 face,
BTC collateral/settlement, and inverse PnL. Short PnL = contracts*$100*
(1/F_exit - 1/F_entry), valued in USD at exit SPOT, never at exit futures.
Choose an even integer contract count floor(F_entry/200)*2 and set
Q=contracts*$100/F_entry (approximately one BTC); hedge is exact, no fractional
contracts. Capital = Q*S_entry, with no extra USDT. Q is the gross BTC purchase;
spot-entry haircut Q*spot_cost and futures-entry haircut N/F_entry*fut_cost
are deducted from this same BTC pool. Entry costs thus slightly undercollateralize
the ideal pre-fee 1x hedge. BTC_end = Q - entry costs + inverse PnL -
N/F_exit*fut_cost; final spot-sale cost deducts BTC_end*spot_cost.
USD net = BTC_end_after_sale*S_exit/(Q*S_entry)-1;
BTC net = BTC_end_after_sale/Q-1 (USD-hedged wealth expressed in BTC).

Margin: same Q BTC, short N=L*Q*F_entry for L=1/1.5/2; only 1x is USD neutral.
Walk every held daily HIGH and exit-day OPEN (exit-day high occurs after exit
and is excluded, correcting v2's path endpoint). High of last-traded contract
is a conservative adverse MARK proxy, not a guaranteed bound on true marks.
Equity_BTC = Q - spot-entry cost - futures-entry cost + N*(1/M-1/F_entry).
Margin ratio = maintenance_BTC/equity_BTC; equity<=0 or ratio>=100% triggers.
Also report a conservative liquidation count reserving the full 0.20% futures
exit haircut: (maintenance+N/M*fut_cost)/equity>=100%.
No liquidation-damaged leveraged return is passed off as a carry return.

Maintenance uses the [published 2021 BTC quarterly tier table]({BRACKETS}),
frozen across this sample, with [cumulative bracket calculation]({MARGIN}):
BTC-value caps 10/20/30/50/100/200/400/1000/infinity; marginal rates
0.4/0.5/1/2.5/5/10/12.5/15/25%. This is an explicit historical-tier assumption,
not proof of each expired contract's contemporaneous account brackets.
Report the maximum observed position BTC value/tier; results apply to the
declared ~1 BTC scale. Include a 1% maintenance sensitivity at 1x.

Hold is v2's delivery-day 00:00 UTC OPEN proxy, not actual 08:00 settlement or
the index's final-hour average. It pays the same taker+slippage haircut as a
normal close; no additional double settlement fee. Delivery settlement details
are in the specifications link. USDT spot is treated as USD (no depeg/FX model).
"""


def deliveries():
    for year in range(2021, 2027):
        for month in (3, 6, 9, 12):
            first_next = dt.date(year + (month == 12), month % 12 + 1, 1)
            d = first_next - dt.timedelta(days=1)
            d -= dt.timedelta(days=(d.weekday() - 4) % 7)
            if d <= ASOF - dt.timedelta(days=7):
                yield d


def spot_ohlc():
    frames = []
    for name in ("BTCUSDT_1d.csv", "BTCUSDT_1d_since_2026-06.csv"):
        f = pd.read_csv(HERE / "data" / name)
        f["date"] = pd.to_datetime(f.open_time, unit="ms").dt.normalize()
        frames.append(f.set_index("date")[["open", "high", "low", "close"]].astype(float))
    overlap = frames[0].index.intersection(frames[1].index)
    if len(overlap):
        disagree = (frames[0].loc[overlap] - frames[1].loc[overlap]).abs().max(axis=1) > 1e-8
        for date in overlap[disagree]:
            print(f"Spot overlap revision: {date.date()} old close={frames[0].at[date, 'close']:.2f} "
                  f"supplemental close={frames[1].at[date, 'close']:.2f}; later file takes precedence", flush=True)
    f = pd.concat(frames)
    f = f[~f.index.duplicated(keep="last")].sort_index()
    return f[f.index.date < ASOF]


def fetch_month(job):
    symbol, ym = job
    name = f"{symbol}-1d-{ym}.zip"
    p = DATA / name
    url = f"{BASE}/{symbol}/1d/{name}"
    missing = DATA / f"{name}.missing.json"
    if missing.exists():
        return {"symbol": symbol, "month": ym, "url": url, "status": "404", "rows": []}
    raw, error = None, ""
    if p.exists():
        raw = p.read_bytes()
    else:
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers={"User-Agent": "quant/1.0"}), timeout=25) as r:
                    raw = r.read()
                # Validate ZIP before keeping it. Existing task caches are never modified.
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    if z.testzip() is not None:
                        raise ValueError("ZIP CRC failure")
                p.write_bytes(raw)
                break
            except HTTPError as e:
                if e.code == 404:
                    missing.write_text(json.dumps({"url": url, "status": 404, "asof": str(ASOF)}), encoding="utf-8")
                    return {"symbol": symbol, "month": ym, "url": url, "status": "404", "rows": []}
                error = str(e)
            except (URLError, TimeoutError, OSError, ValueError) as e:
                error = str(e)
            if attempt < 2:
                time.sleep(attempt + 1)
    if raw is None:
        return {"symbol": symbol, "month": ym, "url": url, "status": f"ERROR {error}", "rows": []}
    rows = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for member in z.namelist():
            if not member.endswith(".csv"):
                continue
            for line in z.read(member).decode("utf-8-sig").splitlines():
                c = line.split(",")
                if not c[0].isdigit():
                    continue
                rows.append((int(c[0]), *(float(v) for v in c[1:5])))
    return {"symbol": symbol, "month": ym, "url": url, "status": "OK", "rows": rows}


def download_universe(ds):
    DATA.mkdir(parents=True, exist_ok=True)
    jobs = []
    for d in ds:
        m = dt.date(d.year, d.month, 1)
        for _ in range(12):
            jobs.append((f"BTCUSD_{d:%y%m%d}", f"{m:%Y-%m}"))
            m = (m - dt.timedelta(days=1)).replace(day=1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = []
        for i, result in enumerate(pool.map(fetch_month, jobs), 1):
            fetched.append(result)
            if i % 36 == 0 or i == len(jobs):
                print(f"Vision monthly archives checked: {i}/{len(jobs)}", flush=True)
    manifest = [{k: v for k, v in r.items() if k != "rows"} | {"bars": len(r["rows"])} for r in fetched]
    mp = DATA / "download_manifest_2026-10-15.json"
    if not mp.exists():
        mp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    futures = {}
    for d in ds:
        symbol = f"BTCUSD_{d:%y%m%d}"
        records = [r for r in fetched if r["symbol"] == symbol]
        rows = [bar for r in records for bar in r["rows"]]
        if not rows:
            futures[d] = (pd.DataFrame(), records)
            continue
        f = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
        dup = f[f.ts.duplicated(keep=False)]
        if len(dup) and (dup.groupby("ts").nunique() > 1).any().any():
            raise ValueError(f"Conflicting duplicate futures bars: {symbol}")
        f = f.drop_duplicates("ts").sort_values("ts")
        f["date"] = pd.to_datetime(f.ts, unit="ms").dt.normalize()
        f = f.set_index("date").drop(columns="ts")
        if (f <= 0).any().any() or (f.high < f[["open", "close", "low"]].max(axis=1)).any():
            raise ValueError(f"Invalid futures OHLC: {symbol}")
        futures[d] = (f[f.index <= pd.Timestamp(d)], records)
    return futures, manifest


def coverage(fut, spot, delivery, records):
    end = pd.Timestamp(delivery)
    errors = [r["month"] for r in records if r["status"].startswith("ERROR")]
    if fut.empty:
        return {"partial": True, "reason": "all Vision months unavailable", "first_dte": None,
                "first": "—", "last": "—", "fut_gaps": [], "joint_gaps": [], "errors": errors}
    common = fut.index.intersection(spot.index)
    common = common[common <= end]
    fut_gaps = pd.date_range(fut.index[0], end).difference(fut.index)
    if len(common) == 0:
        return {"partial": True, "reason": "no spot overlap", "first_dte": None,
                "first": str(fut.index[0].date()), "last": str(fut.index[-1].date()),
                "fut_gaps": [str(t.date()) for t in fut_gaps], "joint_gaps": [], "errors": errors}
    first_dte = (end - common[0]).days
    joint_gaps = pd.date_range(common[0], end).difference(common)
    reasons = []
    if first_dte < PARTIAL_DTE:
        reasons.append(f"first common DTE={first_dte}<60")
    if len(fut_gaps):
        reasons.append(f"{len(fut_gaps)} missing futures days through delivery")
    if len(joint_gaps):
        reasons.append(f"{len(joint_gaps)} missing common days through delivery")
    if errors:
        reasons.append("download errors " + ",".join(errors))
    return {"partial": bool(reasons), "reason": "; ".join(reasons) or "complete common daily history",
            "first_dte": first_dte, "first": str(fut.index[0].date()), "last": str(fut.index[-1].date()),
            "fut_gaps": [str(t.date()) for t in fut_gaps],
            "joint_gaps": [str(t.date()) for t in joint_gaps], "errors": errors}


def maintenance(value_btc):
    """Tax-bracket maintenance; equivalent to value*rate minus cumulative deduction."""
    total, floor = 0., 0.
    for tier, (cap, rate) in enumerate(TIERS, 1):
        total += (min(value_btc, cap) - floor) * rate
        if value_btc <= cap:
            return total, tier
        floor = cap
    raise AssertionError("unreachable")


def margin_walk(path, Fe, Q, N, spot_cost=SPOT_COST, fut_cost=FUT_COST):
    wallet = Q * (1 - spot_cost) - N / Fe * fut_cost
    out = {"liq": False, "reserve_liq": False, "max_ratio": 0., "max_reserved_ratio": 0.,
           "first_liq": "—", "first_reserved_liq": "—", "max_value": 0., "max_tier": 0,
           "min_equity": math.inf, "sensitivity_1pct_liq": False}
    for date, mark in path:
        equity = wallet + N * (1 / mark - 1 / Fe)
        value = N / mark
        mm, tier = maintenance(value)
        ratio = mm / equity if equity > 0 else math.inf
        reserved = (mm + value * fut_cost) / equity if equity > 0 else math.inf
        out["max_ratio"] = max(out["max_ratio"], ratio)
        out["max_reserved_ratio"] = max(out["max_reserved_ratio"], reserved)
        out["min_equity"] = min(out["min_equity"], equity)
        out["max_value"] = max(out["max_value"], value)
        out["max_tier"] = max(out["max_tier"], tier)
        if ratio >= 1 and not out["liq"]:
            out.update(liq=True, first_liq=str(date.date()))
        if reserved >= 1 and not out["reserve_liq"]:
            out.update(reserve_liq=True, first_reserved_liq=str(date.date()))
        if equity <= value * (.01 + fut_cost):
            out["sensitivity_1pct_liq"] = True
    return out


def replay(fut, spot, delivery, xd, cov, spot_cost=SPOT_COST):
    r = {"code": f"{delivery:%y%m%d}", "delivery": delivery, "exit_dte": xd,
         "partial": cov["partial"], "entered": False, "status": "NO SIGNAL"}
    if fut.empty:
        return r | {"status": "MISSING VISION"}
    df = fut.join(spot, how="inner", lsuffix="_f", rsuffix="_s").dropna()
    df = df[df.index <= pd.Timestamp(delivery)]
    if df.empty:
        return r | {"status": "NO SPOT OVERLAP"}
    dte = (pd.Timestamp(delivery) - df.index).days
    basis = df.close_f / df.close_s - 1
    # Fixed v2 signal allowance, including in spot-fee sensitivity (no re-selection).
    signal_ann = (basis - TERM_BASIS_ALLOW - ROUND_TRIP) * 365 / np.maximum(dte, 1)
    candidates = df.index[(dte >= MIN_DTE_ENTRY + 1) & (signal_ann > MIN_NET_ANN)]
    if len(candidates) == 0:
        return r
    signal = candidates[0]
    e = signal + pd.Timedelta(days=1)
    x = pd.Timestamp(delivery) - pd.Timedelta(days=xd)
    if e not in df.index or x not in df.index:
        return r | {"status": "MISSING EXACT FILL", "partial": True}
    if x <= e:
        return r | {"status": "NO HOLD WINDOW"}
    path_days = pd.date_range(e, x)
    missing = path_days.difference(df.index)
    if len(missing):
        return r | {"status": f"UNOBSERVABLE PATH ({len(missing)} missing days)", "partial": True}
    Fe, Se = float(df.at[e, "open_f"]), float(df.at[e, "open_s"])
    Fx, Sx = float(df.at[x, "open_f"]), float(df.at[x, "open_s"])
    contracts = 2 * math.floor(Fe / (2 * FACE))
    if contracts <= 0:
        raise ValueError("Insufficient price for declared contract sizing")
    N = contracts * FACE
    Q = N / Fe
    pnl_btc = contracts * FACE * (1 / Fx - 1 / Fe)
    entry_cost_btc = Q * spot_cost + N / Fe * FUT_COST
    end_btc = (Q - entry_cost_btc + pnl_btc - N / Fx * FUT_COST) * (1 - spot_cost)
    gross = (Q + pnl_btc) * Sx / (Q * Se) - 1
    net = end_btc * Sx / (Q * Se) - 1
    btc_net = end_btc / Q - 1
    days = (x - e).days
    # No exit-day future high: position closed at open, before that high is observed.
    path = [(t, float(df.at[t, "high_f"])) for t in pd.date_range(e, x - pd.Timedelta(days=1))]
    path.append((x, Fx))
    walks = {L: margin_walk(path, Fe, Q, L * N, spot_cost) for L in LEVS}
    return r | {"entered": True, "status": "ENTERED", "signal": signal.date(), "entry": e.date(),
                "exit": x.date(), "days": days, "dte_entry": (pd.Timestamp(delivery)-e).days,
                "basis_signal": float(basis.at[signal]), "basis_entry": Fe/Se-1,
                "terminal_basis": Fx/Sx-1, "Fe": Fe, "Se": Se, "Fx": Fx, "Sx": Sx,
                "contracts": contracts, "Q": Q, "capital": Q*Se, "pnl_btc": pnl_btc,
                "pnl_usd": pnl_btc*Sx, "gross": gross, "net": net,
                "net_ann": net*365/days, "btc_net": btc_net, "btc_ann": btc_net*365/days,
                "walks": walks, "adverse_high": max(m for _, m in path)/Fe-1}


def aggregate(rows):
    if not rows:
        return {"n": 0}
    anns = np.array([r["net_ann"] for r in rows])
    rng = np.random.default_rng(cfg.BOOT_SEED)
    boot = anns[rng.integers(0, len(anns), size=(10_000, len(anns)))].mean(axis=1)
    loyo = {y: float(np.mean([r["net_ann"] for r in rows if r["delivery"].year != y]))
            if any(r["delivery"].year != y for r in rows) else math.nan
            for y in sorted({r["delivery"].year for r in rows})}
    def split(after):
        vals = [r["net_ann"] for r in rows if (r["delivery"].year >= 2024) == after]
        return float(np.mean(vals)) if vals else math.nan
    return {"n": len(rows), "pos": sum(r["net"] > 0 for r in rows), "mean": float(anns.mean()),
            "btc_mean": float(np.mean([r["btc_ann"] for r in rows])),
            "ci_lo": float(np.percentile(boot, 2.5)), "ci_hi": float(np.percentile(boot, 97.5)),
            "worst": min(r["net"] for r in rows), "worst_ann": float(anns.min()),
            "loyo": loyo, "pre": split(False), "post": split(True)}


def mechanics_checks():
    # Analytical invariants catch inverse sign/unit mistakes and leverage-path errors.
    for Fe in (20_000., 100_000.):
        Q, N = 1., Fe
        for mark in (Fe*.25, Fe, Fe*3, Fe*100):
            equity = Q + N*(1/mark-1/Fe)
            assert np.isclose(equity*mark, N)
            assert np.isclose(maintenance(N/mark)[0]/equity, .004)
        for Se, Fx, Sx in ((Fe*.98, Fe*.5, Fe*.5), (Fe*.98, Fe*2, Fe*2)):
            assert np.isclose((Q+N*(1/Fx-1/Fe))*Sx/(Q*Se)-1, Fe/Se-1)
        p = [(pd.Timestamp("2024-01-01"), Fe*1.1), (pd.Timestamp("2024-01-02"), Fe*2.1)]
        assert not margin_walk(p, Fe, Q, N)["liq"]
        assert margin_walk(p, Fe, Q, 2*N)["liq"]
    assert np.isclose(maintenance(15)[0], 10*.004+5*.005)
    # Synthetic execution checks: close signal never fills across a calendar gap,
    # and a high occurring after the scheduled exit open cannot liquidate a trade.
    delivery = dt.date(2024, 3, 29)
    ix = pd.date_range("2024-01-01", pd.Timestamp(delivery))
    f = pd.DataFrame({"open": 11_000., "high": 11_000., "low": 11_000., "close": 11_000.}, index=ix)
    s = pd.DataFrame({"open": 10_000., "high": 10_000., "low": 10_000., "close": 10_000.}, index=ix)
    cov = {"partial": False}
    missing_fill = replay(f.drop(ix[1]), s, delivery, 5, cov)
    assert not missing_fill["entered"] and missing_fill["status"] == "MISSING EXACT FILL"
    exit_date = pd.Timestamp(delivery) - pd.Timedelta(days=5)
    f.at[exit_date, "high"] = 1_000_000.
    result = replay(f, s, delivery, 5, cov)
    assert result["entered"] and not result["walks"][2.]["liq"]
    assert np.isclose(result["pnl_usd"], result["pnl_btc"] * result["Sx"])
    assert np.isclose(1 + result["net"], (1 + result["btc_net"]) * result["Sx"] / result["Se"])
    print("Mechanics checks: inverse PnL, USD hedge, cumulative tiers, 1x/2x liquidation PASS", flush=True)


def write_report(recs, covers, manifest, output):
    full = [r for r in recs if r["entered"] and not r["partial"]]
    part = [r for r in recs if r["entered"] and r["partial"]]
    family = {xd: aggregate([r for r in full if r["exit_dte"] == xd]) for xd in EXIT_DTES+(0,)}
    a5 = family[5]
    complete_family = all(family[x]["n"] for x in EXIT_DTES)
    worst = min((family[x]["mean"] for x in EXIT_DTES if family[x]["n"]), default=math.nan)
    kill = bool(complete_family and worst > MIN_NET_ANN and a5["pos"]/a5["n"] >= .8
                and a5["ci_lo"] > 0 and all(v > 0 for v in a5["loyo"].values()))
    liq1 = any(r["walks"][1.]["reserve_liq"] for r in full+part)
    passes = kill and worst > CASH_YIELD and not liq1
    verdict = "PASS — COIN-M rescues carry on observed 1x capital paths" if passes else "DEAD — COIN-M does NOT pass the preregistered carry rescue test"
    lines = [PREREG, "## Exit family (FULL, 1x)", "",
             "| DTE | n | USD positive | USD mean ann ROC | BTC mean ann | USD CI95 | worst USD net | pre-2024 | post-2024 | LOYO min |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for xd, a in family.items():
        if not a["n"]:
            lines.append(f"| {xd if xd else 'hold proxy'} | 0 | — | — | — | — | — | — | — | — |")
            continue
        lines.append(f"| {xd if xd else 'hold proxy'} | {a['n']} | {a['pos']}/{a['n']} | {a['mean']:+.2%} | {a['btc_mean']:+.2%} | [{a['ci_lo']:+.2%}, {a['ci_hi']:+.2%}] | {a['worst']:+.3%} | {a['pre']:+.2%} | {a['post']:+.2%} | {min(a['loyo'].values()):+.2%} |")
    lines += ["", f"**Family-worst USD ROC: {worst:+.2%}/yr.** DTE5 LOYO: " +
              (", ".join(f"drop {y}: {v:+.2%}" for y,v in a5["loyo"].items()) if a5["n"] else "unavailable"),
              "", "## Every contract (DTE5; PARTIAL never enters the verdict)", "",
              "| contract | bucket/status | entry → exit | DTE entry | signal basis | actual entry basis | gross USD | net USD | USD ann ROC | BTC net / ann | inverse PnL BTC / USD | capital USD |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    r5 = [r for r in recs if r["exit_dte"] == 5]
    for r in r5:
        bucket = "PARTIAL" if r["partial"] else "FULL"
        if not r["entered"]:
            lines.append(f"| {r['code']} | {bucket}: {r['status']} | — | — | — | — | — | — | — | — | — | — |")
        else:
            lines.append(f"| {r['code']} | {bucket} | {r['entry']} → {r['exit']} | {r['dte_entry']} | {r['basis_signal']:+.2%} | {r['basis_entry']:+.2%} | {r['gross']:+.3%} | {r['net']:+.3%} | {r['net_ann']:+.2%} | {r['btc_net']:+.2%} / {r['btc_ann']:+.2%} | {r['pnl_btc']:+.6f} / {r['pnl_usd']:+.2f} | {r['capital']:.2f} |")
    losers = [r["code"] for r in r5 if r["entered"] and r["net"] <= 0]
    lines += ["", "USD losers (DTE5, including PARTIAL): " + (", ".join(losers) or "none") + ".",
              "BTC losses are listed explicitly above; BTC-denominated loss does not imply USD carry loss.",
              "", "## PARTIAL exit family (descriptive)", "",
              "| DTE | entered | positive USD | USD mean ann | BTC mean ann |", "|---|---|---|---|---|"]
    for xd in EXIT_DTES+(0,):
        a = aggregate([r for r in part if r["exit_dte"] == xd])
        lines.append(f"| {xd if xd else 'hold proxy'} | {a['n']} | " +
                     (f"{a['pos']}/{a['n']} | {a['mean']:+.2%} | {a['btc_mean']:+.2%} |" if a["n"] else "— | — | — |"))
    lines += ["", "## Liquidation by leverage (observed paths; ratio threshold 100%)", "",
              "| bucket / exit | leverage | paths | maintenance-only hits | with exit-cost reserve | peak raw margin ratio | peak reserved ratio | max BTC position value | max tier |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for bucket, sub in (("FULL", full), ("PARTIAL observed", part)):
        for xd in EXIT_DTES+(0,):
            rs = [r for r in sub if r["exit_dte"] == xd]
            if not rs:
                continue
            for L in LEVS:
                ws = [r["walks"][L] for r in rs]
                lines.append(f"| {bucket} / {xd if xd else 'hold'} | {L:g}x | {len(ws)} | {sum(w['liq'] for w in ws)} | {sum(w['reserve_liq'] for w in ws)} | {max(w['max_ratio'] for w in ws):.2%} | {max(w['max_reserved_ratio'] for w in ws):.2%} | {max(w['max_value'] for w in ws):.4f} | {max(w['max_tier'] for w in ws)} |")
    lines += ["", "First hits, DTE5 (raw / reserved); — means observed and survived, UNKNOWN means no complete trade path:", "",
              "| contract | 1x | 1.5x | 2x |", "|---|---|---|---|"]
    for r in r5:
        vals = [f"{r['walks'][L]['first_liq']} / {r['walks'][L]['first_reserved_liq']}" if r["entered"]
                else ("NO POSITION" if not r["partial"] else "UNKNOWN") for L in LEVS]
        lines.append(f"| {r['code']} | " + " | ".join(vals) + " |")
    lines += ["", f"1% flat maintenance + exit reserve sensitivity: {sum(r['walks'][1.]['sensitivity_1pct_liq'] for r in full)}/{len(full)} FULL trade paths hit at 1x.",
              "Counts across exits are overlapping observations, not independent contracts. At >1x collateral is the same Q BTC but the short is larger; this is not a USD-neutral carry position.",
              "", "## Capital comparison (existing reports, different data windows/universes)", "",
              "| model | capital per $1 spot value | ann return | observed liquidation |", "|---|---|---|---|",
              f"| COIN-M, family-worst FULL | $1 | {worst:+.2%} | {'YES' if liq1 else 'none on observed 1x paths'} |",
              f"| COIN-M, DTE5 FULL | $1 | {a5['mean'] if a5['n'] else math.nan:+.2%} | same daily proxy |",
              "| USD-M v2, family-worst (archived, 8 contracts) | $1 spot denominator, collateral excluded | +10.1% | short not independently funded |",
              "| USD-M margin engine, DTE5 c=1.50 (archived, 8 contracts) | $2.50 | +4.1% | 0/8; c selected with hindsight |",
              "| USD-M margin engine, DTE5 c=2.00 | $3 | +3.4% | 0/8 |",
              "| USD-M portfolio-margin upper bound | $1.10 | +9.3% | modelled |",
              "| declared cash hurdle | $1 | +4.5% | not modelled here |", "",
              "Sources: [v2 archived result](BASIS_CARRY_V2_BTCUSDT_2026-08-19.md), "
              "[margin-engine result](BASIS_MARGIN_ENGINE_BTCUSDT_2026-10-15.md). "
              "These archived USD-M results are read-only benchmarks; not rerun or presented as a matched sample."]
    old_codes = {"240329", "240628", "240927", "241227", "250328", "250627", "251226", "260327"}
    common = [r for r in full if r["exit_dte"] == 5 and r["code"] in old_codes]
    a = aggregate(common)
    if a["n"]:
        lines += [f"COIN-M DTE5 on {a['n']}/8 archived USD-M delivery codes: {a['mean']:+.2%}/yr "
                  "(delivery-matched only; entry dates differ)."]
    lines += ["", "## Data coverage and gaps", "",
              "Spot files combined, range 2023-01-01 through 2026-10-14. Later supplemental file takes precedence "
              "on overlaps. One revision found: 2026-06-06 close 60,593.99 in original versus 60,884.62 in "
              "supplemental (which has explicit close_time); original terminal row appears to be an unfinished bar. "
              "No spot data before 2023; no additional downloads of spot or substitution of perpetual futures.", "",
              "| contract | futures first / last | first common DTE | bucket | reason |", "|---|---|---|---|---|"]
    gap_details = []
    for d,c in covers.items():
        lines.append(f"| {d:%y%m%d} | {c['first']} / {c['last']} | {c['first_dte']} | {'PARTIAL' if c['partial'] else 'FULL'} | {c['reason']} |")
        if c["fut_gaps"]:
            gap_details.append(f"Missing futures dates {d:%y%m%d}: {', '.join(c['fut_gaps'])}.")
        if c["joint_gaps"]:
            gap_details.append(f"Missing common dates {d:%y%m%d}: {', '.join(c['joint_gaps'])}.")
    lines += [""] + gap_details
    counts = {s: sum(m["status"] == s for m in manifest) for s in ("OK", "404")}
    lines += ["", f"Monthly requests: {len(manifest)}; available {counts['OK']}; HTTP404 {counts['404']}; "
              f"other errors {sum(m['status'].startswith('ERROR') for m in manifest)}. "
              "404s before listing are expected, not manufactured missing daily bars. All monthly statuses/URLs "
              "are in backtest/data/basis_cm/download_manifest_2026-10-15.json. Raw ZIPs retained; missing URLs cached as dated .missing.json files.",
              "", f"## VERDICT: **{verdict}**", "",
              "This is conditional on the observed daily price proxy and frozen fee/tier assumptions. "
              "It does not establish real mark-price liquidation immunity, order-book capacity, historical account "
              "margin settings, or a portfolio CAGR. Missing contracts cannot be declared liquidation-free.",
              "", "## Actual printed run output", "", "```text", "\n".join(output), "```", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return family, worst, verdict, full, part


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    # Materialize declared prereg before accessing prices. Never edit pre-existing repo files.
    if not REPORT.exists():
        REPORT.write_text(PREREG + "\nResults pending first run.\n", encoding="utf-8")
    mechanics_checks()
    spot = spot_ohlc()
    ds = list(deliveries())
    futures, manifest = download_universe(ds)
    recs, covers = [], {}
    for d in ds:
        fut, records = futures[d]
        cov = coverage(fut, spot, d, records)
        covers[d] = cov
        for xd in EXIT_DTES+(0,):
            recs.append(replay(fut, spot, d, xd, cov))
    full = [r for r in recs if r["entered"] and not r["partial"]]
    fam = {xd: aggregate([r for r in full if r["exit_dte"] == xd]) for xd in EXIT_DTES+(0,)}
    output = ["Mechanics checks: inverse PnL, USD hedge, cumulative tiers, 1x/2x liquidation PASS",
              f"As-of {ASOF}; settled quarterly contracts checked: {len(ds)}",
              f"Spot coverage: {spot.index[0].date()} through {spot.index[-1].date()}",
              f"Cost allowance: {ROUND_TRIP:.2%}; CM futures leg {FUT_COST:.2%}; spot leg {SPOT_COST:.2%}"]
    for xd, a in fam.items():
        output.append(f"FULL exit={'hold' if xd == 0 else xd}: n={a['n']} " +
                      (f"positive={a['pos']}/{a['n']} USD_ROC_ann={a['mean']:+.4%} BTC_ann={a['btc_mean']:+.4%} "
                       f"CI95=[{a['ci_lo']:+.4%},{a['ci_hi']:+.4%}]" if a["n"] else "NO EVIDENCE"))
    for L in LEVS:
        rs = [r for r in full if r["exit_dte"] == 5]
        output.append(f"FULL DTE5 leverage={L:g}x: liquidation={sum(r['walks'][L]['liq'] for r in rs)}/{len(rs)}; "
                      f"with_exit_reserve={sum(r['walks'][L]['reserve_liq'] for r in rs)}/{len(rs)}")
    partial_codes = [f"{d:%y%m%d}" for d,c in covers.items() if c["partial"]]
    output.append("PARTIAL contracts: " + (", ".join(partial_codes) or "none"))
    output.append("USD losers DTE5: " + (", ".join(r["code"] for r in recs if r["entered"] and r["exit_dte"]==5 and r["net"] <= 0) or "none"))
    # Report is generated, then actual summary output is recorded verbatim in its final block.
    _, worst, verdict, _, _ = write_report(recs, covers, manifest, [])
    output += [f"VERDICT: {verdict}", f"1x family-worst USD ROC {worst:+.4%}/yr vs USD-M margin engine +4.1%/yr", f"wrote -> {REPORT}"]
    write_report(recs, covers, manifest, output)
    print("\n".join(output), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
