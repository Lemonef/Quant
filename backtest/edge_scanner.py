"""
Edge-hunting scanner: test a battery of mechanism hypotheses via conditional forward-return
expectancy (the cheap first filter). For each signal: pooled avg forward return over H bars vs the
unconditional baseline, hit rate, frequency. Big positive (or negative) edge = worth developing.
4h, 25 coins, merged 2021-2026.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load
DATA=Path(__file__).parent/"data"
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}

def rsi(c,n):
    d=c.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); dn=(-d).clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    return (100-100/(1+up/dn.replace(0,np.nan))).fillna(50)

def scan(name, sigfn, H):
    fwd=[]; nb=0
    for s in coins:
        df=M[s]; c=df.close; f=c.shift(-H)/c-1
        sig=sigfn(df,c).reindex(c.index).fillna(False)
        v=f[sig].dropna(); fwd.append(v); nb+=int(sig.sum())
    allf=pd.concat(fwd) if fwd else pd.Series(dtype=float)
    base=pd.concat([M[s].close.pct_change(H).dropna() for s in coins]).mean()
    if len(allf)<30: return None
    return (name,len(allf),allf.mean()*100,(allf>0).mean()*100,base*100,(allf.mean()-base)*100)

H=6
tests=[
 ("flush <-10% (rev)",   lambda df,c: c.pct_change()<-0.10),
 ("pump >+10% (fade?)",  lambda df,c: c.pct_change()>0.10),
 ("3 red bars",          lambda df,c: (c.pct_change()<0).rolling(3).sum()==3),
 ("3 green bars",        lambda df,c: (c.pct_change()>0).rolling(3).sum()==3),
 ("RSI2<5 oversold",     lambda df,c: rsi(c,2)<5),
 ("RSI2>95 overbought",  lambda df,c: rsi(c,2)>95),
 ("RSI14<25",            lambda df,c: rsi(c,14)<25),
 ("RSI14>75",            lambda df,c: rsi(c,14)>75),
 ("3+ATR below MA20",    lambda df,c: c < c.rolling(20).mean()-3*(df.high-df.low).rolling(14).mean()),
 ("3+ATR above MA20",    lambda df,c: c > c.rolling(20).mean()+3*(df.high-df.low).rolling(14).mean()),
 ("vol spike+red",       lambda df,c: (df.volume>3*df.volume.rolling(20).mean())&(c.pct_change()<0)),
 ("new 50-bar high",     lambda df,c: c>=c.rolling(50).max()),
 ("inside-bar squeeze",  lambda df,c: (df.high<df.high.shift(1))&(df.low>df.low.shift(1))),
 ("new 50-bar low (rev)",lambda df,c: c<=c.rolling(50).min()),
 ("2-bar flush <-15%",   lambda df,c: c.pct_change(2)<-0.15),
 ("4 red bars",          lambda df,c: (c.pct_change()<0).rolling(4).sum()==4),
 ("RSI14<20 deep",       lambda df,c: rsi(c,14)<20),
 ("RSI14<30",            lambda df,c: rsi(c,14)<30),
 ("-20% from 20-high",   lambda df,c: c/c.rolling(20).max()-1 < -0.20),
 ("-30% from 20-high",   lambda df,c: c/c.rolling(20).max()-1 < -0.30),
 ("big-range bar+down",  lambda df,c: ((df.high-df.low)/c>0.12)&(c.pct_change()<0)),
 ("vol dryup near low",  lambda df,c: (df.volume<0.5*df.volume.rolling(20).mean())&(c<c.rolling(20).mean())),
 ("BTC-rel underperf",   lambda df,c: c.pct_change(6) - M["BTCUSDT"].close.pct_change(6).reindex(c.index) < -0.15),
]
print(f"signal forward {H} bars (~24h), 25 coins, 2021-2026")
print(f"{'signal':22s} {'n':>6s} {'avg_fwd%':>9s} {'hit%':>6s} {'base%':>7s} {'EDGE%':>7s}")
rows=[scan(n,f,H) for n,f in tests]
for r in sorted([x for x in rows if x],key=lambda z:-abs(z[5])):
    print(f"{r[0]:22s} {r[1]:6d} {r[2]:9.2f} {r[3]:6.1f} {r[4]:7.2f} {r[5]:7.2f}")
print("\nEDGE% = conditional avg minus baseline. Big +EDGE on reversion signals = contrarian alpha")
print("(uncorrelated to trend). Big +EDGE on momentum signals (new high/green) overlaps trend.")
