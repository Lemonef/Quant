"""
FAMILY BATCH: cross-sectional equity factors ported to crypto, all market-neutral long-short
(rank coins daily, long top quintile / short bottom). Market-neutral -> best shot at being
uncorrelated to trend(momentum) & flush(abs reversion). Factors:
  mom30   long 30d winners            (time-series momentum's XS cousin; expect OOS decay)
  lowvol  long LOW 30d realized vol    (low-volatility anomaly)
  rev7    long 7d LOSERS               (short-term overreaction reversal)
  skew30  long LOW 30d return-skew     (lottery-demand: high-skew coins overpriced -> short them)
Report corr to book + OOS Sharpe + 15% blend contribution. 25 coins, daily, 2021-2026.
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
px=pd.DataFrame({s:M[s].close for s in coins}).resample("1D").last().ffill()
R=px.pct_change()
n=len(px); Q=5; COST=0.0008

# --- factor signals (higher signal => expected higher fwd return => LONG) ---
mom30 = px.pct_change(30)                      # winners
lowvol= -R.rolling(30).std()                   # low vol = high signal
rev7  = -px.pct_change(7)                       # losers = high signal
skew30= -R.rolling(30).skew()                   # low skew = high signal
FACTORS={"mom30":mom30,"lowvol":lowvol,"rev7":rev7,"skew30":skew30}

def rank_ls(S):
    out=[]
    for d in range(n-1):
        row=S.iloc[d].dropna()
        if len(row)<10: out.append((px.index[d+1],0.0)); continue
        k=max(1,len(row)//Q); srt=row.sort_values()
        longs=srt.index[-k:]; shorts=srt.index[:k]
        nr=R.iloc[d+1]
        pnl=(nr[longs].mean()-nr[shorts].mean())/2.0 - COST
        out.append((px.index[d+1], pnl if pd.notna(pnl) else 0.0))
    return pd.Series(dict(out))
SLEEVES={k:rank_ls(v) for k,v in FACTORS.items()}

# baselines
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
SLEEVES={k:v.reindex(IDX).fillna(0) for k,v in SLEEVES.items()}

def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
oo=int(len(IDX)*0.6)
corr=pd.DataFrame({"trend":trend,"flush":flush,**SLEEVES}).corr().round(2)
print("correlations (daily):")
print(corr.to_string())
print("\nstandalone + 15% blend (current = trend70/flush30, OOS Sh 1.05 / DD -12.9%):")
cur=0.7*trend+0.3*flush
for k,v in SLEEVES.items():
    f=met(v); o=met(v.iloc[oo:])
    b=0.6*trend+0.25*flush+0.15*v; ob=met(b.iloc[oo:])
    print(f"  {k:8s} corrT{corr.loc['trend',k]:5.2f} corrF{corr.loc['flush',k]:5.2f} | standalone OOS Sh{o[2]:5.2f} DD{o[1]:6.1f}% | +15% blend OOS Sh{ob[2]:5.2f} DD{ob[1]:6.1f}%")
print("\nDECISION: keep a factor only if corr<~0.3 to BOTH and +15% blend OOS Sharpe >= 1.05 (current).")
print("LS earns funding on neither side here (spot) -> shorts would cost borrow live; treat as research.")
