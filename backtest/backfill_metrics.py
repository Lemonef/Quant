"""
backfill_metrics.py — one-shot + incremental Binance Vision positioning-metrics history.

WHY: the live positioning collector (backtest/collect_positioning.py) died 2026-08-10 —
Binance's futures REST API returns HTTP 451 (geo-block) from GitHub's US runners, and its
30-day retention was bleeding history away. Binance Vision (data.binance.vision, CloudFront
CDN, no geo-block) publishes DAILY dumps of the exact same fields at 5-min granularity with
history back to ~2021-01 — so the "history only accrues forward" constraint is gone.

WHAT: for each symbol, downloads every daily metrics zip not yet ingested, aggregates to
ONE ROW PER UTC DAY, and appends to backtest/data/options/{SYM}_metrics_daily.csv:

    date, sum_open_interest, sum_open_interest_value, toptrader_ls_ratio,
    global_ls_ratio, taker_ls_vol_ratio, n_obs

Aggregation: LAST 5-min observation of the day for levels/ratios (matches how the dead
API collector sampled once daily), n_obs recorded so a partial day is visible.
Idempotent: re-running downloads nothing already in the CSV (verify with a double run —
second run must append zero). A missing/404 day is recorded in the skip log and does not
abort the sweep (partial-outage hardening).

Usage:
    python backtest/backfill_metrics.py                # incremental (from last row)
    python backtest/backfill_metrics.py --full         # full history from 2021-01-01
    python backtest/backfill_metrics.py --symbols BTCUSDT,ETHUSDT
"""
import argparse, csv, datetime as dt, io, sys, time, zipfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

HERE = Path(__file__).resolve().parent
OUTDIR = HERE / "data" / "options"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
EARLIEST = dt.date(2021, 1, 1)          # probed 2026-08-18: 2021-01-15 exists, 2020-06-15 404s
BASE = "https://data.binance.vision/data/futures/um/daily/metrics"
COLS = ["date", "sum_open_interest", "sum_open_interest_value", "toptrader_ls_ratio",
        "global_ls_ratio", "taker_ls_vol_ratio", "n_obs"]
PAUSE_S = 0.15                          # CDN courtesy gap
RETRIES = 3


def fetch_day(sym, day):
    """-> aggregated row dict, 'missing' (404), or None (transient failure after retries)."""
    url = f"{BASE}/{sym}/{sym}-metrics-{day.isoformat()}.zip"
    for attempt in range(RETRIES):
        try:
            with urlopen(Request(url, headers={"User-Agent": "quant-backfill/1.0"}),
                         timeout=30) as r:
                raw = r.read()
            break
        except HTTPError as e:
            if e.code == 404:
                return "missing"
            time.sleep(2 ** attempt)
        except URLError:
            time.sleep(2 ** attempt)
    else:
        return None
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        with z.open(z.namelist()[0]) as f:
            rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")))
    if not rows:
        return "missing"
    last = rows[-1]
    return dict(date=day.isoformat(),
                sum_open_interest=last["sum_open_interest"],
                sum_open_interest_value=last["sum_open_interest_value"],
                toptrader_ls_ratio=last["sum_toptrader_long_short_ratio"],
                global_ls_ratio=last["count_long_short_ratio"],
                taker_ls_vol_ratio=last["sum_taker_long_short_vol_ratio"],
                n_obs=len(rows))


def have_dates(path):
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {r["date"] for r in csv.DictReader(f)}


def run(symbols, full):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    yesterday = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    for sym in symbols:
        path = OUTDIR / f"{sym}_metrics_daily.csv"
        seen = have_dates(path)
        # audit #2: ALWAYS enumerate the full span — `todo` is the set difference, so a
        # historical day that failed once is retried on every run, not orphaned
        start = EARLIEST
        days = [start + dt.timedelta(days=i) for i in range((yesterday - start).days + 1)]
        todo = [d for d in days if d.isoformat() not in seen]
        print(f"{sym}: {len(seen)} rows on disk, {len(todo)} days to fetch "
              f"({todo[0] if todo else '-'} .. {todo[-1] if todo else '-'})", flush=True)
        new_file = not path.exists()
        added, missing, failed = 0, [], []
        with path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            if new_file:
                w.writeheader()
            for i, d in enumerate(todo):
                row = fetch_day(sym, d)
                if row == "missing":
                    missing.append(d.isoformat())
                elif row is None:
                    failed.append(d.isoformat())
                else:
                    w.writerow(row); added += 1
                if (i + 1) % 200 == 0:
                    f.flush()
                    print(f"  {sym} {i + 1}/{len(todo)} (+{added}, miss {len(missing)}, "
                          f"fail {len(failed)})", flush=True)
                time.sleep(PAUSE_S)
        print(f"  {sym} DONE: +{added} rows, {len(missing)} missing (404), "
              f"{len(failed)} failed-after-retry", flush=True)
        if failed:
            print(f"  {sym} FAILED DAYS (rerun to fill): {failed[:10]}{'…' if len(failed) > 10 else ''}",
                  flush=True)
    # in-place sort+dedup so incremental appends stay ordered even after gap-fills
    for sym in symbols:
        path = OUTDIR / f"{sym}_metrics_daily.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            rows = {r["date"]: r for r in csv.DictReader(f)}
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            for d in sorted(rows):
                w.writerow(rows[d])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    a = ap.parse_args()
    run([s.strip().upper() for s in a.symbols.split(",") if s.strip()], a.full)
