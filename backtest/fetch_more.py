"""Fetch ~15 more liquid coins, both windows (2021-2022 _bear + 2023-2026), 4H, to expand universe."""
import time, csv
from pathlib import Path
import requests
OUT=Path(__file__).parent/"data"; OUT.mkdir(exist_ok=True)
NEW=["MATICUSDT","DOTUSDT","ATOMUSDT","NEARUSDT","FILUSDT","UNIUSDT","AAVEUSDT","ETCUSDT",
     "XLMUSDT","ALGOUSDT","SANDUSDT","MANAUSDT","FTMUSDT","GALAUSDT","ICPUSDT"]
BASE="https://api.binance.com/api/v3/klines"
WINDOWS={"bear_4h":(1609459200000,1672531200000),"4h":(1672531200000,1780704000000)}

def fetch(sym,iv,a,b):
    rows=[]; start=a
    while start<b:
        try:
            r=requests.get(BASE,params={"symbol":sym,"interval":"4h","startTime":start,"endTime":b,"limit":1000},timeout=20)
            if r.status_code!=200: return rows
            d=r.json()
        except Exception: return rows
        if not d: break
        rows.extend(d)
        if len(d)<1000: break
        start=d[-1][0]+1; time.sleep(0.12)
    return rows

for sym in NEW:
    for suf,(a,b) in WINDOWS.items():
        path=OUT/f"{sym}_{suf}.csv" if suf=="bear_4h" else OUT/f"{sym}_4h.csv"
        if path.exists(): continue
        rows=fetch(sym,suf,a,b)
        if not rows: print(f"{sym} {suf}: NO DATA (skip)"); continue
        with open(path,"w",newline="") as f:
            w=csv.writer(f); w.writerow(["open_time","open","high","low","close","volume"])
            for k in rows: w.writerow([k[0],k[1],k[2],k[3],k[4],k[5]])
        print(f"{sym} {suf}: {len(rows)} bars")
print("done")
