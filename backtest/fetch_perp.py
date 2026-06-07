"""Fetch Binance PERP (continuous) 4H klines 2021-2026 for coins we have spot+funding for.
Gives spot-perp BASIS -> realistic carry risk."""
import time, csv
from pathlib import Path
import requests
OUT=Path(__file__).parent/"data"
BASE="https://fapi.binance.com/fapi/v1/continuousKlines"
START=1609459200000; END=1780704000000

coins=sorted({p.stem.replace("_funding","") for p in OUT.glob("*_funding.csv")})

def fetch(sym):
    rows=[]; start=START
    while start<END:
        try:
            r=requests.get(BASE,params={"pair":sym,"contractType":"PERPETUAL","interval":"4h","startTime":start,"endTime":END,"limit":1000},timeout=20)
            if r.status_code!=200: return rows
            d=r.json()
        except Exception: return rows
        if not d: break
        rows.extend(d)
        if len(d)<1000: break
        start=d[-1][0]+1; time.sleep(0.1)
    return rows

for sym in coins:
    path=OUT/f"{sym}_perp_4h.csv"
    if path.exists(): continue
    rows=fetch(sym)
    if not rows: print(f"{sym}: no perp"); continue
    with open(path,"w",newline="") as f:
        w=csv.writer(f); w.writerow(["open_time","close"])
        for k in rows: w.writerow([k[0],k[4]])
    print(f"{sym}: {len(rows)} perp bars")
print("done")
