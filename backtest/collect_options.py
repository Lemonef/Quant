"""Deribit options snapshot collector — builds the history the public API lacks.

The public API serves the CURRENT chain only (mark IV, open interest, greeks)
plus DVOL history; every options-derived factor candidate (GEX, max-pain,
put/call OI, skew, IV percentile) needs chain HISTORY, so collection must run
daily and accrue. Each run appends one row per live instrument to
backtest/data/options/<CCY>_chain_<YYYY-MM>.csv (monthly files keep any single
CSV small) and one row to <CCY>_dvol.csv. Designed for the GitHub Actions cron
(free, machine-independent); running it twice in a day just adds a second
snapshot — downstream consumers de-duplicate on snap_ts.

Stdlib only (urllib/csv/json) — no venv needed in CI.
"""
import csv, json, time, urllib.request
from pathlib import Path

API = "https://www.deribit.com/api/v2/public"
CURRENCIES = ("BTC", "ETH")
OUT = Path(__file__).resolve().parent / "data" / "options"

CHAIN_FIELDS = ["snap_ts", "instrument_name", "underlying_price", "mark_price",
                "mark_iv", "open_interest", "bid_price", "ask_price",
                "volume", "volume_usd"]


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)["result"]


def collect(now_ms=None):
    now_ms = now_ms or int(time.time() * 1000)
    OUT.mkdir(parents=True, exist_ok=True)
    month = time.strftime("%Y-%m", time.gmtime(now_ms / 1000))
    for ccy in CURRENCIES:
        rows = _get(f"{API}/get_book_summary_by_currency?currency={ccy}&kind=option")
        path = OUT / f"{ccy}_chain_{month}.csv"
        new = not path.exists()
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(CHAIN_FIELDS)
            for r in rows:
                w.writerow([now_ms] + [r.get(k) for k in CHAIN_FIELDS[1:]])
        dvol = _get(f"{API}/get_volatility_index_data?currency={ccy}"
                    f"&start_timestamp={now_ms - 86_400_000}&end_timestamp={now_ms}"
                    "&resolution=3600")["data"]
        dpath = OUT / f"{ccy}_dvol.csv"
        seen = set()
        if dpath.exists():
            with open(dpath) as f:
                seen = {ln.split(",", 1)[0] for ln in f.read().splitlines()[1:]}
        with open(dpath, "a", newline="") as f:
            w = csv.writer(f)
            if not seen:
                w.writerow(["ts", "open", "high", "low", "close"])
            for ts, o, h, l, c in dvol:
                if str(ts) not in seen:
                    w.writerow([ts, o, h, l, c])
        print(f"{ccy}: {len(rows)} instruments -> {path.name}; dvol rows appended")


if __name__ == "__main__":
    collect()
