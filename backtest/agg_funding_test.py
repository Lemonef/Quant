"""
Squeeze the FREE full-history funding data one more way: AGGREGATE market funding as a crowding /
market-timing gauge (not a per-coin sleeve). Thesis: when AVG funding across all coins is very HIGH
= whole market overheated/over-levered long -> lower forward returns (and crash risk). Very NEGATIVE
= capitulation -> higher forward returns. Could augment/replace the 200-MA bear filter for exposure
scaling. Tests: (1) forward return vs aggregate-funding bucket, (2) does a funding-based exposure
overlay beat the 200-MA one on the book. Free data, full history 2021-2026.
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
def fund_daily(s):
    f=pd.read_csv(DATA/f"{s}_funding.csv"); f.index=pd.to_datetime(f.fundingTime,unit="ms",utc=True)
    return f.fundingRate.resample("1D").sum().rename(s)
F=pd.concat([fund_daily(s) for s in coins],axis=1)
aggF=F.mean(axis=1)                                  # whole-market average daily funding
# basket forward return (equal-weight daily)
px=pd.DataFrame({s:M[s].close for s in coins}).resample("1D").last().ffill()
basket=px.pct_change().mean(axis=1)
aggF=aggF.reindex(basket.index).ffill()
z=(aggF-aggF.rolling(90).mean())/aggF.rolling(90).std()

print("forward 7d basket return vs aggregate-funding z-score (crowding):")
fwd=basket.rolling(7).sum().shift(-7)
df=pd.DataFrame({"z":z,"fwd":fwd}).dropna()
for lo,hi,lab in [(-9,-1.5,"z<-1.5 (capitulation)"),(-1.5,-0.5,"-1.5..-0.5"),(-0.5,0.5,"neutral"),(0.5,1.5,"0.5..1.5"),(1.5,9,"z>1.5 (overheated)")]:
    v=df[(df.z>=lo)&(df.z<hi)].fwd
    print(f"  {lab:22s} n={len(v):5d} fwd7d {v.mean()*100:7.2f}%  vs base {df.fwd.mean()*100:6.2f}%")

# overlay test: scale book exposure by funding regime vs 200-MA regime
btc=M["BTCUSDT"].close; reg200=btc>btc.rolling(200).mean()
tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=4.0,adx_filter=True,ma_filter=200,btc_regime=reg200)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
IDX=trend.index; oo=int(len(IDX)*0.6)
def flush_coin(s):
    df=M[s]; c=df.close; r=c.pct_change().values; cv=c.values; hv=df.high.values
    p=np.zeros(len(c)); ep=0.0; held=0; size=0.0
    for i in range(1,len(c)):
        if held>0:
            p[i]=size
            if hv[i]/ep-1>=0.05 or held>=2: held=0;size=0.0
            else: held+=1
            continue
        if r[i-1]<-0.08 and r[i]>-0.02: size=min(3.0,abs(r[i-1])/0.10);p[i]=size;ep=cv[i];held=1
    pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*0.0008).rename(s)
flush=((1+pd.concat([flush_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
def cr():
    alts=[c for c in coins if c!="BTCUSDT"]
    def cc(s):
        c=M[s].close; cv=c.values; hv=M[s].high.values; brv=btc.pct_change().reindex(c.index).values; p=np.zeros(len(c)); ep=0.0; held=0
        for i in range(1,len(c)):
            if held>0:
                p[i]=1.0
                if hv[i]/ep-1>=0.05 or held>=3: held=0
                else: held+=1
                continue
            if brv[i-1]<-0.05: p[i]=1.0; ep=cv[i]; held=1
        return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*0.0008).rename(s)
    return ((1+pd.concat([cc(s) for s in alts],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
book=0.55*trend+0.25*flush+0.20*cr()
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
zb=z.reindex(IDX).ffill()
reg200d=reg200.resample("1D").last().reindex(IDX).ffill().fillna(False)
overlays={
 "no overlay (1x always)": pd.Series(1.0,index=IDX),
 "200-MA x0.3 (current)": reg200d.map(lambda b:1.0 if b else 0.3),
 "funding z<1 full / z>1 x0.3": (zb<1.0).map(lambda b:1.0 if b else 0.3),
 "200MA AND funding (both)": ((reg200d)&(zb<1.0)).map(lambda b:1.0 if b else 0.3),
}
print("\nexposure overlay on the book (trend.55/flush.25/crash.20):")
for nm,ov in overlays.items():
    b=book*ov.reindex(IDX).fillna(1.0); f=met(b); o=met(b.iloc[oo:])
    print(f"  {nm:28s} FULL Sh{f[2]:.2f} DD{f[1]:6.1f}% | OOS Sh{o[2]:.2f} DD{o[1]:6.1f}%")
print("\nif a funding overlay beats 200-MA -> free new-data edge. else 200-MA already captures it.")
