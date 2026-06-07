"""
PROVE the cross-asset diversification thesis: run the SAME trend engine (Donchian breakout) on
other asset classes (futures/indices) via free yfinance daily data. Check:
  1. does trend-following WORK outside crypto? (per-asset Sharpe)
  2. are those trend returns UNCORRELATED to crypto trend? (corr matrix)
  3. does a multi-asset trend book have HIGHER Sharpe than crypto alone? (the free lunch)
Long/SHORT Donchian (futures go both ways), inverse-vol sized so assets combine at equal risk.
Daily, ~2010-2026.
"""
import numpy as np, pandas as pd, yfinance as yf
DPY=252
ASSETS={
 "BTC (crypto)":"BTC-USD","ETH (crypto)":"ETH-USD",
 "Gold":"GC=F","Oil":"CL=F","NatGas":"NG=F","Copper":"HG=F",
 "S&P500":"ES=F","Nasdaq":"NQ=F","Bonds10y":"ZN=F","Dollar":"DX=F",
 "Corn":"ZC=F","Soybean":"ZS=F",
}
N_ENTRY,N_EXIT=50,25
def trend_returns(close):
    c=close.dropna()
    if len(c)<300: return None
    hi=c.rolling(N_ENTRY).max().shift(1); lo=c.rolling(N_EXIT).min().shift(1)
    pos=pd.Series(np.nan,index=c.index)
    pos[c>hi]=1.0; pos[c<lo]=-1.0; pos=pos.ffill().fillna(0.0)
    r=c.pct_change()
    raw=pos.shift(1)*r - pos.diff().abs().fillna(0)*0.0002
    # inverse-vol scale to ~15% annual target so assets combine at equal risk
    rv=raw.rolling(60).std()*np.sqrt(DPY)
    scaled=raw*(0.15/rv.shift(1)).clip(upper=3).fillna(1.0)
    return scaled
def met(pr):
    pr=pr.dropna()
    if len(pr)<60 or pr.std()==0: return (0,0,0)
    eq=(1+pr.fillna(0)).cumprod(); yrs=len(eq)/DPY
    return ((eq.iloc[-1]**(1/yrs)-1)*100 if eq.iloc[-1]>0 else -100,(eq/eq.cummax()-1).min()*100,pr.mean()/pr.std()*np.sqrt(DPY))

print("downloading daily data (free yfinance)...")
rets={}
for name,tk in ASSETS.items():
    try:
        df=yf.download(tk,start="2010-01-01",progress=False,auto_adjust=True)
        if df is None or len(df)==0: print(f"  {name:14s} NO DATA"); continue
        close=df["Close"]; close=close.iloc[:,0] if hasattr(close,'columns') else close
        tr=trend_returns(close)
        if tr is None: print(f"  {name:14s} too short"); continue
        rets[name]=tr; f=met(tr); print(f"  {name:14s} trend: CAGR{f[0]:6.1f}% DD{f[1]:6.1f}% Sharpe{f[2]:5.2f}")
    except Exception as e: print(f"  {name:14s} err {e}")

R=pd.DataFrame(rets).dropna(how="all")
if len(R.columns)>=4:
    print("\ncorrelation of trend returns (crypto vs rest):")
    print(R.corr().round(2).to_string())
    cry=[c for c in R.columns if "crypto" in c]; oth=[c for c in R.columns if "crypto" not in c]
    print("\n=== THE TEST: does adding non-crypto trend stack Sharpe? ===")
    def port(cols):
        p=R[cols].mean(axis=1); return met(p)
    fc=port(cry); print(f"  crypto-only trend book      CAGR{fc[0]:6.1f}% DD{fc[1]:6.1f}% Sharpe{fc[2]:5.2f}")
    fo=port(oth); print(f"  non-crypto (futures) book   CAGR{fo[0]:6.1f}% DD{fo[1]:6.1f}% Sharpe{fo[2]:5.2f}")
    fa=port(list(R.columns)); print(f"  ALL-ASSET combined book     CAGR{fa[0]:6.1f}% DD{fa[1]:6.1f}% Sharpe{fa[2]:5.2f}")
    print("\nif ALL-ASSET Sharpe > crypto-only -> diversification stacks = the real 'do better'.")
    print("then leverage that higher-Sharpe book -> higher CAGR at SAME drawdown.")
