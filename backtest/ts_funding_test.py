"""
FAMILY: time-series funding-extreme reversion (single-coin). When a coin's OWN funding hits an
extreme NEGATIVE (shorts crowded, paying longs = capitulative positioning) AND price confirms with
an up-bar, go long (squeeze bounce). Directional, single-coin, positioning-triggered. Different from
fund_LS (cross-sectional rank) and crashreb (price-crash trigger). Also test extreme POSITIVE funding
as an exit/avoid signal. long-only. 4h, 25 coins w/ funding, 2021-2026.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest
DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists() and (DATA/f"{s}_funding.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
def fund_4h(s):  # 8h funding -> align to 4h bar index (ffill)
    f=pd.read_csv(DATA/f"{s}_funding.csv"); f.index=pd.to_datetime(f.fundingTime,unit="ms",utc=True)
    return f.fundingRate.astype(float)
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean()
COST=0.0008

# expectancy: coin fwd-6bar return conditional on own trailing-1d funding percentile
print("coin fwd-6bar return vs own funding z-score (pooled):")
rows=[]
for s in coins:
    c=M[s].close; r6=c.shift(-6)/c-1
    fz=fund_4h(s).resample("4h").sum().reindex(c.index).ffill()
    z=(fz-fz.rolling(180).mean())/fz.rolling(180).std()
    rows.append(pd.DataFrame({"fwd":r6,"z":z}).dropna())
A=pd.concat(rows); base=A.fwd.mean()
for lo,hi,lab in [(-99,-2,"z<-2 (shorts crowded)"),(-2,-1,"-2..-1"),(-1,1,"normal"),(1,2,"1..2"),(2,99,"z>2 (longs crowded)")]:
    v=A[(A.z>=lo)&(A.z<hi)].fwd
    print(f"  {lab:24s} n={len(v):6d} fwd {v.mean()*100:7.3f}%  edge {(v.mean()-base)*100:7.3f}%")

ZT,H,TP=-2.0,6,0.05
def tsf_coin(s):  # own funding z<-2 + up confirm bar -> long, exit +5% or H bars
    c=M[s].close; cv=c.values; hv=M[s].high.values; r=c.pct_change().values
    fz=fund_4h(s).resample("4h").sum().reindex(c.index).ffill()
    z=((fz-fz.rolling(180).mean())/fz.rolling(180).std()).values
    p=np.zeros(len(c)); ep=0.0; held=0
    for i in range(1,len(c)):
        if held>0:
            p[i]=1.0
            if hv[i]/ep-1>=TP or held>=H: held=0
            else: held+=1
            continue
        if not np.isnan(z[i]) and z[i]<ZT and r[i]>0: p[i]=1.0; ep=cv[i]; held=1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*COST).rename(s)
tsf=((1+pd.concat([tsf_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1)
ntr=sum(int(((tsf_coin(s)!=0).astype(int).diff()==1).sum()) for s in coins)

tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
IDX=trend.index
def flush_coin(s):
    df=M[s]; c=df.close; r=c.pct_change().values; cv=c.values; hv=df.high.values
    p=np.zeros(len(c)); ep=0.0; held=0; size=0.0
    for i in range(1,len(c)):
        if held>0:
            p[i]=size
            if hv[i]/ep-1>=0.05 or held>=4: held=0;size=0.0
            else: held+=1
            continue
        if r[i-1]<-0.08 and r[i]>-0.02: size=min(3.0,abs(r[i-1])/0.10);p[i]=size;ep=cv[i];held=1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*0.0008).rename(s)
flush=((1+pd.concat([flush_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
tsf=tsf.reindex(IDX).fillna(0)
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
oo=int(len(IDX)*0.6)
print(f"\ntsf entries ~{ntr}")
print("\ncorrelations:")
print(pd.DataFrame({"trend":trend,"flush":flush,"tsfund":tsf}).corr().round(2).to_string())
def row(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); print(f"  {t:30s} FULL Sh{f[2]:5.2f} DD{f[1]:6.1f}% | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")
print("\nsleeves + blends:")
row("tsfund standalone", tsf)
row("trend70/flush30 (current)", 0.7*trend+0.3*flush)
row("trend60/flush25/tsfund15", 0.6*trend+0.25*flush+0.15*tsf)
print("\nDECISION: keep if corr<~0.3 to both AND lifts blend OOS Sharpe above 1.05.")
