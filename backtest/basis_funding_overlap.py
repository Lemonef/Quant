"""Matched-sample overlap of the COIN-M quarterly-basis and live funding sleeves.

Run from the repository root: python -B backtest/basis_funding_overlap.py
This is deliberately read-only with respect to the live bot.  It uses the cached
COIN-M bars and the local funding CSVs, and writes only its dated report.
"""
import io
import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

import basis_coinm_test as cm


# Declared before calculating results.  These are interpretation thresholds for
# correlations of return streams, not statistical significance cut-offs.
SAME_PREMIUM = 0.60
DIFFERENT_PREMIUM = 0.30
ASOF = "2026-10-15"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "backtest_results" / f"BASIS_FUNDING_OVERLAP_{ASOF}.md"


def cached_futures(deliveries):
    """Load precisely the already-cached COIN-M daily bars; never download."""
    out = {}
    for delivery in deliveries:
        symbol = f"BTCUSD_{delivery:%y%m%d}"
        rows, records = [], []
        for p in sorted(cm.DATA.glob(f"{symbol}-1d-*.zip")):
            with zipfile.ZipFile(p) as z:
                for member in z.namelist():
                    if not member.endswith(".csv"):
                        continue
                    for line in io.TextIOWrapper(z.open(member), encoding="utf-8-sig"):
                        c = line.rstrip().split(",")
                        if c and c[0].isdigit():
                            rows.append((int(c[0]), *(float(x) for x in c[1:5])))
            records.append({"symbol": symbol, "month": p.name[-11:-4], "status": "OK", "rows": []})
        # Preserve missing-cache evidence for coverage(), without contacting Vision.
        for p in sorted(cm.DATA.glob(f"{symbol}-1d-*.zip.missing.json")):
            records.append({"symbol": symbol, "month": p.name[-24:-17], "status": "404", "rows": []})
        if rows:
            f = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
            f = f.drop_duplicates("ts").sort_values("ts")
            f["date"] = pd.to_datetime(f.ts, unit="ms").dt.normalize()
            f = f.set_index("date").drop(columns="ts")
            out[delivery] = (f[f.index <= pd.Timestamp(delivery)], records)
        else:
            out[delivery] = (pd.DataFrame(), records)
    return out


def basis_returns():
    """DTE5, FULL positions from basis_coinm_test, marked daily then closed at DTE5 open."""
    spot = cm.spot_ohlc()
    deliveries = list(cm.deliveries())
    futures = cached_futures(deliveries)
    rows, held = [], []
    for delivery in deliveries:
        fut, records = futures[delivery]
        cov = cm.coverage(fut, spot, delivery, records)
        trade = cm.replay(fut, spot, delivery, 5, cov)
        if not (trade["entered"] and not trade["partial"]):
            continue
        e, x = pd.Timestamp(trade["entry"]), pd.Timestamp(trade["exit"])
        df = fut.join(spot, how="inner", lsuffix="_f", rsuffix="_s")
        # At each held close, inverse short + spot wealth is marked in USD.  The
        # entry fees are in the BTC wallet; the prescribed Q*Fe*St/Ft identity is
        # therefore adjusted only by that actual, already-paid BTC fee.
        notional = trade["contracts"] * cm.FACE
        fee_btc = trade["Q"] * cm.SPOT_COST + notional / trade["Fe"] * cm.FUT_COST
        wealth = []
        for d in pd.date_range(e, x - pd.Timedelta(days=1)):
            F, S = float(df.at[d, "close_f"]), float(df.at[d, "close_s"])
            wealth.append((d, (trade["Q"] * trade["Fe"] / F - fee_btc) * S))
        # The reference strategy exits at DTE5 OPEN; do not pretend it held the
        # contract through that day's close.  Apply its futures exit and spot-sale costs.
        F, S = float(df.at[x, "open_f"]), float(df.at[x, "open_s"])
        exit_btc = (trade["Q"] * trade["Fe"] / F - fee_btc - notional / F * cm.FUT_COST) * (1 - cm.SPOT_COST)
        wealth.append((x, exit_btc * S))
        prev = trade["Q"] * trade["Se"]
        for d, w in wealth:
            rows.append((d, w / prev - 1.0, delivery.strftime("%Y-%m-%d")))
            prev = w
        held.append(trade)
    result = pd.DataFrame(rows, columns=["date", "basis", "delivery"]).set_index("date").sort_index()
    # More than one dated contract can be live on a calendar day.  Each source
    # position is approximately one BTC of capital, so the sleeve's daily return
    # is the equal-capital mean of its simultaneously marked positions.
    result = result.groupby(level=0).basis.mean().to_frame()
    return result, held


def funding_daily():
    """Exact 1x fund_block loop logic, then compound the three 8h returns per UTC day."""
    btc = pd.read_csv(HERE / "data" / "BTCUSDT_funding.csv")
    eth = pd.read_csv(HERE / "data" / "ETHUSDT_funding.csv")
    b = dict(zip(btc.fundingTime.astype("int64"), btc.fundingRate.astype(float)))
    e = dict(zip(eth.fundingTime.astype("int64"), eth.fundingRate.astype(float)))
    history, pos, gate = [], 0, 0.3
    periods = []
    # This exactly mirrors paper_bot.py: only matched BTC/ETH prints, trailing
    # average before the current print, and costs charged before multiplying equity.
    for t in sorted(b):
        if t not in e:
            continue
        composite = (b[t] + e[t]) / 2.0
        signal = float(np.mean(history[-21:])) if history else 0.0
        want = pos
        if pos == 0 and signal > 0.00003:
            want = 1
        elif pos == 1 and signal < -0.00003:
            want = 0
        newgate = gate
        if gate < 1.0 and signal >= 0.00005:
            newgate = 1.0
        elif gate >= 1.0 and signal < 0.000025:
            newgate = 0.3
        side_cost = 0.003 if want != pos else 0.0  # SWITCH_COST = 2 * COST; COST=.0015
        gate_cost = 0.003 * abs(newgate - gate) if (pos == 1 and want == 1) else 0.0
        periods.append((pd.to_datetime(t, unit="ms").normalize(), want * newgate * composite - side_cost - gate_cost))
        pos, gate = want, newgate
        history.append(composite)
    p = pd.DataFrame(periods, columns=["date", "ret"])
    return p.groupby("date").ret.apply(lambda x: float(np.prod(1 + x) - 1)).rename("funding")


def sharpe(r):
    return float(r.mean() / r.std(ddof=1) * math.sqrt(365)) if len(r) > 1 and r.std(ddof=1) else math.nan


def drawdown(r):
    equity = (1 + r).cumprod()
    return equity / equity.cummax() - 1


def verdict(correlation):
    if correlation > SAME_PREMIUM:
        return "largely the same premium"
    if correlation < DIFFERENT_PREMIUM:
        return "genuinely different"
    return "partially overlapping"


def main():
    br, trades = basis_returns()
    fr = funding_daily()
    common = br[["basis"]].join(fr, how="inner").dropna()
    r30 = (1 + common[["basis", "funding"]]).rolling(30).apply(np.prod, raw=True) - 1
    r30 = r30.dropna()
    dd = pd.DataFrame({"basis": drawdown(common.basis), "funding": drawdown(common.funding)})
    combo = (common.basis + common.funding) / 2.0

    # The supplied quarterly-close level is independently useful because it
    # extends before the COIN-M position sample.  Funding is averaged over the
    # preceding 90 eight-hour prints (30 calendar days), with no look-ahead.
    q = pd.read_csv(HERE / "data" / "options" / "btc_quarterly_basis_daily.csv", parse_dates=["date"]).set_index("date")
    spot = cm.spot_ohlc().close.rename("spot")
    level = q.join(spot, how="inner")
    level["basis_level"] = level.quarterly_close / level.spot - 1.0
    btc_rates = pd.read_csv(HERE / "data" / "BTCUSDT_funding.csv")
    raw = pd.DataFrame({"date": pd.to_datetime(btc_rates.fundingTime, unit="ms").dt.normalize(),
                        "rate": btc_rates.fundingRate.astype(float)})
    # Use all prints through the day; rolling then retain its last observation.
    raw["trail30_funding"] = raw.rate.rolling(90, min_periods=90).mean()
    daily_trail = raw.groupby("date").trail30_funding.last()
    level_funding = level.join(daily_trail, how="inner").dropna()

    daily_corr = common.corr().at["basis", "funding"]
    corr30 = r30.corr().at["basis", "funding"]
    dd_corr = dd.corr().at["basis", "funding"]
    level_corr = level_funding[["basis_level", "trail30_funding"]].corr().iat[0, 1]
    lines = [
        f"# COIN-M basis vs perp-funding overlap — {ASOF}", "",
        "## Preregistered interpretation thresholds", "",
        f"- Correlation > {SAME_PREMIUM:.1f}: **largely the same premium**.",
        f"- Correlation < {DIFFERENT_PREMIUM:.1f}: **genuinely different**.",
        f"- Otherwise: **partially overlapping**.", "",
        "## Matched construction and coverage", "",
        "COIN-M is the same FULL DTE5 1x positions selected by `basis_coinm_test.py`: long BTC spot and short the inverse quarterly. Daily USD wealth is marked from the daily closes as `Q * F_entry * S_t / F_t`, less the already-paid entry BTC fees; the DTE5 exit observation uses the source strategy's open exit and exit costs. When dated contracts overlap, their approximately one-BTC-capital daily returns are equal-capital averaged. Funding is the live `paper_bot.py` 1x `fund_block` rule exactly: matched BTC/ETH prints, equal-weight funding, trailing 21-print side signal, 30%/100% hysteretic gate, and 0.30% two-leg costs on side changes and resizes. It is aggregated from 8h returns to UTC daily compounded returns.", "",
        f"- Basis held windows: {len(trades)} FULL DTE5 trades; {br.index.min().date()} to {br.index.max().date()}, {len(br)} marked trading days.",
        f"- Matched active days: {len(common)}; {common.index.min().date()} to {common.index.max().date()}. No flat days are inserted between quarterly holds.",
        f"- Funding input coverage: 2021-01-01 to 2026-06-06; its matched-day returns are used above.", "",
        "## Return-stream overlap", "",
        f"- Daily-return correlation: **{daily_corr:+.3f}**.",
        f"- 30-observation rolling-return correlation: **{corr30:+.3f}**.",
        f"- Drawdown-depth correlation (each sleeve's cumulative equity drawdown on the matched active-day sequence): **{dd_corr:+.3f}**.",
        f"- Classification from daily correlation: **{verdict(daily_corr)}**.", "",
        "## Risk-adjusted comparison", "",
        "Sharpe uses the daily matched observations and is annualised at **365** (no cap).", "",
        f"| sleeve | annualised Sharpe (365) |",
        "|---|---:|",
        f"| COIN-M basis | {sharpe(common.basis):.3f} |",
        f"| Perp funding | {sharpe(common.funding):.3f} |",
        f"| 50/50 daily-return combination | {sharpe(combo):.3f} |", "",
        "## Level-versus-funding test", "",
        f"The quarterly basis level is `quarterly_close / BTC spot close - 1`; funding is the trailing 30-day (90-print) mean BTC perp rate, both aligned at daily close. Coverage is {level_funding.index.min().date()} to {level_funding.index.max().date()}, n={len(level_funding)}. Correlation: **{level_corr:+.3f}**.", "",
        "## Verdict", "",
        f"On matched active days, COIN-M basis and the live funding sleeve are **{verdict(daily_corr)}** by the declared daily-return threshold. The level/funding correlation is reported separately as the leverage-demand diagnostic; it is not substituted for return-stream overlap.", ""
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
