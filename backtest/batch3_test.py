"""
FAMILY BATCH 3 (finish the queue + fresh ones):
  lwbreak  Larry Williams volatility breakout: close > prevclose + k*ATR (volatility thrust) -> long,
           exit 20-bar low. The PROPER version (momentum-thrust entry), not the plain rangex earlier.
  rsi2rev  Connors RSI2 reversion: RSI(2)<10 AND price>MA200 (dip in uptrend) -> long, exit RSI2>70
           or close>MA5. Classic equity short-term mean-reversion; gentler than flush.
  volbreak Volume-surge breakout: volume>2*avg20 AND close>20-bar high -> long (volume-confirmed).
Corr to book (trend/flush) + OOS + 15% blend. 4h, 25 coins, 2021-2026.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest, atr as ATR, rsi as RSI
DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean(); COST=0.0008

def lw_coin(s,k=1.0):
    df=M[s]; c=df.close; cv=c.values; a=ATR(df,14).values; dn=df.low.rolling(20).min().shift(1).values
    bull=reg.reindex(c.index).ffill().fillna(False).values; pc=c.shift(1).values
    p=np.zeros(len(c)); inpos=False
    for i in range(20,len(c)):
        if inpos:
            if cv[i]<dn[i]: inpos=False
            else: p[i]=1.0
        elif bull[i] and cv[i]>pc[i]+k*a[i]: inpos=True; p[i]=1.0
    return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*COST).rename(s)
def rsi2_coin(s):
    df=M[s]; c=df.close; cv=c.values; r2=RSI(c,2).values; ma200=c.rolling(200).mean().values; ma5=c.rolling(5).mean().values
    p=np.zeros(len(c)); inpos=False
    for i in range(200,len(c)):
        if inpos:
            if r2[i]>70 or cv[i]>ma5[i]: inpos=False
            else: p[i]=1.0
        elif cv[i]>ma200[i] and r2[i]<10: inpos=True; p[i]=1.0
    return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*COST).rename(s)
def vol_coin(s):
    df=M[s]; c=df.close; cv=c.values; v=df.volume.values; va=df.volume.rolling(20).mean().values
    hi=c.rolling(20).max().shift(1).values; dn=df.low.rolling(20).min().shift(1).values
    bull=reg.reindex(c.index).ffill().fillna(False).values
    p=np.zeros(len(c)); inpos=False
    for i in range(20,len(c)):
        if inpos:
            if cv[i]<dn[i]: inpos=False
            else: p[i]=1.0
        elif bull[i] and v[i]>2*va[i] and cv[i]>hi[i]: inpos=True; p[i]=1.0
    return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*COST).rename(s)
def agg(fn): return ((1+pd.concat([fn(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1)
SLEEVES={"lwbreak":agg(lw_coin),"rsi2rev":agg(rsi2_coin),"volbreak":agg(vol_coin)}

tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
IDX=trend.index
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
SLEEVES={k:v.reindex(IDX).fillna(0) for k,v in SLEEVES.items()}
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
oo=int(len(IDX)*0.6)
corr=pd.DataFrame({"trend":trend,"flush":flush,**SLEEVES}).corr().round(2)
print("correlations:"); print(corr.to_string())
print("\nstandalone + 15% add to improved book (trend.55/flush.25/x):")
for k,v in SLEEVES.items():
    o=met(v.iloc[oo:]); b=met((0.55*trend+0.25*flush+0.20*v).iloc[oo:])
    print(f"  {k:8s} corrT{corr.loc['trend',k]:5.2f} corrF{corr.loc['flush',k]:5.2f} | standalone OOS Sh{o[2]:5.2f} DD{o[1]:6.1f}% | as 20%-sleeve OOS Sh{b[2]:5.2f} DD{b[1]:6.1f}%")
print("\n(book w/ crashreb instead = OOS Sh 1.28. A sleeve here must beat that to matter.)")
