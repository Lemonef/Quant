"""
FREE on-chain edge test (CoinMetrics community API, BTC). The classic theses:
  - exchange NETFLOW (in-out): coins leaving exchanges = accumulation = bullish; inflow = sell pressure
  - active addresses growth = network demand = bullish
Test: do these predict forward BTC + basket returns? Does an on-chain overlay beat the 200-MA regime
filter on the book? On-chain is BTC-only here (free tier) -> use as a MARKET-TIMING overlay, like funding.
If it works FREE -> real new-data edge (and justifies paying for all-coin on-chain). 2021-2026.
"""
import numpy as np, pandas as pd, requests
from pathlib import Path
from engine import load, backtest
DATA=Path(__file__).parent/"data"; DPY=365
U="https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
def cm(asset,metrics):
    out=[]; nxt=None
    while True:
        p={"assets":asset,"metrics":metrics,"frequency":"1d","page_size":10000,"start_time":"2020-06-01"}
        if nxt: p["next_page_token"]=nxt
        r=requests.get(U,params=p,timeout=30).json()
        out+=r.get("data",[]); nxt=r.get("next_page_token")
        if not nxt: break
    df=pd.DataFrame(out); df.index=pd.to_datetime(df["time"],utc=True).dt.normalize()
    for m in metrics.split(","):
        if m in df: df[m]=pd.to_numeric(df[m],errors="coerce")
    return df
oc=cm("btc","FlowInExNtv,FlowOutExNtv,AdrActCnt")
oc["netflow"]=oc["FlowInExNtv"]-oc["FlowOutExNtv"]      # +inflow(bearish) / -outflow(bullish)
print(f"on-chain rows: {len(oc)}  {oc.index.min().date()}..{oc.index.max().date()}")

def have(s): return (DATA/f"{s}_bear_4h.csv").exists() and (DATA/f"{s}_4h.csv").exists()
coins=sorted({p.stem[:-3] for p in DATA.glob("*_4h.csv") if not p.stem.endswith("_bear") and have(p.stem[:-3])})
def merged(s):
    df=pd.concat([load(f"{s}_bear","4h",DATA), load(s,"4h",DATA)]); return df[~df.index.duplicated(keep="first")].sort_index()
M={s:merged(s) for s in coins}
px=pd.DataFrame({s:M[s].close for s in coins}).resample("1D").last().ffill()
basket=px.pct_change().mean(axis=1); basket.index=basket.index.normalize()

nf=oc["netflow"].reindex(basket.index).ffill()
nfz=(nf-nf.rolling(30).mean())/nf.rolling(30).std()    # netflow z (high=inflow=bearish)
adr=oc["AdrActCnt"].reindex(basket.index).ffill()
adrg=(adr/adr.rolling(30).mean()-1)                    # active-address growth vs 30d

fwd=basket.rolling(7).sum().shift(-7)
print("\nforward 7d basket return vs BTC exchange-netflow z (high z = inflows = supposed bearish):")
d=pd.DataFrame({"z":nfz,"fwd":fwd}).dropna()
for lo,hi,lab in [(-9,-1,"z<-1 (outflow/accum)"),(-1,-0.3,"-1..-0.3"),(-0.3,0.3,"neutral"),(0.3,1,"0.3..1"),(1,9,"z>1 (inflow/sell)")]:
    v=d[(d.z>=lo)&(d.z<hi)].fwd
    print(f"  {lab:22s} n={len(v):5d} fwd7d {v.mean()*100:7.2f}%  vs base {d.fwd.mean()*100:6.2f}%")
print("\nforward 7d vs active-address growth (high = network demand = bullish?):")
d2=pd.DataFrame({"g":adrg,"fwd":fwd}).dropna()
for lo,hi,lab in [(-9,-0.05,"g<-5% (shrinking)"),(-0.05,0,"-5..0%"),(0,0.05,"0..5%"),(0.05,9,"g>5% (growing)")]:
    v=d2[(d2.g>=lo)&(d2.g<hi)].fwd
    print(f"  {lab:18s} n={len(v):5d} fwd7d {v.mean()*100:7.2f}%  vs base {d2.fwd.mean()*100:6.2f}%")

# overlay: book exposure cut when net INFLOW high (distribution) vs 200-MA
btc=M["BTCUSDT"].close; reg200=(btc>btc.rolling(200).mean()).resample("1D").last()
tcfg=dict(strat="donchian",entry=55,exit=20,risk=5,stop_mult=4.0,adx_filter=True,ma_filter=200,btc_regime=(btc>btc.rolling(200).mean()))
trend=pd.concat([backtest(M[s],tcfg)[0].resample("1D").last().ffill().pct_change().rename(s) for s in coins],axis=1).fillna(0.0).mean(axis=1)
IDX=trend.index; trend.index=trend.index.normalize(); IDX=trend.index; oo=int(len(IDX)*0.6)
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
    return (pd.Series(p,index=c.index).shift(1).fillna(0)*c.pct_change()-pd.Series(p,index=c.index).diff().abs().fillna(0)*0.0008).rename(s)
flush=((1+pd.concat([flush_coin(s) for s in coins],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1)
flush.index=flush.index.normalize(); flush=flush.reindex(IDX).fillna(0)
alts=[c for c in coins if c!="BTCUSDT"]
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
crash=((1+pd.concat([cc(s) for s in alts],axis=1).fillna(0).mean(axis=1)).resample("1D").prod()-1)
crash.index=crash.index.normalize(); crash=crash.reindex(IDX).fillna(0)
book=0.55*trend+0.25*flush+0.20*crash
def met(pr):
    pr=pr.dropna()
    if len(pr)<10 or pr.std()==0: return (0,0,0)
    eq=(1+pr).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))
reg200d=reg200.reindex(IDX).ffill().fillna(False); nfzb=nfz.reindex(IDX).ffill()
ov={
 "200-MA x0.3 (current)": reg200d.map(lambda b:1.0 if b else 0.3),
 "netflow z<1 full/z>1 x0.3": (nfzb<1.0).map(lambda b:1.0 if b else 0.3),
 "200MA AND netflow<1": ((reg200d)&(nfzb<1.0)).map(lambda b:1.0 if b else 0.3),
}
print("\nbook exposure overlay:")
for nm,o in ov.items():
    b=book*o.reindex(IDX).fillna(1.0); f=met(b); oo_=met(b.iloc[oo:])
    print(f"  {nm:28s} FULL Sh{f[2]:.2f} DD{f[1]:6.1f}% | OOS Sh{oo_[2]:.2f} DD{oo_[1]:6.1f}%")
print("\nif netflow/address predicts (table) or overlay beats 200-MA -> FREE on-chain edge is real.")
