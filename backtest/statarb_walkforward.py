"""
Stat-arb pairs, WALK-FORWARD (the fair test). Static cointegration died OOS because pairs were
frozen from 2021-23 train. Here: every STEP bars, re-select cointegrated pairs on a trailing
LOOKBACK window, then trade them the next STEP bars with a ROLLING hedge beta + rolling z-score.
This mimics real stat-arb (continuous re-estimation). If THIS is still negative OOS, the family
is dead for our universe. 4h, 25 coins, merged 2021-2026.
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
px=pd.DataFrame({s:M[s].close for s in coins}).dropna(how="all").ffill().dropna()
lpx=np.log(px); ret=px.pct_change().fillna(0)
n=len(px); cn=len(coins)
LOOK,STEP,W,Z,EXIT,COST,DFMAX,TOPK=720,180,30,2.0,0.5,0.0008,-3.2,20  # 720*4h=120d lookback, re-pick every 30d
print(f"{cn} coins, {n} bars. WF: lookback {LOOK}b(~120d), re-pick every {STEP}b(~30d), top{TOPK} pairs/window\n")

def ols(y,X):
    b,_,_,_=np.linalg.lstsq(X,y,rcond=None); r=y-X@b
    dof=max(1,len(y)-X.shape[1]); s2=(r@r)/dof
    cov=s2*np.linalg.pinv(X.T@X); return b,r,np.sqrt(np.diag(cov))
def df_stat(sp):
    s=sp[:-1]; ds=np.diff(sp); X=np.column_stack([np.ones(len(s)),s])
    b,_,se=ols(ds,X); return b[1]/se[1]

LV=lpx.values; RV=ret.values
port=np.zeros(n)  # 4h portfolio return
idxpairs=list(combinations(range(cn),2))
start=LOOK
windows=0; avg_pairs=[]
while start<n:
    end=min(start+STEP,n)
    tr=LV[start-LOOK:start]
    # select cointegrated pairs on trailing window
    sel=[]
    for i,j in idxpairs:
        a=tr[:,i]; b=tr[:,j]
        X=np.column_stack([np.ones(len(b)),b]); be,res,_=ols(a,X)
        d=df_stat(res)
        if d<DFMAX: sel.append((i,j,d))
    sel.sort(key=lambda z:z[2]); sel=sel[:TOPK]
    avg_pairs.append(len(sel)); windows+=1
    if not sel: start=end; continue
    # trade the next STEP bars; rolling beta + rolling z on extended slice
    s0=start-W  # need W warmup for z
    for (i,j,d) in sel:
        a=lpx.iloc[s0:end,i].values; b=lpx.iloc[s0:end,j].values
        # rolling hedge beta over W
        sp=np.full(len(a),np.nan)
        for k in range(W,len(a)):
            xb=b[k-W:k]; xa=a[k-W:k]
            X=np.column_stack([np.ones(W),xb]); be,_,_=ols(xa,X)
            sp[k]=a[k]-be[1]*b[k]-be[0]
        sps=pd.Series(sp); mu=sps.rolling(W).mean(); sd=sps.rolling(W).std()
        z=((sps-mu)/sd).values
        ra=RV[s0:end,i]; rb=RV[s0:end,j]
        pos=0.0  # position decided at bar k-1, earns return ra[k]-rb[k]
        for k in range(W,len(a)):
            kk=s0+k
            newpos=pos
            if pos==0:
                if z[k]>Z: newpos=-1.0
                elif z[k]<-Z: newpos=1.0
            elif abs(z[k])<EXIT: newpos=0.0
            if start<=kk<end:
                pnl=pos*(ra[k]-rb[k])/2.0 - abs(newpos-pos)*COST
                port[kk]+= pnl/max(1,len(sel))
            pos=newpos
    start=end
print(f"windows={windows}, avg pairs/window={np.mean(avg_pairs):.1f}")
statarb4h=pd.Series(port,index=px.index)
statarb=((1+statarb4h).resample("1D").prod()-1)

# book baselines
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
print("\ncorrelations (daily):")
print(pd.DataFrame({"trend":trend,"flush":flush,"statarb_wf":statarb}).corr().round(2).to_string())
def row(t,pr):
    f=met(pr); o=met(pr.iloc[oo:]); print(f"  {t:30s} FULL Sh{f[2]:5.2f} DD{f[1]:6.1f}% | OOS C{o[0]:6.1f}% DD{o[1]:6.1f}% Sh{o[2]:5.2f}")
print("\nsleeves + blends:")
row("statarb_wf standalone", statarb)
row("trend70/flush30 (current)", 0.7*trend+0.3*flush)
row("trend60/flush25/statarb15", 0.6*trend+0.25*flush+0.15*statarb)
print("\nfunding NOT modelled. DECISION: add only if OOS Sharpe>0 AND lifts blend OOS Sharpe.")
