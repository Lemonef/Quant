"""
SKEW-FIX via INTRABAR stops (1h proxy for 1m; 10 majors have 1h). Backtests assume stops fire at the
4h CLOSE; reality = stop fills mid-bar. Test: (1) how much does intrabar fill worsen DD (backtest
optimism), (2) does a WIDER stop or NO hard-stop (Donchian-exit-only) reduce intrabar whipsaw =
a real robustness improvement for the live trend sleeve.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, atr as ATR
DATA=Path(__file__).parent/"data"; DPY=365
coins=sorted(p.stem[:-3] for p in DATA.glob("*_1h.csv"))
ENTRY,EXITN=55,20
def load4(s):
    df=load(s,"4h",DATA)
    try: df=pd.concat([load(f"{s}_bear","4h",DATA),df])
    except Exception: pass
    return df[~df.index.duplicated(keep="first")].sort_index()
M={s:load4(s) for s in coins}; H={s:load(s,"1h",DATA).sort_index() for s in coins}
btc=M["BTCUSDT"].close; reg=(btc>btc.rolling(200).mean())

def trend_coin(s, intrabar, stopmult):
    df=M[s]; c=df.close; cv=c.values
    a=ATR(df,14).values; donHi=c.rolling(ENTRY).max().shift(1).values; donLo=c.rolling(EXITN).min().shift(1).values
    ma=c.rolling(200).mean().values; bull=reg.reindex(c.index).ffill().fillna(False).values
    i4=c.index.values; h1i=H[s].index.values; h1lo=H[s].low.values
    stop=0.0; inpos=False; rets=np.zeros(len(c))
    for i in range(ENTRY+1,len(c)):
        if inpos:
            ex=0; px=cv[i]
            if intrabar and stopmult>0:
                a0=np.searchsorted(h1i,i4[i-1],side="right"); a1=np.searchsorted(h1i,i4[i],side="right")
                mn=h1lo[a0:a1].min() if a1>a0 else cv[i]
                if mn<=stop: ex=1; px=stop
                elif cv[i]<donLo[i]: ex=1; px=cv[i]
            else:
                if stopmult>0 and cv[i]<stop: ex=1; px=cv[i]
                elif cv[i]<donLo[i]: ex=1; px=cv[i]
            rets[i]=px/cv[i-1]-1
            if ex: inpos=False
        if not inpos and cv[i]>donHi[i] and bull[i] and cv[i]>ma[i] and a[i]>0:
            inpos=True; stop=(cv[i]-stopmult*a[i]) if stopmult>0 else 0.0
    return pd.Series(rets,index=c.index)
def book(intrabar,stopmult):
    R=pd.concat([trend_coin(s,intrabar,stopmult).rename(s) for s in coins],axis=1).fillna(0)
    return R.mean(axis=1).resample("1D").apply(lambda x:(1+x).prod()-1)
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
print(f"10 majors, 1h from {H['BTCUSDT'].index.min().date()} (intrabar test window)")
print("\n=== stop variants under REALISTIC intrabar fills (1x) ===")
print(f"  {'config':22s} CAGR     DD    Sharpe")
variants=[("ATR 2.5 (current)",2.5),("ATR 3.5 (wider)",3.5),("ATR 5.0 (very wide)",5.0),("NO hard stop (Donchian only)",0.0)]
res={}
for name,sm in variants:
    bi=book(True,sm); res[sm]=bi; f=met(bi)
    print(f"  {name:22s} {f[0]:6.1f}% {f[1]:6.1f}% {f[2]:5.2f}")
print("\n=== leverage table: current ATR2.5 vs BEST variant (intrabar) ===")
best_sm=max(res, key=lambda k: met(res[k])[2])
FUND=0.0003
print(f"  best variant = stopmult {best_sm}")
for L in [1,2,3]:
    fc=met(res[2.5]*L-max(0,L-1)*FUND); fb=met(res[best_sm]*L-max(0,L-1)*FUND)
    print(f"  {L}x: ATR2.5 {fc[0]:6.1f}%/{fc[1]:6.1f}%/Sh{fc[2]:.2f}  | best {fb[0]:6.1f}%/{fb[1]:6.1f}%/Sh{fb[2]:.2f}")
print("\nif wider/no-stop beats ATR2.5 under intrabar -> the hard stop causes whipsaw; widen it live.")
