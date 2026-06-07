"""
Risk-aware carry (basis trade): long spot + short perp, ON only when funding positive.
Daily PnL (delta-neutral, 1 unit/leg) = funding_received + spot_ret - perp_ret  (the spot-perp
basis move is the REAL risk my earlier model ignored). Cost on entry/exit. Then ensemble w/ trend.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest

DATA=Path(__file__).parent/"data"; DPY=365
def have_full(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have_full(p.stem[:-3])})
cc=[c for c in coins if (DATA/f"{c}_funding.csv").exists() and (DATA/f"{c}_perp_4h.csv").exists()]

def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)])
    return df[~df.index.duplicated(keep="first")].sort_index()
SPOT=pd.DataFrame({s:merged(s).close.resample("1D").last() for s in coins}).dropna(how="all")
IDX=SPOT.index

def perp_daily(s):
    df=pd.read_csv(DATA/f"{s}_perp_4h.csv"); df["dt"]=pd.to_datetime(df.open_time,unit="ms",utc=True)
    return df.set_index("dt").close.astype(float).resample("1D").last()
def funding_daily(s):
    f=pd.read_csv(DATA/f"{s}_funding.csv"); f["dt"]=pd.to_datetime(f.fundingTime,unit="ms",utc=True)
    return f.set_index("dt").fundingRate.astype(float).resample("1D").sum()

PERP=pd.DataFrame({s:perp_daily(s) for s in cc}).reindex(IDX)
FUND=pd.DataFrame({s:funding_daily(s) for s in cc}).reindex(IDX).fillna(0.0)
SPOT_cc=SPOT[cc]
sret=SPOT_cc.pct_change(); pret=PERP.pct_change()

def met(pr):
    pr=pr.dropna()
    if len(pr)<60 or pr.std()==0: return dict(C=0,DD=0,Sh=0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    c=eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else -1
    dd=(eq/eq.cummax()-1).min(); sh=pr.mean()/pr.std()*np.sqrt(DPY)
    return dict(C=c*100,DD=dd*100,Sh=sh)

on=(FUND.rolling(3).mean()>0).astype(float)
basis_pnl = sret - pret                       # delta-neutral price move = -(basis change) = real risk
carry_each = on.shift(1).fillna(0)*(FUND + basis_pnl) - on.diff().abs().fillna(0)*0.0006
carry=carry_each.mean(axis=1)

# trend core
CFG=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200)
trend=pd.concat([backtest(merged(s),CFG)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).reindex(IDX).fillna(0.0).mean(axis=1)

n=len(IDX); oos=int(n*0.6)
y22a=pd.Timestamp("2022-01-01",tz="UTC"); y22b=pd.Timestamp("2023-01-01",tz="UTC")
def bear(pr): return pr[(pr.index>=y22a)&(pr.index<y22b)]
def line(t,pr):
    f=met(pr); b=met(bear(pr)); o=met(pr.iloc[oos:])
    print(f"  {t:22s} FULL C{f['C']:6.1f}% DD{f['DD']:6.1f}% Sh{f['Sh']:5.2f} | 2022 Sh{b['Sh']:5.2f} | OOS C{o['C']:6.1f}% DD{o['DD']:6.1f}% Sh{o['Sh']:5.2f}")

print(f"{len(cc)} coins w/ spot+perp+funding\n")
print("=== risk-aware carry vs trend ===")
line("carry v2 (basis-risk)", carry)
line("trend core", trend)
print(f"\ncorr trend-carry: {trend.corr(carry):.2f}  carry vol(ann): {carry.std()*np.sqrt(DPY)*100:.1f}%")

# ensemble: inverse-vol fixed weights, NO leverage overlay
df=pd.DataFrame({"trend":trend,"carry":carry}).fillna(0.0)
w=(1/df.std())/((1/df.std()).sum())
blend=(df*w).sum(axis=1)
print(f"\n=== ENSEMBLE trend+carry (inverse-vol w={dict(zip(['trend','carry'],w.round(2).tolist()))}) ===")
line("trend+carry blend", blend)
oo=blend.iloc[oos:]; kelly=oo.mean()/oo.var() if oo.var()>0 else 0
print(f"\nblend OOS Kelly ~ {kelly:.2f}x  (use half ~{kelly/2:.2f}x)")
print("=== leverage on blend ===")
for L in [1.0,1.5,2.0,2.5,3.0]:
    o=met(blend.iloc[oos:]*L); print(f"  {L:.1f}x: OOS CAGR {o['C']:7.1f}%  DD {o['DD']:7.1f}%  Sharpe {o['Sh']:.2f}")
