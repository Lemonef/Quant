"""Read-only live COIN-M quarterly basis entry scanner."""

import datetime as dt
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Binance's public responses are UTF-8; avoid cp874 console encoding failures.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

HERE = __file__
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(HERE)))
from basis_coinm_test import (  # noqa: E402
    MIN_DTE_ENTRY,
    MIN_NET_ANN,
    ROUND_TRIP,
    TERM_BASIS_ALLOW,
)

EXCHANGE_INFO = "https://dapi.binance.com/dapi/v1/exchangeInfo"
PREMIUM_INDEX = "https://dapi.binance.com/dapi/v1/premiumIndex"
SPOT_TICKER = "https://api.binance.com/api/v3/ticker/price"
COINS = ("BTC", "ETH")


def get_json(url):
    try:
        with urlopen(Request(url, headers={"User-Agent": "basis-coinm-now/1.0"}), timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"endpoint unreachable: {url} ({exc})") from exc


def main():
    try:
        exchange = get_json(EXCHANGE_INFO)
        symbols = {
            symbol["symbol"]: symbol
            for symbol in exchange.get("symbols", [])
            if symbol.get("baseAsset") in COINS
            and symbol.get("contractType") in ("CURRENT_QUARTER", "NEXT_QUARTER")
        }

        marks = get_json(PREMIUM_INDEX)
        mark_prices = {
            row["symbol"]: float(row["markPrice"])
            for row in marks
            if row.get("symbol") in symbols
        }
        spot_prices = {}
        for coin in COINS:
            ticker = get_json(f"{SPOT_TICKER}?symbol={coin}USDT")
            spot_prices[coin] = float(ticker["price"])

        today = dt.datetime.now(dt.timezone.utc).date()
        rows = []
        for symbol, info in symbols.items():
            if symbol not in mark_prices:
                raise RuntimeError(f"endpoint unreachable: {PREMIUM_INDEX} (missing {symbol})")
            delivery = dt.datetime.fromtimestamp(info["deliveryDate"] / 1000, dt.timezone.utc).date()
            dte = (delivery - today).days
            spot = spot_prices[info["baseAsset"]]
            futures = mark_prices[symbol]
            basis = futures / spot - 1.0
            annualised = (basis - TERM_BASIS_ALLOW - ROUND_TRIP) * 365.0 / max(dte, 1)
            qualifies = dte >= MIN_DTE_ENTRY and annualised > MIN_NET_ANN
            rows.append((info["baseAsset"], symbol, dte, spot, futures, basis, annualised, qualifies))

        rows.sort(key=lambda row: (COINS.index(row[0]), row[2], row[1]))
        print("symbol | contract | DTE | spot | futures | basis | annualised net | qualifies")
        for coin, contract, dte, spot, futures, basis, annualised, qualifies in rows:
            print(f"{coin} | {contract} | {dte} | {spot:.2f} | {futures:.2f} | "
                  f"{basis:+.4%} | {annualised:+.2%}/yr | {'yes' if qualifies else 'no'}")

        for coin in COINS:
            candidates = [row for row in rows if row[0] == coin]
            best = max(candidates, key=lambda row: row[6])
            if any(row[7] for row in candidates):
                entry = next(row for row in candidates if row[7])
                print(f"ENTRY AVAILABLE: {entry[1]}")
            else:
                print(f"NO ENTRY: best is {best[1]} at {best[6]:.2%}/yr vs hurdle {MIN_NET_ANN:.0%}")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Research signal only. Live entry requires: Binance COIN-M access for this account, a decision on counterparty exposure, and the operational risks in")
    print("research/overnight-2026-10-15.md (ADL, pre-delivery liquidity).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
