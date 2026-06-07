"""
SKEW-FIX: make leverage EFFICIENT. Plain leverage is inefficient here (neg skew: rare crash-day
losses blow up under leverage). Test overlays that cap tails so CAGR keeps rising while DD stays
controlled:
  A) static leverage (baseline, what we had)
  B) VOL-TARGET: scale daily exposure to a target annualised vol (auto-derisk when realized vol
     spikes = exactly the crash periods). Cap max exposure.
  C) vol-target + daily CIRCUIT BREAKER (if yesterday book < -4%, halve today).
Find the config + exposure that gives the best CAGR for a tolerable DD. 4h, 25 coins, 2021-26.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest
DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean(); alts=[c for c in coins if c!="BTCUSDT"]
def met(pr):
    pr=pr.dropna()
    if len(pr)<5 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=reg)
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
IDX=trend.index; oo=int(len(IDX)*0.6)
def fl(H):
    def fc(s):
        df=M[s]; c=df.close; r=c.pct_change().values; cv=c.values; hv=df.high.values; p=np.zeros(len(c)); ep=0.0; held=0; sz=0.0
        for i in range(1,len(c)):
            if held>0:
                p[i]=sz
                if hv[i]/ep-1>=0.05 or held>=H: held=0;sz=0.0
                else: held+=1
                continue
            if r[i-1]<-0.08 and r[i]>-0.02: sz=min(3.0,abs(r[i-1])/0.10);p[i]=sz;ep=cv[i];held=1
        return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*0.0008).rename(s)
    return ((1+pd.concat([fc(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1).reindex(IDX).fillna(0)
def cr():
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
book=0.55*trend+0.25*fl(2)+0.20*cr()
btcd=btc.resample("1D").last(); regd=(btcd>btcd.rolling(200).mean()).reindex(IDX).ffill().fillna(False)
base=(book*regd.map(lambda b:1.0 if b else 0.3)).rename("base")  # bear-scaled book (1x)
FUND=0.0003

def lever_static(L):
    return base*L - max(0,L-1)*FUND
def vol_target(tgt, maxlev, cb=False):
    rv=base.rolling(30).std()*np.sqrt(DPY)
    scale=(tgt/rv.shift(1)).clip(upper=maxlev).fillna(1.0)
    if cb:
        breaker=(base.shift(1)<-0.04).map(lambda x:0.5 if x else 1.0)
        scale=scale*breaker
    lr=base*scale - (scale-1).clip(lower=0)*FUND
    return lr, scale.mean()

print("=== A) STATIC leverage (baseline) ===")
print(f"  {'lev':4s} {'CAGR':>7s} {'DD':>7s} {'Sharpe':>6s} | CAGR/DD ratio")
for L in [1,2,3,4]:
    f=met(lever_static(L)); print(f'  {L}x   {f[0]:6.1f}% {f[1]:6.1f}% {f[2]:5.2f} | {abs(f[0]/f[1]):.2f}')
print("\n=== B) VOL-TARGET (scale to target annual vol, cap maxlev) ===")
print(f"  {'target':8s} {'maxlev':6s} {'CAGR':>7s} {'DD':>7s} {'Sharpe':>6s} {'avgLev':>6s} | OOS CAGR/DD/Sh")
for tgt in [0.30,0.40,0.50,0.60]:
    for mx in [3,4]:
        lr,al=vol_target(tgt,mx); f=met(lr); o=met(lr.iloc[oo:])
        print(f'  {tgt*100:5.0f}%   {mx}x     {f[0]:6.1f}% {f[1]:6.1f}% {f[2]:5.2f} {al:5.2f}x | {o[0]:5.1f}%/{o[1]:5.1f}%/{o[2]:.2f}')
print("\n=== C) VOL-TARGET + circuit breaker (yesterday<-4% -> halve) ===")
for tgt in [0.40,0.50,0.60]:
    lr,al=vol_target(tgt,4,cb=True); f=met(lr); o=met(lr.iloc[oo:])
    print(f'  tgt{tgt*100:.0f}% +CB: FULL CAGR{f[0]:6.1f}% DD{f[1]:6.1f}% Sh{f[2]:.2f} | OOS CAGR{o[0]:5.1f}% DD{o[1]:5.1f}% Sh{o[2]:.2f}')
print("\nGOAL: find config where CAGR is HIGH but DD stays ~25-35% (vs static 3x = 24%/35%).")
print("If vol-target beats static at same DD -> tail-capping made leverage efficient = real CAGR unlock.")
