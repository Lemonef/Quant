"""
Paper-trading bot — validated strategy, tracking 1x / 2x / 3x leverage in parallel.
  Donchian 55/20 breakout + 200-MA filter, long-only, ATR stop, ATR-risk sizing.
  ~20-coin Binance basket, 4H, each coin = equal-capital sub-account.
Signals are identical across leverages; only position size differs -> one fetch, 3 accounts.

NO REAL MONEY. Public Binance REST (no key). Persists state_{1,2,3}x.json + equity_{1,2,3}x.csv,
writes web/data.json for the dashboard. Run once per 4H (GitHub Actions) or --loop.
"""
import sys, os, json, time, csv
from datetime import datetime, timezone
from pathlib import Path
import requests, numpy as np, pandas as pd

HERE = Path(__file__).parent

# ---- config ----
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","LINKUSDT",
         "LTCUSDT","DOGEUSDT","MATICUSDT","DOTUSDT","ATOMUSDT","NEARUSDT","FILUSDT","UNIUSDT",
         "ETCUSDT","XLMUSDT","ALGOUSDT","ICPUSDT"]
LEVELS     = [1.0, 2.0, 3.0]   # leverages tracked in parallel
INTERVAL   = "4h"
ENTRY, EXIT = 55, 20
MA_LEN, ADX_MIN, ATR_LEN = 200, 25, 14
ATR_STOP   = 2.5
RISK_PCT   = 5.0
START_EQUITY = 10000.0
COST = 0.001 + 0.0005
BASE = "https://api.binance.com/api/v3/klines"

TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT  = os.environ.get("TG_CHAT", "")
def tg(msg):
    if not TG_TOKEN or not TG_CHAT: return
    try: requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                       data={"chat_id": TG_CHAT, "text": msg}, timeout=10)
    except Exception: pass

def now(): return datetime.now(timezone.utc).isoformat()
def tag(lev): return f"{int(lev)}x"
def state_path(lev): return HERE/f"state_{tag(lev)}.json"
def eqlog_path(lev): return HERE/f"equity_{tag(lev)}.csv"
TRADELOG = HERE/"trades.csv"

def fetch(sym, limit=400):
    r = requests.get(BASE, params={"symbol": sym, "interval": INTERVAL, "limit": limit}, timeout=20)
    r.raise_for_status()
    df = pd.DataFrame(r.json(), columns=["t","o","h","l","c","v","ct","q","n","tb","tq","ig"])
    for x in ["o","h","l","c"]: df[x] = df[x].astype(float)
    return df

def rma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()
def indicators(df):
    h,l,c = df.h, df.l, df.c; pc = c.shift()
    tr = pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    atr = rma(tr, ATR_LEN)
    up = h.diff(); dn = -l.diff()
    plus = np.where((up>dn)&(up>0),up,0.0); minus=np.where((dn>up)&(dn>0),dn,0.0)
    atrx = rma(tr,14)
    pdi = 100*rma(pd.Series(plus,index=df.index),14)/atrx.replace(0,np.nan)
    mdi = 100*rma(pd.Series(minus,index=df.index),14)/atrx.replace(0,np.nan)
    dx = 100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    adx = rma(dx.fillna(0),14)
    return atr, adx, c.rolling(MA_LEN).mean(), h.rolling(ENTRY).max(), l.rolling(EXIT).min()

def load_state(lev):
    p = state_path(lev)
    if p.exists(): return json.loads(p.read_text())
    sub = START_EQUITY/len(COINS)
    return {"coins": {c: {"cash": sub, "units": 0.0, "entry": 0.0, "stop": 0.0, "peak": 0.0} for c in COINS}}

def log_trade(row):
    new = not TRADELOG.exists()
    with open(TRADELOG,"a",newline="") as f:
        w=csv.writer(f)
        if new: w.writerow(["time","lev","coin","action","price","units","reason","pnl"])
        w.writerow(row)

def append_eq(lev, total):
    p = eqlog_path(lev); new = not p.exists()
    with open(p,"a",newline="") as f:
        w=csv.writer(f)
        if new: w.writerow(["time","equity"])
        w.writerow([now(), round(total,2)])

def closed_pnls(levtag):
    out = []
    if TRADELOG.exists():
        with open(TRADELOG) as f:
            r = csv.DictReader(f)
            for row in r:
                if row.get("lev")==levtag and row.get("action")=="SELL" and row.get("pnl"):
                    try: out.append(float(row["pnl"]))
                    except ValueError: pass
    return out

def stats_from_series(series):
    if len(series) < 2: return 0.0, 0.0
    eq = [s[1] for s in series]
    peak = eq[0]; mdd = 0.0
    for v in eq:
        peak = max(peak, v); mdd = min(mdd, v/peak - 1)
    years = len(eq) / (365*6)   # one point per ~4h cycle
    cagr = (eq[-1]/eq[0])**(1/years) - 1 if years > 0 and eq[-1] > 0 else 0.0
    return cagr*100, mdd*100

def write_webdata(states, totals):
    levels = []
    for lev in LEVELS:
        series = []
        p = eqlog_path(lev)
        if p.exists():
            with open(p) as f:
                next(f, None)
                for line in f:
                    a = line.strip().split(",")
                    if len(a)==2: series.append([a[0][:16], round(float(a[1]),2)])
        cagr, mdd = stats_from_series(series)
        pls = closed_pnls(tag(lev))
        wins = [x for x in pls if x > 0]; losses = [x for x in pls if x <= 0]
        wr = (len(wins)/len(pls)*100) if pls else 0.0
        pf = (sum(wins)/abs(sum(losses))) if losses and sum(losses)!=0 else (0.0 if not wins else 999.0)
        levels.append({"lev": tag(lev), "equity": round(totals[lev],2),
                       "pnl_pct": round((totals[lev]/START_EQUITY-1)*100,2),
                       "cagr": round(cagr,1), "maxdd": round(mdd,1),
                       "wr": round(wr,1), "pf": round(pf,2), "trades": len(pls),
                       "series": series})
    s3 = states[LEVELS[-1]]   # positions: same coins across levels; show units at 3x
    positions = [{"coin": c, "units": round(cs["units"],6), "entry": cs["entry"], "stop": cs["stop"]}
                 for c, cs in s3["coins"].items() if cs["units"] > 0]
    data = {"updated": now()[:16], "start": START_EQUITY, "n_coins": len(COINS),
            "levels": levels, "positions": positions}
    web = HERE.parent/"web"; web.mkdir(exist_ok=True)
    (web/"data.json").write_text(json.dumps(data), encoding="utf-8")

def cycle():
    states = {lev: load_state(lev) for lev in LEVELS}
    totals = {lev: 0.0 for lev in LEVELS}
    actions = []
    # BTC master regime: only go long ANYTHING when BTC > its own 200-MA (cuts correlated crashes)
    try:
        bdf = fetch("BTCUSDT"); _,_,bma,_,_ = indicators(bdf); bi = len(bdf)-2
        btc_ok = bool(bdf.c.iloc[bi] > bma.iloc[bi])
    except Exception:
        btc_ok = True
    for c in COINS:
        try: df = fetch(c)
        except Exception as e:
            print(f"{c}: fetch fail {e}")
            for lev in LEVELS: totals[lev] += states[lev]["coins"][c]["cash"]
            continue
        atr,adx,ma,donHi,donLo = indicators(df)
        i = len(df)-2
        price, low, high, a = df.c.iloc[i], df.l.iloc[i], df.h.iloc[i], atr.iloc[i]
        breakout = price > donHi.iloc[i-1] and adx.iloc[i] > ADX_MIN and price > ma.iloc[i] and btc_ok
        breakdown = price < donLo.iloc[i-1]
        for lev in LEVELS:
            cs = states[lev]["coins"][c]
            if cs["units"] > 0:
                cs["peak"] = max(cs["peak"], high)
                if breakdown or low < cs["stop"]:
                    pnl = cs["units"]*price*(1-COST) - cs["units"]*cs["entry"]*(1+COST)
                    cs["cash"] += cs["units"]*price*(1-COST)
                    log_trade([now(),tag(lev),c,"SELL",round(price,6),round(cs["units"],6),"exit",round(pnl,2)])
                    if lev==LEVELS[-1]: actions.append(f"{c} EXIT")
                    cs.update(units=0.0, entry=0.0, stop=0.0, peak=0.0)
            elif breakout and a > 0:
                sd = a*ATR_STOP
                units = lev*(cs["cash"]*RISK_PCT/100)/sd
                units = min(units, cs["cash"]*0.95*lev/price)
                if units > 0:
                    cs["cash"] -= units*price*(1+COST)
                    cs.update(units=units, entry=price, stop=price-sd, peak=high)
                    log_trade([now(),tag(lev),c,"BUY",round(price,6),round(units,6),"breakout",""])
                    if lev==LEVELS[-1]: actions.append(f"{c} BUY")
            totals[lev] += cs["cash"] + cs["units"]*price
    for lev in LEVELS:
        states[lev]["last_run"]=now(); states[lev]["equity"]=round(totals[lev],2)
        state_path(lev).write_text(json.dumps(states[lev], indent=2))
        append_eq(lev, totals[lev])
    write_webdata(states, totals)
    summ = " | ".join(f"{tag(lev)} ${totals[lev]:,.0f}" for lev in LEVELS) + \
           (f" | {', '.join(actions)}" if actions else " | no trades")
    tg("PaperBot " + summ); print(f"{now()}  {summ}")

if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            try: cycle()
            except Exception as e: print("cycle error:", e)
            time.sleep(4*3600)
    else:
        cycle()
