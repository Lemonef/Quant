"""
NEW FAMILY CANDIDATE: stat-arb pairs (cointegration). Market-neutral mean reversion of a SPREAD,
not of a single coin -> structurally different from trend(momentum) and flush(absolute reversion).
Should be ~uncorrelated to the book if it works.

Method (Engle-Granger, hand-rolled; no statsmodels):
1. TRAIN (first 60%): for every coin pair, OLS hedge ratio beta on log prices, build spread,
   Dickey-Fuller stat on the spread. Keep pairs with DF < -3.2 (cointegrated in-sample only).
2. Trade selected pairs on the FULL series with the TRAIN-fixed beta + rolling z-score:
   z>+Z  -> short spread (short A, long beta*B);  z<-Z -> long spread; exit |z|<EXIT.
   Equal-weight across pairs. 2 legs each -> double trading cost. Funding ignored (note).
3. Daily returns -> correlation to trend & flush + OOS Sharpe. Add as sleeve only if
   corr<~0.3 to both AND OOS Sharpe positive on PAIRS PICKED IN TRAIN ONLY (no look-ahead).
4h, ~25 coins, merged 2021-2026.
"""
import numpy as np, pandas as pd
from itertools import combinations
from pathlib import Path
from engine import load, backtest
DATA=Path(__file__).parent/"data"; DPY=365
def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
# common index, aligned close panel
px=pd.DataFrame({s:M[s].close for s in coins}).dropna(how="all").ffill().dropna()
lpx=np.log(px)
n=len(px); split=int(n*0.6)
print(f"{len(coins)} coins, {n} 4h bars aligned, train=first {split} bars\n")

def ols(y,X):  # X already has const col; returns beta, resid, se_of_last_coef
    b,_,_,_=np.linalg.lstsq(X,y,rcond=None); r=y-X@b
    dof=max(1,len(y)-X.shape[1]); s2=(r@r)/dof
    cov=s2*np.linalg.pinv(X.T@X); return b,r,np.sqrt(np.diag(cov))

def df_stat(spread):  # Dickey-Fuller (no augmentation): ds ~ const + gamma*s_{t-1}
    s=spread[:-1]; ds=np.diff(spread); X=np.column_stack([np.ones(len(s)),s])
    b,_,se=ols(ds,X); return b[1]/se[1]   # t-stat on gamma; very negative = mean-reverting

# --- TRAIN: find cointegrated pairs ---
LtrA=lpx.values[:split]
pairs=[]
for i,j in combinations(range(len(coins)),2):
    a=LtrA[:,i]; b=LtrA[:,j]
    X=np.column_stack([np.ones(len(b)),b]); beta,resid,_=ols(a,X)
    df=df_stat(resid)
    if df<-3.2:   # cointegrated in-sample
        pairs.append((coins[i],coins[j],beta[1],beta[0],df))
pairs.sort(key=lambda z:z[4])
print(f"cointegrated pairs (DF<-3.2) in TRAIN: {len(pairs)}")
for a,b,be,c,d in pairs[:12]: print(f"  {a:9s}~{b:9s} beta{be:6.2f} DF{d:6.2f}")

# --- trade each selected pair on FULL series, train-fixed beta, rolling z ---
W,Z,EXIT,COST=30,2.0,0.5,0.0008
def pair_ret(a,b,beta,const):
    sp=lpx[a]-beta*lpx[b]-const
    mu=sp.rolling(W).mean(); sd=sp.rolling(W).std(); z=(sp-mu)/sd
    pos=np.zeros(len(sp)); cur=0.0
    zv=z.values
    for k in range(W,len(sp)):
        if cur==0:
            if zv[k]>Z: cur=-1.0
            elif zv[k]<-Z: cur=1.0
        elif abs(zv[k])<EXIT: cur=0.0
        pos[k]=cur
    pos=pd.Series(pos,index=sp.index)
    ra=px[a].pct_change(); rb=px[b].pct_change()
    # spread long = long A, short beta*B (normalised to ~1 gross/leg); pnl on prev position
    gross=1+abs(beta)
    pnl=pos.shift(1).fillna(0)*(ra-beta*rb)/gross
    turn=pos.diff().abs().fillna(0)*(1+abs(beta))/gross
    return (pnl-turn*COST).rename(f"{a}~{b}")

if pairs:
    legs=pd.concat([pair_ret(a,b,be,c) for a,b,be,c,d in pairs],axis=1).fillna(0)
    sa4h=legs.mean(axis=1)
    statarb=((1+sa4h).resample("1D").prod()-1)
else:
    statarb=pd.Series(dtype=float)

# --- book baselines (trend, flush) on daily ---
btc=M["BTCUSDT"].close; reg=btc>btc.rolling(200).mean()
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
statarb=statarb.reindex(IDX).fillna(0)

def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
oo=int(len(IDX)*0.6)
print("\ncorrelations (daily returns):")
print(pd.DataFrame({"trend":trend,"flush":flush,"statarb":statarb}).corr().round(2).to_string())
def row(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); print(f"  {t:30s} FULL Sh{f[2]:5.2f} DD{f[1]:6.1f}% | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")
print("\nsleeves + blends:")
row("statarb standalone", statarb)
row("trend70/flush30 (current)", 0.7*trend+0.3*flush)
row("trend60/flush25/statarb15", 0.6*trend+0.25*flush+0.15*statarb)
row("trend55/flush25/statarb20", 0.55*trend+0.25*flush+0.20*statarb)
print("\nNOTE: funding/borrow on the short leg NOT modelled (perp shorts pay/receive funding).")
print("DECISION: add only if corr<~0.3 to both AND OOS Sharpe>0 (pairs chosen in TRAIN only).")
