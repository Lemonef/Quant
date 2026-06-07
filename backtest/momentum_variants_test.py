"""
FAMILY BATCH: directional momentum-entry variants (long-only, btc-bull gated, exit on 20-bar low =
same as trend's exit, so this is a fair 'different ENTRY, same EXIT' comparison vs the Donchian core).
  tsmom   absolute time-series momentum vote: price>price N-ago for >=2 of {30d,90d,180d}
  accel   momentum acceleration: 30d momentum positive AND rising (2nd derivative > 0)
  rangex  faster breakout: close > 20-bar high (range expansion / shorter Donchian)
Question: does any BEAT the trend core (standalone OOS Sh 0.86) or complement it? 4h, 25 coins, 2021-26.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest, atr as ATR
DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean()
COST=0.0008
def sim(sigfn):  # long while sig true, exit when close<20-bar low OR sig false; bull-gated entry
    def coin(s):
        df=M[s]; c=df.close; cv=c.values; dn=df.low.rolling(20).min().shift(1).values
        sig=sigfn(df,c).reindex(c.index).fillna(False).values
        bull=reg.reindex(c.index).ffill().fillna(False).values
        p=np.zeros(len(c)); inpos=False
        for i in range(1,len(c)):
            if inpos:
                if cv[i]<dn[i] or not sig[i]: inpos=False
                else: p[i]=1.0
            elif bull[i] and sig[i] and not np.isnan(dn[i]): inpos=True; p[i]=1.0
        pos=pd.Series(p,index=c.index); return (pos.shift(1).fillna(0)*c.pct_change()-pos.diff().abs().fillna(0)*COST).rename(s)
    return ((1+pd.concat([coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1)
def tsmom(df,c):
    v=((c>c.shift(180)).astype(int)+(c>c.shift(540)).astype(int)+(c>c.shift(1080)).astype(int))
    return v>=2
def accel(df,c):
    m=c.pct_change(180); return (m>0)&(m>m.shift(180))
def rangex(df,c):
    return c>c.rolling(120).max().shift(1)   # 20-bar high (120? no) -> use 20-day=120 bars
SLEEVES={"tsmom":sim(tsmom),"accel":sim(accel),"rangex":sim(rangex)}

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
SLEEVES={k:v.reindex(IDX).fillna(0) for k,v in SLEEVES.items()}
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
oo=int(len(IDX)*0.6)
corr=pd.DataFrame({"trend":trend,"flush":flush,**SLEEVES}).corr().round(2)
print("correlations:"); print(corr.to_string())
ot=met(trend.iloc[oo:]); print(f"\ntrend core: standalone OOS Sh {ot[2]:.2f} DD {ot[1]:.1f}%")
print("variants (vs trend core, + as crashreb-style 15% add to current best blend 1.05):")
for k,v in SLEEVES.items():
    o=met(v.iloc[oo:]); b=met((0.6*trend+0.25*flush+0.15*v).iloc[oo:])
    print(f"  {k:7s} corrT{corr.loc['trend',k]:5.2f} | standalone OOS Sh{o[2]:5.2f} DD{o[1]:6.1f}% | +15% blend OOS Sh{b[2]:5.2f} DD{b[1]:6.1f}%")
print("\nDECISION: a variant is useful only if it BEATS trend's standalone Sh, or lifts blend >1.05.")
