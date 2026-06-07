"""Fetch DEEP history 2018-01 -> 2021-01 (4H) for majors that existed then.
Combined with existing 2021-2026 data -> full 2018-2026 to test the 2018 bear + 2019-20 chop regime."""
import time, csv
from pathlib import Path
import requests
OUT=Path(__file__).parent/"data"
# majors with Binance history back to ~2018
MAJORS=["BTCUSDT","ETHUSDT","LTCUSDT","XRPUSDT","BNBUSDT","ADAUSDT","EOSUSDT","NEOUSDT","XLMUSDT","TRXUSDT"]
START=1514764800000  # 2018-01-01
END  =1609459200000  # 2021-01-01
BASE="https://api.binance.com/api/v3/klines"

def fetch(sym):
    rows=[]; start=START
    while start<END:
        try:
            r=requests.get(BASE,params={"symbol":sym,"interval":"4h","startTime":start,"endTime":END,"limit":1000},timeout=20)
            if r.status_code!=200: return rows
            d=r.json()
        except Exception: return rows
        if not d: break
        rows.extend(d)
        if len(d)<1000: break
        start=d[-1][0]+1; time.sleep(0.12)
    return rows

for sym in MAJORS:
    path=OUT/f"{sym}_deep_4h.csv"
    if path.exists(): continue
    rows=fetch(sym)
    if not rows: print(f"{sym}: no deep data"); continue
    with open(path,"w",newline="") as f:
        w=csv.writer(f); w.writerow(["open_time","open","high","low","close","volume"])
        for k in rows: w.writerow([k[0],k[1],k[2],k[3],k[4],k[5]])
    print(f"{sym}: {len(rows)} bars")
print("done")
