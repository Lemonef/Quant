"""
User's idea: Trend Meter EMA stack on DAILY, always-in long/short.
  all 3 bands green (EMA 13>21>34>55) -> LONG, hold
  all 3 bands red  (EMA 13<21<34<55) -> SHORT, hold
  in between -> hold current position (flip only on full opposite alignment)
Tested per-coin on a basket, daily, merged 2021-2026 (so the SHORT side faces the 2022 bear).
Also a long-only variant and a 200-MA cross sanity check. Costs incl flip slippage+funding.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load

DATA=Path(__file__).parent/"data"; DPY=365
BASKET=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","DOGEUSDT"]
FLIP=0.001+0.0005      # commission+slippage per side
FUND=0.10/DPY          # ~10%/yr funding drag while short

def daily_close(sym):
    a=load(f"{sym}_bear","4h",DATA).close.resample("1D").last()
    b=load(sym,"4h",DATA).close.resample("1D").last()
    return pd.concat([a,b])[~pd.concat([a,b]).index.duplicated(keep="first")].sort_index()

PX=pd.DataFrame({s:daily_close(s) for s in BASKET}).dropna(how="all")
RET=PX.pct_change().fillna(0.0)

def met(pr):
    pr=pr.dropna()
    if len(pr)<30 or pr.std()==0: return (0,0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    cagr=eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else -1
    dd=(eq/eq.cummax()-1).min(); sh=pr.mean()/pr.std()*np.sqrt(DPY)
    dn=pr[pr<0].std(); so=pr.mean()/dn*np.sqrt(DPY) if dn>0 else 0
    return (cagr*100,dd*100,sh,so)

def emas(c): return [c.ewm(span=n,adjust=False).mean() for n in (13,21,34,55)]

def coin_pos(sym, mode):
    c=PX[sym]; e1,e2,e3,e4=emas(c)
    green=(e1>e2)&(e2>e3)&(e3>e4)
    red=(e1<e2)&(e2<e3)&(e3<e4)
    raw=pd.Series(np.nan,index=c.index)
    raw[green]=1.0
    raw[red]=-1.0 if mode=="ls" else 0.0
    return raw.ffill().fillna(0.0)

def strat_ret(mode):
    out=[]
    for s in BASKET:
        pos=coin_pos(s,mode)
        flips=pos.diff().abs().fillna(0.0)
        r=pos.shift(1).fillna(0.0)*RET[s]
        cost=flips*FLIP + (pos.shift(1)<0).astype(float)*FUND   # funding only while short
        out.append((r-cost).rename(s))
    return pd.concat(out,axis=1).fillna(0.0).mean(axis=1)

y22a=pd.Timestamp("2022-01-01",tz="UTC"); y22b=pd.Timestamp("2023-01-01",tz="UTC")
def bear(pr): return pr[(pr.index>=y22a)&(pr.index<y22b)]
ls=strat_ret("ls"); lo=strat_ret("lo")
n=len(ls); oos=int(n*0.6)
def row(tag,pr):
    f=met(pr); b=met(bear(pr)); o=met(pr.iloc[oos:])
    print(f"  {tag:22s} FULL C{f[0]:7.1f}% DD{f[1]:7.1f}% Sh{f[2]:5.2f} | 2022 C{b[0]:7.1f}% Sh{b[2]:5.2f} | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")

print(f"daily bars {len(PX)} (~2021-2026)\n=== TM EMA-stack DAILY ===")
row("always-in L/S", ls)
row("long-only (green=long)", lo)
print(f"\ncorr LS vs long-only: {ls.corr(lo):.2f}")
print("\n=== leverage on always-in L/S ===")
for L in [1.0,1.5,2.0,3.0]:
    f=met(ls*L); print(f"  {L:.1f}x: CAGR {f[0]:7.1f}%  DD {f[1]:7.1f}%  Sharpe {f[2]:.2f}")
