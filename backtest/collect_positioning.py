"""Binance perp positioning collector — the revealed-positioning class's
cheapest member (open interest, global long/short accounts, top-trader
long/short positions). Binance's futures/data endpoints serve only ~30 days of
1d history, so like the options collector this accrues forward; each run pulls
the full available window and de-duplicates on timestamp, which also
self-heals any missed cron days. Appends to
backtest/data/options/<SYMBOL>_positioning.csv (same committed dataset dir).
Stdlib only — no CI dependencies."""
import csv, json, urllib.request
from pathlib import Path

FAPI = "https://fapi.binance.com/futures/data"
# the bot's core traded set; extend deliberately, one symbol = 3 requests/day
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
OUT = Path(__file__).resolve().parent / "data" / "options"
FIELDS = ["timestamp", "sum_oi", "sum_oi_value", "global_long_acct",
          "global_ls_ratio", "top_pos_long_acct", "top_pos_ls_ratio"]


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "positioning-collector"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collect():
    OUT.mkdir(parents=True, exist_ok=True)
    for sym in SYMBOLS:
        # Codex-audit hardening 1: one symbol's outage must not abort the rest
        try:
            oi = {r["timestamp"]: r for r in
                  _get(f"{FAPI}/openInterestHist?symbol={sym}&period=1d&limit=30")}
            gl = {r["timestamp"]: r for r in
                  _get(f"{FAPI}/globalLongShortAccountRatio?symbol={sym}&period=1d&limit=30")}
            tp = {r["timestamp"]: r for r in
                  _get(f"{FAPI}/topLongShortPositionRatio?symbol={sym}&period=1d&limit=30")}
        except Exception as e:
            print(f"WARN {sym}: fetch failed ({e}) — skipped this run, next run backfills")
            continue
        path = OUT / f"{sym}_positioning.csv"
        seen = set()
        if path.exists():
            with open(path) as f:
                seen = {ln.split(",", 1)[0] for ln in f.read().splitlines()[1:]}
        new_rows = 0
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if not seen:
                w.writerow(FIELDS)
            # Codex-audit hardening 2: write only ts present in ALL THREE endpoints —
            # a partial row would be sealed forever by the de-dup and never healed;
            # an unwritten ts is re-fetched inside the 30d window next run
            for ts in sorted(set(oi) & set(gl) & set(tp)):
                if str(ts) in seen:
                    continue
                o, g, t = oi[ts], gl[ts], tp[ts]
                w.writerow([ts, o.get("sumOpenInterest"), o.get("sumOpenInterestValue"),
                            g.get("longAccount"), g.get("longShortRatio"),
                            t.get("longAccount"), t.get("longShortRatio")])
                new_rows += 1
        print(f"{sym}: +{new_rows} rows -> {path.name}")


if __name__ == "__main__":
    collect()
