"""
Extended history test: majors over 2018-2026 (deep+bear+main), to stress the strategy on the
2018 bear (BTC -84%) + 2019-2020 chop — the regime the critique said was untested.
Trend basket 55/20 + 200-MA (+ optional BTC master regime). Segment metrics.
"""
import numpy as np, pandas as pd
from pathlib import Path
from engine import load, backtest

DATA=Path(__file__).parent/"data"; DPY=365
MAJORS=["BTCUSDT","ETHUSDT","LTCUSDT","XRPUSDT","BNBUSDT","ADAUSDT","EOSUSDT","NEOUSDT","XLMUSDT","TRXUSDT"]
coins=[s for s in MAJORS if (DATA/f"{s}_deep_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()]

def merged(s):
    parts=[]
    for stem in [f"{s}_deep", f"{s}_bear", s]:
        if (DATA/f"{stem}_4h.csv").exists():
            parts.append(load(stem,"4h",DATA))
    df=pd.concat(parts)
    return df[~df.index.duplicated(keep="first")].sort_index()

M={s:merged(s) for s in coins}
btc=M["BTCUSDT"].close; btc_reg=btc>btc.rolling(200).mean()

def basket(cfg):
    rs=[]
    for s in coins:
        eq,_=backtest(M[s],cfg)
        rs.append(eq.resample("1D").last().ffill().pct_change().rename(s))
    return pd.concat(rs,axis=1).fillna(0.0).mean(axis=1)

def met(pr):
    pr=pr.dropna()
    if len(pr)<30 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    c=eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else -1
    dd=(eq/eq.cummax()-1).min(); sh=pr.mean()/pr.std()*np.sqrt(DPY)
    return (c*100,dd*100,sh)

cfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=2.5,adx_filter=True,ma_filter=200,btc_regime=btc_reg)
pr=basket(cfg)
print(f"{len(coins)} majors, {len(pr)} days  ({str(pr.index[0])[:10]} -> {str(pr.index[-1])[:10]})\n")

def seg(t,a,b):
    s=pr[(pr.index>=pd.Timestamp(a,tz='UTC'))&(pr.index<pd.Timestamp(b,tz='UTC'))]
    c,d,sh=met(s); print(f"  {t:22s} CAGR {c:7.1f}%  DD {d:7.1f}%  Sharpe {sh:5.2f}")

print("=== trend basket 55/20 + MA200 + BTC-regime, by regime ===")
seg("2018 bear (Jan-Dec)","2018-01-01","2019-01-01")
seg("2019-2020 chop","2019-01-01","2021-01-01")
seg("2021-2022 (bull+bear)","2021-01-01","2023-01-01")
seg("2023-2026","2023-01-01","2026-07-01")
seg("FULL 2018-2026","2018-01-01","2026-07-01")
