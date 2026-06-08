"""
Paper-trading bot — tabbed multi-edge book. NO REAL MONEY. 20-coin Binance basket, 4H, public REST.
Accounts tracked in parallel (each its own paper account, $10k):
  TREND    1x/2x/3x  - Donchian 55/20 + 200-MA + BTC-master regime, ATR stop/sizing
  FLUSH    1x/2x/3x  - liquidation-flush reversion (>8% dump + stabilise, magnitude size, +5%/4bar exit)
  CRASHREB 1x/2x/3x  - BTC-crash rebound: BTC dumps >5% in a 4h bar -> buy ALL alts, +5%/3bar exit
  BLEND    1x/2x/3x  - derived 70% trend_1x + 30% flush_1x (the ORIGINAL deployed book — kept)
  BOOK V2  1x/2x/3x  - derived .55 trend + .25 flush + .20 crashreb, scaled x0.3 when BTC<200MA
                       (the UPGRADED book: backtest OOS Sharpe 1.05->1.57, DD 12.9%->7.2%)
Dashboard (web/) reads web/data.json -> tabs: Donchian | Flush | Crashreb | Blend 70/30 | Book v2.
Old tabs kept intact for live comparison; Book v2 is the new recommended system.
"""
import sys, os, json, time, csv
from datetime import datetime, timezone
from pathlib import Path
import requests, numpy as np, pandas as pd

HERE=Path(__file__).parent
COINS=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","LINKUSDT",
       "LTCUSDT","DOGEUSDT","MATICUSDT","DOTUSDT","ATOMUSDT","NEARUSDT","FILUSDT","UNIUSDT",
       "ETCUSDT","XLMUSDT","ALGOUSDT","ICPUSDT"]
INTERVAL="4h"; START=10000.0; COST=0.001+0.0005
ENTRY,EXIT,MA_LEN,ADX_MIN,ATR_LEN,ATR_STOP,RISK_PCT=55,20,200,25,14,4.0,5.0  # ATR_STOP 2.5->4.0: tight stop whipsawed (bear-validated: FULL Sh 1.42->1.49, DD 18%->14%, 2022 -12.7%->-7.7%)
FL_THR,FL_CONFIRM,FL_TARGET,FL_MAXBARS=-0.08,-0.02,0.05,2  # FL_MAXBARS 4->2: capitulation bounces are fast (FULL Sh 0.82->0.90, DD 22%->15.6%, better both OOS halves)
CR_THR,CR_TARGET,CR_MAXBARS=-0.05,0.05,3            # crashreb: BTC<-5% bar -> buy alts, +5%/3bar exit
LEVELS=[1,2,3]; STRATS=["trend","flush","crashreb"]; BLEND_W=(0.7,0.3)
BOOK_W=(0.55,0.25,0.20); BEAR_MULT=0.3              # Book v2 weights + bear-regime exposure scale
REGLOG=HERE/"regime_log.csv"
BASE="https://api.binance.com/api/v3/klines"
TG_TOKEN=os.environ.get("TG_TOKEN",""); TG_CHAT=os.environ.get("TG_CHAT","")

def tg(m):
    if TG_TOKEN and TG_CHAT:
        try: requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",data={"chat_id":TG_CHAT,"text":m},timeout=10)
        except Exception: pass
def now(): return datetime.now(timezone.utc).isoformat()
def acct(strat,lev): return f"{strat}_{lev}x"
def spath(a): return HERE/f"state_{a}.json"
def epath(a): return HERE/f"equity_{a}.csv"
TRADELOG=HERE/"trades.csv"

def fetch(sym,limit=400):
    r=requests.get(BASE,params={"symbol":sym,"interval":INTERVAL,"limit":limit},timeout=20); r.raise_for_status()
    df=pd.DataFrame(r.json(),columns=["t","o","h","l","c","v","ct","q","n","tb","tq","ig"])
    for x in ["o","h","l","c"]: df[x]=df[x].astype(float)
    return df
def rma(s,n): return s.ewm(alpha=1/n,adjust=False).mean()
def indicators(df):
    h,l,c=df.h,df.l,df.c; pc=c.shift()
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1); atr=rma(tr,ATR_LEN)
    up=h.diff(); dn=-l.diff(); plus=np.where((up>dn)&(up>0),up,0.0); minus=np.where((dn>up)&(dn>0),dn,0.0)
    ax=rma(tr,14); pdi=100*rma(pd.Series(plus,index=df.index),14)/ax.replace(0,np.nan); mdi=100*rma(pd.Series(minus,index=df.index),14)/ax.replace(0,np.nan)
    adx=rma((100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)).fillna(0),14)
    return atr,adx,c.rolling(MA_LEN).mean(),h.rolling(ENTRY).max(),l.rolling(EXIT).min()

def load_state(a):
    p=spath(a)
    if p.exists(): return json.loads(p.read_text())
    sub=START/len(COINS)
    return {"coins":{c:{"cash":sub,"units":0.0,"entry":0.0,"stop":0.0,"peak":0.0,"held":0,"size":0.0} for c in COINS}}
def log_trade(row):
    new=not TRADELOG.exists()
    with open(TRADELOG,"a",newline="") as f:
        w=csv.writer(f)
        if new: w.writerow(["time","acct","coin","action","price","units","reason","pnl"])
        w.writerow(row)
def append_eq(a,total):
    p=epath(a); new=not p.exists()
    with open(p,"a",newline="") as f:
        w=csv.writer(f)
        if new: w.writerow(["time","equity"])
        w.writerow([now(),round(total,2)])
def series_of(a):
    p=epath(a); out=[]
    if p.exists():
        with open(p) as f:
            next(f,None)
            for ln in f:
                x=ln.strip().split(",")
                if len(x)==2: out.append([x[0][:16],round(float(x[1]),2)])
    return out
def pnls(a):
    out=[]
    if TRADELOG.exists():
        with open(TRADELOG) as f:
            for row in csv.DictReader(f):
                if row.get("acct")==a and row.get("action")=="SELL" and row.get("pnl"):
                    try: out.append(float(row["pnl"]))
                    except ValueError: pass
    return out
def block(name,series,total,derived=False):
    ev=[s[1] for s in series]; mdd=0.0
    if len(ev)>1:
        pk=ev[0]
        for v in ev: pk=max(pk,v); mdd=min(mdd,v/pk-1)
    yrs=max(len(ev),1)/(365*6); cagr=((total/START)**(1/yrs)-1) if (yrs>0 and total>0 and len(ev)>=60) else 0.0  # guard: don't annualize warmup (few bars -> nonsense CAGR)
    # Sharpe from per-cycle (4h) equity returns, annualised (6 cycles/day)
    sh=0.0
    if len(ev)>=60:  # guard: warmup Sharpe on a few bars is nonsense (-> -68 etc.)
        rr=np.array([ev[i]/ev[i-1]-1 for i in range(1,len(ev)) if ev[i-1]])
        if len(rr)>2 and rr.std()>0: sh=float(rr.mean()/rr.std()*np.sqrt(6*365))
    pl=pnls(name); wins=[x for x in pl if x>0]; los=[x for x in pl if x<=0]
    wr=len(wins)/len(pl)*100 if pl else 0.0
    pf=sum(wins)/abs(sum(los)) if los and sum(los)!=0 else (0.0 if not wins else 999.0)
    return dict(equity=round(total,2),pnl_pct=round((total/START-1)*100,2),cagr=round(cagr*100,1),
                maxdd=round(mdd*100,1),sharpe=round(sh,2),wr=round(wr,1),pf=round(pf,2),
                trades=len(pl),derived=derived,series=series)

def read_regime():
    out=[]
    if REGLOG.exists():
        with open(REGLOG) as f:
            next(f,None)
            for ln in f:
                x=ln.strip().split(",")
                if len(x)==2:
                    try: out.append(int(x[1]))
                    except ValueError: pass
    return out

def write_webdata(totals, states, btc_ok=True):
    tabs=[]
    for strat,label in [("trend","Donchian (trend)"),("flush","Flush reversion"),("crashreb","Crashreb (BTC-crash bounce)")]:
        levels=[{"lev":f"{L}x", **block(acct(strat,L), series_of(acct(strat,L)), totals[acct(strat,L)])} for L in LEVELS]
        tabs.append({"name":label,"levels":levels})
    # cycle return streams from the three 1x sleeves
    ts=series_of("trend_1x"); fs=series_of("flush_1x"); xs=series_of("crashreb_1x"); reglog=read_regime()
    def rets(ser): return [ser[i][1]/ser[i-1][1]-1 if ser[i-1][1] else 0 for i in range(1,len(ser))]
    # ORIGINAL blend 70/30 (kept)
    blevels=[]
    if len(ts)>1 and len(ts)==len(fs):
        times=[r[0] for r in ts]; tr=rets(ts); fr=rets(fs)
        for L in LEVELS:
            eqb=START; ser=[[times[0],START]]
            for i in range(len(tr)):
                eqb*=(1+L*(BLEND_W[0]*tr[i]+BLEND_W[1]*fr[i]))
                ser.append([times[i+1] if i+1<len(times) else now()[:16],round(eqb,2)])
            blevels.append({"lev":f"{L}x", **block(f"blend_{L}x", ser, eqb, derived=True)})
    else:
        blevels=[{"lev":f"{L}x", **block(f"blend_{L}x", [], START, derived=True)} for L in LEVELS]
    tabs.append({"name":"Blend 70/30 (original)","levels":blevels})
    # BOOK V2: .55 trend + .25 flush + .20 crashreb, scaled x0.3 when BTC<200MA (the upgrade).
    # crashreb starts fresh (shorter history) -> align all three on their common TAIL length.
    v2=[]
    k=min(len(ts),len(fs),len(xs))
    if k>1:
        tsk,fsk,xsk=ts[-k:],fs[-k:],xs[-k:]; regk=reglog[-k:] if len(reglog)>=k else reglog
        times=[r[0] for r in tsk]; tr=rets(tsk); fr=rets(fsk); xr=rets(xsk)
        for L in LEVELS:
            eqb=START; ser=[[times[0],START]]
            for i in range(len(tr)):
                bull = regk[i+1] if i+1<len(regk) else (regk[-1] if regk else 1)
                mult = 1.0 if bull else BEAR_MULT
                eqb*=(1+L*mult*(BOOK_W[0]*tr[i]+BOOK_W[1]*fr[i]+BOOK_W[2]*xr[i]))
                ser.append([times[i+1] if i+1<len(times) else now()[:16],round(eqb,2)])
            v2.append({"lev":f"{L}x", **block(f"bookv2_{L}x", ser, eqb, derived=True)})
    else:
        v2=[{"lev":f"{L}x", **block(f"bookv2_{L}x", [], START, derived=True)} for L in LEVELS]
    tabs.append({"name":"Book v2 (upgraded ★)","levels":v2})
    # Diversified Blend ★ — 40% crypto-trend + 40% gold(PAXG) + 20% cash. ALL on Binance (PAXGUSDT), ONE account.
    # LIVE/FORWARD derived track (computed from the live trend sleeve + live PAXG price, no extra trades/state) —
    # same forward-test basis as every other tab. Accrues real out-of-sample results going forward; sits at start
    # during warmup (block() guards CAGR/Sharpe under 60 bars so warmup never annualizes to nonsense).
    # Validated 8y backtest for reference (NOT shown here): 1x 25.8% CAGR / Sharpe 1.24 / -13.4% DD.
    try:
        dbl=[]
        if len(ts)>1:
            times=[r[0] for r in ts]; tr=rets(ts)
            pc=fetch("PAXGUSDT",limit=len(ts)+5)["c"].pct_change().fillna(0).tolist()
            gr=pc[-len(tr):] if len(pc)>=len(tr) else [0.0]*len(tr)
            gr=(gr+[0.0]*len(tr))[:len(tr)]
            for L in LEVELS:
                eqb=START; ser=[[times[0],START]]
                for i in range(len(tr)):
                    eqb*=(1+L*(0.4*tr[i]+0.4*gr[i]))   # +0.2 cash @ 0%
                    ser.append([times[i+1] if i+1<len(times) else now()[:16],round(eqb,2)])
                dbl.append({"lev":f"{L}x", **block(f"divblend_{L}x", ser, eqb, derived=True)})
        else:
            dbl=[{"lev":f"{L}x", **block(f"divblend_{L}x", [], START, derived=True)} for L in LEVELS]
        tabs.append({"name":"Diversified Blend ★ (live · crypto+gold, all-Binance)","levels":dbl})
    except Exception:
        tabs.append({"name":"Diversified Blend ★ (live · crypto+gold, all-Binance)",
                     "levels":[{"lev":f"{L}x", **block(f"divblend_{L}x", [], START, derived=True)} for L in LEVELS]})
    pos=[{"coin":c,"units":round(cs["units"],6),"entry":cs["entry"],"stop":round(cs.get("stop",0),6)}
         for c,cs in states["trend_1x"]["coins"].items() if cs["units"]>0]
    pos+=[{"coin":c+" (flush)","units":round(cs["units"],6),"entry":cs["entry"],"stop":"+5%/2bar"}
          for c,cs in states["flush_1x"]["coins"].items() if cs["units"]>0]
    pos+=[{"coin":c+" (crashreb)","units":round(cs["units"],6),"entry":cs["entry"],"stop":"+5%/3bar"}
          for c,cs in states["crashreb_1x"]["coins"].items() if cs["units"]>0]
    total_trades=sum(L["trades"] for t in tabs for L in t["levels"])
    data={"updated":now()[:16],"start":START,"n_coins":len(COINS),"tabs":tabs,"positions":pos,
          "regime":"bull" if btc_ok else "bear","bookv2_exposure":1.0 if btc_ok else BEAR_MULT,
          "total_trades":total_trades}
    web=HERE.parent/"web"; web.mkdir(exist_ok=True); (web/"data.json").write_text(json.dumps(data),encoding="utf-8")

def cycle():
    accts=[acct(s,L) for s in STRATS for L in LEVELS]
    states={a:load_state(a) for a in accts}; totals={a:0.0 for a in accts}; actions=[]
    btc_crash=False; btc_r_prev=0.0
    try:
        bdf=fetch("BTCUSDT"); _,_,bma,_,_=indicators(bdf); bi=len(bdf)-2; btc_ok=bool(bdf.c.iloc[bi]>bma.iloc[bi])
        btc_r_prev=bdf.c.iloc[bi-1]/bdf.c.iloc[bi-2]-1 if bi>=2 else 0.0
        btc_crash=bool(btc_r_prev<CR_THR)            # BTC dumped >5% on the prior bar -> rebound entry
    except Exception: btc_ok=True
    for c in COINS:
        try: df=fetch(c)
        except Exception as e:
            print(f"{c}: fetch fail {e}")
            for a in accts: totals[a]+=states[a]["coins"][c]["cash"]
            continue
        atr,adx,ma,donHi,donLo=indicators(df); i=len(df)-2
        price,low,high,av=df.c.iloc[i],df.l.iloc[i],df.h.iloc[i],atr.iloc[i]
        r_prev=df.c.iloc[i-1]/df.c.iloc[i-2]-1 if i>=2 else 0.0
        r_now=df.c.iloc[i]/df.c.iloc[i-1]-1 if i>=1 else 0.0
        trend_buy=price>donHi.iloc[i-1] and adx.iloc[i]>ADX_MIN and price>ma.iloc[i] and btc_ok and av>0
        trend_exit=price<donLo.iloc[i-1]
        flush_buy=r_prev<FL_THR and r_now>FL_CONFIRM
        for L in LEVELS:
            # trend
            cs=states[acct("trend",L)]["coins"][c]
            if cs["units"]>0:
                cs["peak"]=max(cs["peak"],high)
                if trend_exit or low<cs["stop"]:
                    pnl=cs["units"]*price*(1-COST)-cs["units"]*cs["entry"]*(1+COST); cs["cash"]+=cs["units"]*price*(1-COST)
                    log_trade([now(),acct("trend",L),c,"SELL",round(price,6),round(cs["units"],6),"exit",round(pnl,2)])
                    if L==1: actions.append(f"trend {c} EXIT")
                    cs.update(units=0.0,entry=0.0,stop=0.0,peak=0.0)
            elif trend_buy:
                sd=av*ATR_STOP; u=L*(cs["cash"]*RISK_PCT/100)/sd; u=min(u,cs["cash"]*0.95*L/price)
                if u>0:
                    cs["cash"]-=u*price*(1+COST); cs.update(units=u,entry=price,stop=price-sd,peak=high)
                    log_trade([now(),acct("trend",L),c,"BUY",round(price,6),round(u,6),"breakout",""])
                    if L==1: actions.append(f"trend {c} BUY")
            totals[acct("trend",L)]+=cs["cash"]+cs["units"]*price
            # flush
            fs=states[acct("flush",L)]["coins"][c]
            if fs["units"]>0:
                if high/fs["entry"]-1>=FL_TARGET or fs["held"]>=FL_MAXBARS:
                    pnl=fs["units"]*price*(1-COST)-fs["units"]*fs["entry"]*(1+COST); fs["cash"]+=fs["units"]*price*(1-COST)
                    log_trade([now(),acct("flush",L),c,"SELL",round(price,6),round(fs["units"],6),"bounce/timeout",round(pnl,2)])
                    if L==1: actions.append(f"flush {c} EXIT")
                    fs.update(units=0.0,entry=0.0,held=0,size=0.0)
                else: fs["held"]+=1
            elif flush_buy:
                size=min(3.0,abs(r_prev)/0.10); u=L*size*fs["cash"]*0.95/price
                if u>0:
                    fs["cash"]-=u*price*(1+COST); fs.update(units=u,entry=price,held=1,size=size)
                    log_trade([now(),acct("flush",L),c,"BUY",round(price,6),round(u,6),f"flush {r_prev*100:.0f}%",""])
                    if L==1: actions.append(f"flush {c} BUY")
            totals[acct("flush",L)]+=fs["cash"]+fs["units"]*price
            # crashreb (BTC-wide crash -> buy alts; BTC itself excluded)
            xs=states[acct("crashreb",L)]["coins"][c]
            if xs["units"]>0:
                if high/xs["entry"]-1>=CR_TARGET or xs["held"]>=CR_MAXBARS:
                    pnl=xs["units"]*price*(1-COST)-xs["units"]*xs["entry"]*(1+COST); xs["cash"]+=xs["units"]*price*(1-COST)
                    log_trade([now(),acct("crashreb",L),c,"SELL",round(price,6),round(xs["units"],6),"bounce/timeout",round(pnl,2)])
                    if L==1: actions.append(f"crashreb {c} EXIT")
                    xs.update(units=0.0,entry=0.0,held=0,size=0.0)
                else: xs["held"]+=1
            elif btc_crash and c!="BTCUSDT":
                u=L*xs["cash"]*0.95/price
                if u>0:
                    xs["cash"]-=u*price*(1+COST); xs.update(units=u,entry=price,held=1,size=1.0)
                    log_trade([now(),acct("crashreb",L),c,"BUY",round(price,6),round(u,6),f"BTC crash {btc_r_prev*100:.0f}%",""])
                    if L==1: actions.append(f"crashreb {c} BUY")
            totals[acct("crashreb",L)]+=xs["cash"]+xs["units"]*price
    # log master regime this cycle (for Book v2 bear-scaling reconstruction)
    try:
        rnew=not REGLOG.exists()
        with open(REGLOG,"a",newline="") as f:
            w=csv.writer(f)
            if rnew: w.writerow(["time","btc_ok"])
            w.writerow([now(),int(btc_ok)])
    except Exception: pass
    for a in accts:
        states[a]["last_run"]=now(); states[a]["equity"]=round(totals[a],2)
        spath(a).write_text(json.dumps(states[a],indent=2)); append_eq(a,totals[a])
    write_webdata(totals,states,btc_ok)
    summ=f"trend1x ${totals['trend_1x']:,.0f} flush1x ${totals['flush_1x']:,.0f} crashreb1x ${totals['crashreb_1x']:,.0f}"+(f" | {', '.join(actions)}" if actions else " | no trades")
    tg("PaperBot "+summ); print(f"{now()}  {summ}")

if __name__=="__main__":
    if "--loop" in sys.argv:
        while True:
            try: cycle()
            except Exception as e: print("cycle error:",e)
            time.sleep(4*3600)
    else: cycle()
