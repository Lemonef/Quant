"""Does a bigger universe lift the core's out-of-sample Sharpe? (clean, non-overfit lever)
Core = Donchian55/20 + MA200. Equal-weight basket. Test N=10 vs expanded N. Daily metrics."""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest

DATA=Path(__file__).parent/"data"; DPY=365
ORIG=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","DOGEUSDT"]
CFG=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200)

# discover coins that have BOTH windows
coins=[]
for p in sorted(DATA.glob("*_4h.csv")):
    sym=p.stem[:-3]
    if sym.endswith("_bear"): continue
    if (DATA/f"{sym}_bear_4h.csv").exists():
        coins.append(sym)
print(f"coins with full history: {len(coins)}")

def merged(sym):
    df=pd.concat([load(f"{sym}_bear","4h",DATA), load(sym,"4h",DATA)])
    return df[~df.index.duplicated(keep="first")].sort_index()

def daily_ret(sym):
    eq,_=backtest(merged(sym),CFG)
    return eq.resample("1D").last().ffill().pct_change().rename(sym)

RET=pd.concat([daily_ret(s) for s in coins],axis=1)
idx=RET.index

def met(pr):
    pr=pr.dropna()
    if len(pr)<30 or pr.std()==0: return (0,0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    cagr=eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else -1
    dd=(eq/eq.cummax()-1).min(); sh=pr.mean()/pr.std()*np.sqrt(DPY)
    return (cagr*100,dd*100,sh)

y22a=pd.Timestamp("2022-01-01",tz="UTC"); y22b=pd.Timestamp("2023-01-01",tz="UTC")
n=len(idx); oos=int(n*0.6)
def show(tag,cols):
    pr=RET[cols].reindex(idx).fillna(0.0).mean(axis=1)
    f=met(pr); b=met(pr[(pr.index>=y22a)&(pr.index<y22b)]); o=met(pr.iloc[oos:])
    print(f"  {tag:18s} (N={len(cols):2d}) FULL C{f[0]:6.1f}% DD{f[1]:6.1f}% Sh{f[2]:5.2f} | 2022 Sh{b[2]:5.2f} | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")

print("\n=== universe size effect (core Donchian55/20+MA200) ===")
show("original 10", ORIG)
extra=[c for c in coins if c not in ORIG]
for k in [5,10,15,20]:
    cols=ORIG+extra[:k]
    cols=[c for c in cols if c in RET.columns]
    if len(cols)>len(ORIG): show(f"expanded", cols)
show("ALL available", list(RET.columns))
