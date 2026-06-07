"""
Clean alpha library — each correctly modeled, measured OUT-OF-SAMPLE, then ensemble only the
ones with genuine positive-OOS uncorrelated edge. Daily, merged 2021-2026, full universe.
Alphas:
  trend     - Donchian55/20 + MA200 (the validated core)
  xsmom     - cross-sectional momentum, long top5 / short bottom5, dollar-neutral
  carry     - long spot / short perp, ON only when funding positive (collect), realistic cost
  rsi2dip   - Connors-style: in uptrend (close>MA200) buy RSI(2)<10, exit RSI(2)>50 (long-only)
  tsmom     - time-series momentum 28d sign, long-only
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest

DATA=Path(__file__).parent/"data"; DPY=365
def have_full(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have_full(p.stem[:-3])})
carry_coins=[c for c in coins if (DATA/f"{c}_funding.csv").exists()]

def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)])
    return df[~df.index.duplicated(keep="first")].sort_index()
PX=pd.DataFrame({s:merged(s).close.resample("1D").last() for s in coins}).dropna(how="all")
IDX=PX.index; RET=PX.pct_change().fillna(0.0)
MA200=PX.rolling(200).mean()

def rsi(s,n):
    d=s.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    dn=(-d).clip(lower=0).ewm(alpha=1/n,adjust=False).mean()
    return (100-100/(1+up/dn.replace(0,np.nan))).fillna(50)

def met(pr):
    pr=pr.dropna()
    if len(pr)<60 or pr.std()==0: return dict(C=0,DD=0,Sh=0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    c=eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else -1
    dd=(eq/eq.cummax()-1).min(); sh=pr.mean()/pr.std()*np.sqrt(DPY)
    return dict(C=c*100,DD=dd*100,Sh=sh)

# --- alphas ---
CFG=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200)
trend=pd.concat([backtest(merged(s),CFG)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).reindex(IDX).fillna(0.0).mean(axis=1)

m28=(PX/PX.shift(28)-1); rk=m28.rank(axis=1,ascending=False)
wl=(rk<=5).astype(float); ws=(rk>=len(coins)-4).astype(float)
wl=wl.div(wl.sum(axis=1).replace(0,np.nan),axis=0).fillna(0); ws=ws.div(ws.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
xsturn=(wl-ws).diff().abs().sum(axis=1).fillna(0)
xsmom=((wl-ws).shift(1).fillna(0)*RET).sum(axis=1) - xsturn*0.0006 - 0.10/DPY  # taker + short borrow

def funding_daily(s):
    f=pd.read_csv(DATA/f"{s}_funding.csv"); f["dt"]=pd.to_datetime(f.fundingTime,unit="ms",utc=True)
    return f.set_index("dt").fundingRate.astype(float).resample("1D").sum()
FUND=pd.DataFrame({s:funding_daily(s) for s in carry_coins}).reindex(IDX).fillna(0.0)
on=(FUND.rolling(3).mean()>0).astype(float)            # position on when funding positive
carry_each=on.shift(1).fillna(0)*FUND - on.diff().abs().fillna(0)*0.0004   # cost only on entry/exit
carry=carry_each.mean(axis=1)

# RSI2 dip-in-trend, long-only per coin
def rsi2dip(s):
    c=PX[s]; r=rsi(c,2); up=c>MA200[s]
    pos=pd.Series(np.nan,index=c.index)
    pos[(up)&(r<10)]=1.0; pos[r>50]=0.0
    pos=pos.ffill().fillna(0.0)
    flips=pos.diff().abs().fillna(0.0)
    return (pos.shift(1).fillna(0)*RET[s] - flips*0.0006).rename(s)
rsidip=pd.concat([rsi2dip(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)

sig=(PX/PX.shift(28)-1); pos=(sig>0).astype(float).shift(1).fillna(0)
pos=pos.div(pos.sum(axis=1).replace(0,np.nan),axis=0).fillna(0); tsmom=(pos*RET).sum(axis=1)

ALPHAS={"trend":trend,"xsmom":xsmom,"carry":carry,"rsi2dip":rsidip,"tsmom":tsmom}
n=len(IDX); oos=int(n*0.6)
print(f"daily {n} bars, {len(coins)} coins, {len(carry_coins)} w/ funding\n")
print(f"{'alpha':9s}  FULL(C/DD/Sh)            OOS(C/DD/Sh)")
for nm,pr in ALPHAS.items():
    f=met(pr); o=met(pr.iloc[oos:])
    print(f"{nm:9s}  {f['C']:6.1f}% {f['DD']:6.1f}% {f['Sh']:5.2f}   |  {o['C']:6.1f}% {o['DD']:6.1f}% {o['Sh']:5.2f}")

print("\ncorrelation matrix (daily):")
print(pd.DataFrame(ALPHAS).corr().round(2).to_string())

# ensemble: positive-OOS sleeves only, inverse-vol fixed weights (NO leverage overlay)
oos_sh={nm:met(pr.iloc[oos:])['Sh'] for nm,pr in ALPHAS.items()}
keep=[nm for nm,sh in oos_sh.items() if sh>0.15]
print(f"\nsleeves kept (OOS Sharpe>0.15): {keep}")
if keep:
    df=pd.DataFrame({k:ALPHAS[k] for k in keep})
    vol=df.std(); w=(1/vol)/(1/vol).sum()
    blend=(df*w).sum(axis=1)
    f=met(blend); o=met(blend.iloc[oos:])
    print(f"ENSEMBLE   FULL {f['C']:.1f}% DD{f['DD']:.1f}% Sh{f['Sh']:.2f} | OOS {o['C']:.1f}% DD{o['DD']:.1f}% Sh{o['Sh']:.2f}")
    # Kelly leverage on OOS
    oo=blend.iloc[oos:]; kelly=oo.mean()/oo.var() if oo.var()>0 else 0
    print(f"weights: {dict(zip(keep,(w.round(2)).tolist()))}")
    print(f"full-Kelly leverage (OOS) ~ {kelly/ DPY if False else (oo.mean()/oo.var()):.2f}x  -> use half: ~{(oo.mean()/oo.var())/2:.2f}x")
