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
BAR_MS=4*3600*1000  # width of one INTERVAL bar in ms — mirrors INTERVAL="4h"; change the two together
ENTRY,EXIT,MA_LEN,ADX_MIN,ATR_LEN,ATR_STOP,RISK_PCT=55,20,200,25,14,4.0,5.0  # ATR_STOP 2.5->4.0: tight stop whipsawed (bear-validated: FULL Sh 1.42->1.49, DD 18%->14%, 2022 -12.7%->-7.7%)
FL_THR,FL_CONFIRM,FL_TARGET,FL_MAXBARS=-0.08,-0.02,0.05,2  # FL_MAXBARS 4->2: capitulation bounces are fast (FULL Sh 0.82->0.90, DD 22%->15.6%, better both OOS halves)
CR_THR,CR_TARGET,CR_MAXBARS=-0.05,0.05,3            # crashreb: BTC<-5% bar -> buy alts, +5%/3bar exit
LEVELS=[1,2,3]; STRATS=["trend","flush","crashreb"]; BLEND_W=(0.7,0.3)
BOOK_W=(0.55,0.25,0.20); BEAR_MULT=0.3              # Book v2 weights + bear-regime exposure scale
REGLOG=HERE/"regime_log.csv"
# --- derived-dashboard constants (single source; referenced across write_webdata's derived tabs) ---
SWITCH_COST=2*COST                       # a derived-state change pays two legs (entry+exit / spot+perp) at the per-leg cost used everywhere
DIV_W=(0.4,0.4)                          # Diversified Blend: 40% trend + 40% gold (+20% cash @0%)
TG_W=(0.5,0.5)                           # 50/50 Trend+Gold
CPPI_FLOOR,CPPI_MULT=0.90,5.0            # CPPI: protect 90% of the running peak; exposure = clip(MULT*cushion,0,1)
REG_FAST_ALT,REG_SLOW_ALT=300,900        # Regime A/B "50/150" — 50d/150d-equiv SMAs on 4h bars
REG_FAST_CANON,REG_SLOW_CANON=600,1200   # Regime A/B "100/200" — 100d/200d-equiv SMAs on 4h bars
PRICE_MARGIN=8                           # extra 4h bars so the nearest-preceding join covers the first cycle
CARRY_TRAIL_N=21                         # carry side-decision window: 7 days x 3 funding periods (trailing only)
CARRY_BAND=0.00003                       # carry side hysteresis: enter above ~+3% ann funding, exit below ~-3%
FROTH_ENTER=0.00005                      # carry froth gate: size up when trailing funding annualizes hot
FROTH_EXIT=FROTH_ENTER/2                 # froth hysteresis: size back down only below HALF the entry threshold
CARRY_SIZE_HOT,CARRY_SIZE_COOL=1.0,0.3   # carry position size when frothy vs calm
HR_LEV_HOT,HR_LEV_COOL=1.0,1.5           # Blend High-Return leverage when BTC funding hot vs cool
HR_TRAIL_N=3                             # trailing funding periods for the high-return throttle decision
FROTH_FUND_ANN=0.15                      # annualized BTC funding above which the high-return blend throttles down
REBAL_CAVEAT=("Idealized: rebalances to fixed weights every cycle with no rebalancing cost — the gold/cash "
              "legs trade frictionlessly; live rebalancing would incur fees/slippage.")
# Binance market-data hosts, tried in order. data-api.binance.vision is the PUBLIC data mirror
# that is NOT geo-blocked from cloud IPs — api.binance.com returns 451 from GitHub Actions (the
# silent "0 trades — holding cash" freeze: every kline fetch was failing). Falls back for resilience.
KLINE_HOSTS=["https://data-api.binance.vision","https://api.binance.com"]
BASE=KLINE_HOSTS[0]+"/api/v3/klines"
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

KLINE_PAGE=1000  # Binance hard cap per klines request (>1000 is silently clamped) -> page backward via endTime
def fetch(sym,limit=400):
    last=None
    for host in KLINE_HOSTS:                                  # vision mirror first (cloud-safe), then api.binance.com
        try:
            rows={}                                           # open-time(ms) -> raw kline row; dedupe across pages
            end=None                                          # endTime cursor; None = most-recent page
            while len(rows)<limit:                            # page backward until `limit` bars are honestly satisfied
                params={"symbol":sym,"interval":INTERVAL,"limit":min(KLINE_PAGE,limit-len(rows))}
                if end is not None: params["endTime"]=end
                r=requests.get(host+"/api/v3/klines",params=params,timeout=20); r.raise_for_status()
                page=r.json()
                if not page: break                            # exchange returned nothing more
                before=len(rows)
                for row in page: rows[int(row[0])]=row        # dedupe on open-time
                if len(rows)==before: break                   # no NEW bars -> stop (guard against a non-advancing loop)
                end=int(page[0][0])-1                         # next page ends just before this page's oldest bar
                if len(page)<KLINE_PAGE: break                # short page -> reached the start of available history
            ordered=[rows[t] for t in sorted(rows)][-limit:]  # chronological; honor the requested tail length
            df=pd.DataFrame(ordered,columns=["t","o","h","l","c","v","ct","q","n","tb","tq","ig"])
            for x in ["o","h","l","c"]: df[x]=df[x].astype(float)
            return df
        except Exception as e:
            last=e; continue
    raise last or RuntimeError(f"all kline hosts failed for {sym}")
FUNDING_URL="https://fapi.binance.com/fapi/v1/fundingRate"
FUNDING_SRC="none"   # which source served funding this run (binance-live | binance-archive | none) — surfaced to the UI
def _vision_funding(sym,limit):
    """Cloud-safe funding from Binance's OWN public archive (data.binance.vision). fapi.binance.com is
    geo-blocked from US/GitHub IPs (451), and Bybit/OKX also block US IPs — so the only EXACT-Binance,
    cloud-reachable funding is the monthly archive zips. These finalize at month-end (current partial
    month 404s), so the live throttle may lag ~days; the carry tab (historical) is exact. Walks back
    month-by-month until it has `limit` 8h points."""
    import zipfile, io
    from datetime import timedelta
    base="https://data.binance.vision/data/futures/um/monthly/fundingRate"
    out=[]; d=datetime.now(timezone.utc).replace(day=1); months=0; misses=0
    while len(out)<limit and months<16:
        ym=d.strftime("%Y-%m")
        try:
            r=requests.get(f"{base}/{sym}/{sym}-fundingRate-{ym}.zip",timeout=20)
            if r.status_code==200:
                rows=zipfile.ZipFile(io.BytesIO(r.content)).read(zipfile.ZipFile(io.BytesIO(r.content)).namelist()[0]).decode().splitlines()
                for ln in rows:
                    p=ln.split(",")
                    if p and p[0].isdigit(): out.append((int(p[0]),float(p[2])))  # calc_time, last_funding_rate
                misses=0
            else:
                misses+=1
                if misses>=2 and not out: break    # current + prior month both absent and nothing yet
        except Exception:
            pass
        d=(d-timedelta(days=1)).replace(day=1)     # previous month
        months+=1
    out.sort()                                     # chronological, to match fapi order
    return out[-limit:]
def fetch_funding(sym,limit=500):  # perp funding rate history (8h periods)
    global FUNDING_SRC
    try:                             # 1) Binance fapi — exact + real-time, works on a non-US/home IP
        r=requests.get(FUNDING_URL,params={"symbol":sym,"limit":min(limit,1000)},timeout=20); r.raise_for_status()
        data=[(int(x["fundingTime"]),float(x["fundingRate"])) for x in r.json()]
        if data: FUNDING_SRC="binance-live"; return data
    except Exception:
        pass
    try:                             # 2) Binance Vision monthly archive — exact, cloud-safe (what CI uses)
        data=_vision_funding(sym,limit)
        if data: FUNDING_SRC="binance-archive"
        return data
    except Exception:
        return []
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
    return {"coins":{c:{"cash":sub,"units":0.0,"entry":0.0,"stop":0.0,"peak":0.0,"trough":0.0,"held":0,"bars":0,"size":0.0} for c in COINS}}
def log_trade(row):
    new=not TRADELOG.exists()
    with open(TRADELOG,"a",newline="") as f:
        w=csv.writer(f)
        if new: w.writerow(["time","acct","coin","action","price","units","reason","pnl"])
        w.writerow(row)
TRADEDETAIL=HERE/"trades_detail.csv"  # analysis-grade per-trade close-log: R-multiple, MAE/MFE, hold (additive to trades.csv)
def log_detail(acct_,coin,entry,exit_,stop,units,hold,pnl,peak,trough,reason):
    # NEVER let logging break the trade loop — fully guarded. R = pnl / initial-risk((entry-stop)*units);
    # MFE/MAE = best/worst excursion vs entry during the hold (where stops hurt / how much was left on the table).
    try:
        risk=units*(entry-stop) if (entry>0 and stop>0 and entry>stop) else 0.0
        Rm=round(pnl/risk,3) if risk>0 else ""
        mfe=round((peak/entry-1)*100,2) if (entry and peak) else ""
        mae=round((trough/entry-1)*100,2) if (entry and trough) else ""
        new=not TRADEDETAIL.exists()
        with open(TRADEDETAIL,"a",newline="") as f:
            w=csv.writer(f)
            if new: w.writerow(["time","acct","coin","entry","exit","stop","units","hold_bars","pnl","R_multiple","MFE_pct","MAE_pct","reason"])
            w.writerow([now(),acct_,coin,round(entry,6),round(exit_,6),round(stop,6) if stop else "",round(units,6),hold,round(pnl,2),Rm,mfe,mae,reason])
    except Exception: pass
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
FUNDING_PERIODS_PER_DAY_NOMINAL=3   # Binance funding prints every 8h; fallback only - periods with
                                    # no ETH print are skipped, so measure the real cadence when you can
CYCLES_PER_DAY_NOMINAL=6   # what the cron PROMISES (.github/workflows/paper_bot.yml: 5 */4 * * *).
                           # Never annualise with this: GitHub Actions delays and drops scheduled
                           # runs, so real delivery has been ~4.9/day. Measured cadence wins; this
                           # is only the fallback when a series is too short to measure.

def _span_days(series):
    """Real wall-clock span of an equity series, in days.

    Annualising off len(series)/(365*6) assumed every promised cycle ran. ~17% never did, so the
    window was understated by the same ~17% and every CAGR/Sharpe on the board was inflated
    (audit 2026-10-03 FINDING 1). Timestamps are the only honest source of elapsed time.
    Series carry two shapes: full ISO with offset (the equity CSVs) and 'YYYY-MM-DDTHH:MM'
    (everything built in-process), so normalise to naive UTC before subtracting.
    """
    def _dt(v):
        d=datetime.fromisoformat(str(v))
        return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d
    try:
        d=(_dt(series[-1][0])-_dt(series[0][0])).total_seconds()/86400.0
        return d if d>0 else 0.0
    except Exception:
        return 0.0

def block(name,series,total,derived=False):
    ev=[s[1] for s in series]; mdd=0.0
    if len(ev)>1:
        pk=ev[0]
        for v in ev: pk=max(pk,v); mdd=min(mdd,v/pk-1)
    span=_span_days(series)                                    # REAL elapsed, not an assumed cadence
    cpd=(len(ev)-1)/span if (span>0 and len(ev)>1) else CYCLES_PER_DAY_NOMINAL   # MEASURED cycles/day
    yrs=span/365.0 if span>0 else max(len(ev),1)/(365.0*CYCLES_PER_DAY_NOMINAL)
    cagr=((total/START)**(1/yrs)-1) if (yrs>0 and total>0 and len(ev)>=60) else 0.0  # guard: don't annualize warmup (few bars -> nonsense CAGR)
    # Sharpe from per-cycle equity returns, annualised at the cadence the series ACTUALLY ran at.
    sh=0.0
    if len(ev)>=60:  # guard: warmup Sharpe on a few bars is nonsense (-> -68 etc.)
        rr=np.array([ev[i]/ev[i-1]-1 for i in range(1,len(ev)) if ev[i-1]])
        if len(rr)>2 and rr.std()>0: sh=max(min(float(rr.mean()/rr.std()*np.sqrt(cpd*365)),5.0),-5.0)  # cap ±5 (near-constant series -> giant fake Sharpe)
    pl=pnls(name); wins=[x for x in pl if x>0]; los=[x for x in pl if x<=0]
    wr=len(wins)/len(pl)*100 if pl else 0.0
    pf=sum(wins)/abs(sum(los)) if los and sum(los)!=0 else (0.0 if not wins else 99.99)  # cap (no-loss = "infinite" PF); avoid alarming 999 sentinel
    pf=min(pf,99.99)  # never display absurd profit-factor
    return dict(equity=round(total,2),pnl_pct=round((total/START-1)*100,2),cagr=round(cagr*100,1),
                span_days=round(span,2),cycles_per_day=round(cpd,3),
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

# --- timestamp-join helpers for the gold/BTC-bearing derived tabs (DD5/DD6) ---
def _iso_ms(iso):
    """cycle timestamp (ISO, minute-truncated, tz-aware or naive-UTC) -> epoch ms."""
    dt_=datetime.fromisoformat(iso)
    if dt_.tzinfo is None: dt_=dt_.replace(tzinfo=timezone.utc)
    return int(dt_.timestamp()*1000)
def align_series(df,times_ms):
    """Timestamp join: for each cycle time, the close of the nearest bar whose OPEN-time precedes it
    (searchsorted). None where the cycle predates the first bar -> caller DROPS it, never zero-fills."""
    ot=df["t"].astype("int64").values; cl=df["c"].astype(float).values; out=[]
    for tm in times_ms:
        j=int(np.searchsorted(ot,tm,side="right"))-1
        out.append(float(cl[j]) if j>=0 else None)
    return out
def align_flags(df,flags,times_ms):
    """Like align_series but for a regime-flag series (1.0/0.0/NaN). None where the nearest bar's flag is
    undefined (MA warmup) or the cycle predates the first bar -> DD6: warmup cycles are omitted, not faked."""
    ot=df["t"].astype("int64").values; fv=np.asarray(flags,dtype=float); out=[]
    for tm in times_ms:
        j=int(np.searchsorted(ot,tm,side="right"))-1
        out.append(float(fv[j]) if (j>=0 and fv[j]==fv[j]) else None)
    return out
def price_to_rets(prices):
    """aligned prices (len n) -> per-WINDOW returns (len n-1); None where either endpoint is undefined."""
    out=[]
    for i in range(len(prices)-1):
        a,b=prices[i],prices[i+1]
        out.append((b/a-1) if (a is not None and b is not None and a>0) else None)
    return out
def switch_costs(exposure,defined,prev0=0.0):
    """SWITCH_COST on |Δexposure| between consecutive DEFINED windows (DD4); the first defined window pays
    entry from `prev0` (0 = from flat). Returns a per-window cost list (None where the window is undefined)."""
    out=[None]*len(exposure); prev=prev0
    for i in range(len(exposure)):
        if not defined[i]: continue
        out[i]=SWITCH_COST*abs(exposure[i]-prev); prev=exposure[i]
    return out
def curve_block(key,times,net,derived=True):
    """Build 1x/2x/3x equity blocks from per-window net returns. net[i]=None OMITS that window entirely
    (DD6 warmup / DD5 missing-bar / DD7 funding-gap honesty -> a shorter curve, never a fake flat point)."""
    lv=[]
    for L in LEVELS:
        eqb=START; ser=[]
        for i in range(len(net)):
            if net[i] is None: continue
            if not ser: ser=[[times[i],START]]
            eqb*=(1+L*net[i])
            ser.append([times[i+1] if i+1<len(times) else now()[:16],round(eqb,2)])
        lv.append({"lev":f"{L}x", **block(f"{key}_{L}x", ser, eqb, derived=derived)})
    return lv

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
    # REMOVED 2026-06-08: "Blend 70/30 (original)" tab — redundant, superseded by Book v2 + Diversified Blend.
    # (blevels left computed but not shown; sleeves untouched.) tabs.append({"name":"Blend 70/30 (original)","levels":blevels})
    # BOOK V2: .55 trend + .25 flush + .20 crashreb, scaled x0.3 when BTC<200MA (the upgrade).
    # crashreb starts fresh (shorter history) -> align all three on their common TAIL length.
    v2=[]
    k=min(len(ts),len(fs),len(xs))
    if k>1:
        tsk,fsk,xsk=ts[-k:],fs[-k:],xs[-k:]; regk=reglog[-k:] if len(reglog)>=k else reglog
        times=[r[0] for r in tsk]; tr=rets(tsk); fr=rets(fsk); xr=rets(xsk)
        for L in LEVELS:
            eqb=START; ser=[[times[0],START]]; prev_mult=None
            for i in range(len(tr)):
                # DD2 causality: the regime known at a window's START scales THAT window's return.
                # regk[i] is logged at cycle i (window start); regk[i+1] was end-of-window = look-ahead.
                bull = regk[i] if i<len(regk) else (regk[-1] if regk else 1)
                mult = 1.0 if bull else BEAR_MULT
                if prev_mult is None: prev_mult=mult                       # always-deployed overlay -> no inception cost, only flips pay
                sw = SWITCH_COST*abs(mult-prev_mult)                       # DD4b: a regime flip moves |Δexposure| notional -> costs like every other switch
                eqb*=(1+L*(mult*(BOOK_W[0]*tr[i]+BOOK_W[1]*fr[i]+BOOK_W[2]*xr[i]) - sw))
                prev_mult=mult
                ser.append([times[i+1] if i+1<len(times) else now()[:16],round(eqb,2)])
            v2.append({"lev":f"{L}x", **block(f"bookv2_{L}x", ser, eqb, derived=True)})
    else:
        v2=[{"lev":f"{L}x", **block(f"bookv2_{L}x", [], START, derived=True)} for L in LEVELS]
    tabs.append({"name":"Book v2 (upgraded ★)","levels":v2})
    # ---- Gold/BTC-bearing derived tabs: ONE shared timestamp-joined setup (DD5/DD6) ----
    # Cycle timestamps are irregular bot run-times with gaps; klines sit on clean 4h boundaries. Each cycle is
    # joined to the nearest-preceding bar (never positional tail-align, never zero-fill); cycles with no bar or an
    # undefined regime MA are dropped so the curve is honestly shorter. Each price source is fetched ONCE and reused.
    trr=rets(ts) if len(ts)>1 else []
    if len(ts)>1:
        times=[r[0] for r in ts]; times_ms=[_iso_ms(t) for t in times]
        span_bars=int((int(time.time()*1000)-times_ms[0])//BAR_MS)+PRICE_MARGIN     # 4h bars spanning the whole cycle range
        try: gld=price_to_rets(align_series(fetch("PAXGUSDT",span_bars),times_ms))   # per-window gold return, None where no bar
        except Exception: gld=[None]*len(trr)
        try:
            bc_df=fetch("BTCUSDT",span_bars+REG_SLOW_CANON)                          # deep enough for the 200d (1200-bar) MA on EVERY cycle
            btc_win=price_to_rets(align_series(bc_df,times_ms))
        except Exception:
            bc_df=None; btc_win=[None]*len(trr)
    else:
        times=[now()[:16]]; times_ms=[]; gld=[]; btc_win=[]; bc_df=None
    def _empty_levels(key): return [{"lev":f"{L}x", **block(f"{key}_{L}x", [], START, derived=True)} for L in LEVELS]

    # Diversified Blend ★ — 40% crypto-trend + 40% gold(PAXG) + 20% cash. ONE derived track (no extra trades/state);
    # block() guards CAGR/Sharpe under 60 bars so warmup never annualizes to nonsense. Ref 8y backtest (not shown):
    # 1x 25.8% CAGR / Sharpe 1.24 / -13.4% DD.
    try:
        net=[DIV_W[0]*trr[i]+DIV_W[1]*gld[i] if (i<len(gld) and gld[i] is not None) else None for i in range(len(trr))]
        tabs.append({"name":"Diversified Blend (40/40/20) ★ core","levels":curve_block("divblend",times,net),"caveat":REBAL_CAVEAT})
    except Exception:
        tabs.append({"name":"Diversified Blend (40/40/20) ★ core","levels":_empty_levels("divblend"),"caveat":REBAL_CAVEAT})
    # Regime A/B forward-test (CLEAN) — both tabs gate RAW BTC returns PURELY by their own regime MA, so 50/150 vs
    # canonical 100/200 differ ONLY by the window = a faithful live A/B of the R3 free-upgrade. 40% regime-gated-BTC +
    # 40% gold + 20% cash. Causal: the MA-warmup bars are UNDEFINED (dropped, DD6 — never faked as "cash"); shift(1)
    # keeps the regime one bar behind; the BTC leg pays SWITCH_COST on every entry/exit (DD4a).
    def regime_ab(label,key,fast,slow):
        try:
            if bc_df is None: raise RuntimeError("no BTC bars")
            bc=bc_df["c"].astype(float); maf=bc.rolling(fast).mean(); mas=bc.rolling(slow).mean()
            reg=((bc>maf)&(bc>mas)).astype(float).mask(maf.isna()|mas.isna())        # NaN during MA warmup -> stays undefined, not False
            reg=reg.shift(1)                                                          # regime known at prior close applies to this bar (no lookahead)
            reg_on=align_flags(bc_df,reg,times_ms)                                    # per-cycle flag; None where warmup / pre-first-bar
            defined=[(i<len(gld) and gld[i] is not None and btc_win[i] is not None and reg_on[i] is not None) for i in range(len(trr))]
            exposure=[(DIV_W[0]*reg_on[i]) if (reg_on[i] is not None) else 0.0 for i in range(len(trr))]  # BTC-leg notional: 0 or 0.4
            cost=switch_costs(exposure,defined,prev0=0.0)                             # DD4a: BTC-leg entry/exit pays on |Δexposure|
            net=[(DIV_W[0]*btc_win[i]*reg_on[i]+DIV_W[1]*gld[i]-cost[i]) if defined[i] else None for i in range(len(trr))]
            tabs.append({"name":label,"levels":curve_block(key,times,net),"caveat":REBAL_CAVEAT})
        except Exception:
            tabs.append({"name":label,"levels":_empty_levels(key),"caveat":REBAL_CAVEAT})
    regime_ab("Regime A/B · 50/150 SMA (clean) ★","reg50150",REG_FAST_ALT,REG_SLOW_ALT)
    regime_ab("Regime A/B · canonical 100/200 SMA (clean)","reg100200",REG_FAST_CANON,REG_SLOW_CANON)
    # Diversified Blend + CPPI floor ★ risk-off — path-dependent drawdown floor on the 40/40/20 blend (HALVES CAGR but
    # floors maxDD; gross<=1 so no financing). Causal: exposure e_t from PRE-cycle equity vs trailing CPPI_FLOOR*peak.
    try:
        base=[DIV_W[0]*trr[i]+DIV_W[1]*gld[i] if (i<len(gld) and gld[i] is not None) else None for i in range(len(trr))]
        cpp=[]
        for L in LEVELS:
            eqb=START; ser=[]; peak=START
            for i in range(len(base)):
                if base[i] is None: continue                                         # DD6: drop cycles with no gold bar
                if not ser: ser=[[times[i],START]]
                floor=CPPI_FLOOR*peak; cush=(eqb-floor)/eqb if eqb>0 else 0.0
                et=max(0.0,min(CPPI_MULT*cush,1.0))                                   # CPPI exposure 0..1 (gross<=1, no financing)
                eqb*=(1+et*base[i]); peak=max(peak,eqb)                               # <=1x BY DESIGN; no L (2x/3x mirror 1x, like the board)
                ser.append([times[i+1] if i+1<len(times) else now()[:16],round(eqb,2)])
            cpp.append({"lev":f"{L}x", **block(f"divcppi_{L}x", ser, eqb, derived=True)})
        tabs.append({"name":"Diversified Blend + CPPI floor ★ R3 risk-off","levels":cpp,"caveat":REBAL_CAVEAT})
    except Exception:
        tabs.append({"name":"Diversified Blend + CPPI floor ★ R3 risk-off","levels":_empty_levels("divcppi"),"caveat":REBAL_CAVEAT})
    # --- Gold / 50-50 / Blend-HR / BTC buy-hold (all timestamp-joined, block() guarded) ---
    # DD3: the funding throttle is a CAUSAL per-cycle series computed from the TRAILING funding known at each cycle's
    # START (was one current-funding value stamped retroactively over all history).
    try: fr_hist=fetch_funding("BTCUSDT",1000)
    except Exception: fr_hist=[]
    def hr_lev_at(cycle_ms):
        trail=[r for ft,r in fr_hist if ft<=cycle_ms][-HR_TRAIL_N:]                   # only funding printed before the cycle start
        ann=(sum(trail)/len(trail))*3*365 if trail else 0.0
        return HR_LEV_HOT if ann>FROTH_FUND_ANN else HR_LEV_COOL
    hr=[hr_lev_at(times_ms[i]) for i in range(len(trr))]                              # decision at window START times[i]
    try:
        def _gold_net(fn): return [fn(i) if (i<len(gld) and gld[i] is not None) else None for i in range(len(trr))]
        tabs.append({"name":"Gold (PAXG) ★ diversifier","levels":curve_block("goldph",times,_gold_net(lambda i: gld[i]))})
        tabs.append({"name":"50/50 Trend+Gold ★ (aggressive)","levels":curve_block("tg5050",times,_gold_net(lambda i: TG_W[0]*trr[i]+TG_W[1]*gld[i])),"caveat":REBAL_CAVEAT})
        tabs.append({"name":f"Blend High-Return ★ (levered <=2x, funding-throttled {HR_LEV_HOT}–{HR_LEV_COOL}x)",
                     "levels":curve_block("blendhr",times,_gold_net(lambda i: hr[i]*(DIV_W[0]*trr[i]+DIV_W[1]*gld[i]))),"caveat":REBAL_CAVEAT})
        bh=[btc_win[i] if (i<len(btc_win) and btc_win[i] is not None) else None for i in range(len(trr))]
        tabs.append({"name":"BTC buy-hold (benchmark)","levels":curve_block("btchold",times,bh)})
    except Exception:
        pass
    # Funding / Carry ★ — delta-neutral perp funding harvest (the real retail edge; ~8-20% APY, low DD).
    # REAL Binance funding history (8h). Delta-neutral (long spot + short perp) => price PnL ~0, you collect funding.
    # Leverage is RELATIVELY sane here (market-neutral) so 3x = high-octane yield, not directional blow-up.
    # HONEST SIM (2026-07-17 fix — the old version took abs(funding) every period = teleporting to the paying
    # side for free, which overstates carry in a low/sign-flipping regime): the position is long-spot/short-perp
    # or FLAT, the side is decided from TRAILING funding only (no lookahead), surprise negative periods are PAID,
    # and every state change costs two legs (spot + perp) at the same COST used everywhere else. The froth SIZE gate
    # now has its own hysteresis (enter at FROTH_ENTER, exit only below half — mirrors the side switch) and a resize
    # pays SWITCH_COST on the |Δsize| notional (DD4c). ETH funding gaps are SKIPPED and counted (DD7 — never bridged
    # with BTC's rate). block() annualization is wrong for 8h periods, so stats computed here at 3 periods/day.
    def fund_block(key,ser,eqf,L):
        ev=[s[1] for s in ser]; mdd=0.0; pk=ev[0] if ev else START
        for v in ev: pk=max(pk,v); mdd=min(mdd,v/pk-1)
        # Funding prints every 8h = 3 periods/day NOMINALLY, but periods with no ETH funding are
        # deliberately SKIPPED (DD7), so len(ev) is not elapsed time here either - the same defect
        # block() carried (audit FINDING 1; caught in the Codex cross-check of that fix). Measure.
        span=_span_days(ser)
        ppd=(len(ev)-1)/span if (span>0 and len(ev)>1) else FUNDING_PERIODS_PER_DAY_NOMINAL
        yrs=span/365.0 if span>0 else (len(ev)/(FUNDING_PERIODS_PER_DAY_NOMINAL*365.0) if ev else 0)
        cagr=((eqf/START)**(1/yrs)-1) if (yrs>0 and eqf>0 and len(ev)>=60) else 0.0
        rr=np.array([ev[i]/ev[i-1]-1 for i in range(1,len(ev))]) if len(ev)>1 else np.array([])
        sh=float(rr.mean()/rr.std()*np.sqrt(ppd*365)) if (len(rr)>=60 and rr.std()>0) else 0.0
        sh=min(sh,3.0) if sh>0 else max(sh,-3.0)  # cap: pure-carry vol is ~0 => raw Sharpe inflates (60+); real basis risk caps practical ~2-3
        return {"lev":f"{L}x","equity":round(eqf,2),"pnl_pct":round((eqf/START-1)*100,2),
                "cagr":round(cagr*100,1),"maxdd":round(mdd*100,1),"sharpe":round(sh,2),
                "span_days":round(span,2),"periods_per_day":round(ppd,3),
                "wr":round(float((rr>0).mean()*100),1) if len(rr) else 0.0,"pf":0.0,"trades":0,
                "derived":True,"series":ser}
    try:
        fb=fetch_funding("BTCUSDT",1000); fe=dict(fetch_funding("ETHUSDT",1000))
        # 1000 8h periods = ~333 days of exchange history, but the live-forward test started when the
        # equity series did. Shown whole, this tab silently BACKFILLED ~7 months of backtest and put
        # its Sharpe in the same table as live-forward results (audit 2026-10-03 FINDING 2; that pass
        # read the limit=500 DEFAULT and under-reported the overlap ~4x).
        # The sim still RUNS over the full history - the side/size decisions read a TRAILING window, so
        # cutting the input would cold-start them inside the displayed window and invent a flat opening
        # stretch. Only the DISPLAYED series is cut, rebased to START at the live boundary, so the curve
        # is comparable with every other tab while the signal stays warm. live0 comes from the equity
        # series itself - never a pasted date.
        live0=times_ms[0] if times_ms else None
        eth_skipped=0
        if len(fb)>=60:
            fl=[]
            for L in LEVELS:
                eqf=START; ser=[]; hist=[]; pos=0; gate=CARRY_SIZE_COOL; skipped=0; eq0=None
                for t,rbt in fb:
                    if t not in fe:                                 # DD7: no ETH funding this period -> skip + count (don't bridge with BTC's rate)
                        skipped+=1; continue
                    ret=fe[t]
                    w=hist[-CARRY_TRAIL_N:]; sig=sum(w)/len(w) if w else 0.0
                    want=pos
                    if pos==0 and sig>CARRY_BAND: want=1
                    elif pos==1 and sig<-CARRY_BAND: want=0
                    newgate=gate                                    # DD4c: froth gate is now hysteretic (was a bare threshold -> flip-churned)
                    if gate<CARRY_SIZE_HOT and sig>=FROTH_ENTER: newgate=CARRY_SIZE_HOT
                    elif gate>=CARRY_SIZE_HOT and sig<FROTH_EXIT: newgate=CARRY_SIZE_COOL
                    side_cost=SWITCH_COST if want!=pos else 0.0     # entry/exit = full two-leg switch (existing)
                    gate_cost=SWITCH_COST*abs(newgate-gate) if (pos==1 and want==1) else 0.0  # resize an OPEN position (|0.7| notional); entry cost already covers a fresh open
                    pnl=want*newgate*(rbt+ret)/2.0 - side_cost - gate_cost
                    in_win=(live0 is None or t>=live0)
                    if in_win and eq0 is None and eqf>0: eq0=eqf   # equity ENTERING the displayed window
                    eqf*=(1+L*pnl)
                    pos=want; gate=newgate; hist.append((rbt+ret)/2.0)
                    if in_win and eq0:
                        ser.append([datetime.fromtimestamp(t/1000,timezone.utc).isoformat()[:16],
                                    round(START*eqf/eq0,2)])
                eq_disp=START*eqf/eq0 if (eq0 is not None and eq0>0) else eqf   # window shown, not the warmup
                fl.append(fund_block(f"funding_{L}x",ser,eq_disp,L)); eth_skipped=skipped
            cav=("Shown over the live-forward window only (rebased at the equity series' start) so its "
                 "Sharpe is comparable with the other tabs; the sim itself warms up on the full funding "
                 "history." if live0 else
                 "WARNING: no equity history was available this run, so this tab shows the FULL funding "
                 "history (~333d) and is NOT comparable with the live-forward tabs.")
            tabs.append({"name":"Funding / Carry ★ (delta-neutral, real edge)","levels":fl,
                         "eth_funding_skipped":eth_skipped,
                         "caveat":cav+" Pure carry has near-zero vol, so its Sharpe runs into the +-3 cap"
                                      " - do not read it as better than the directional legs."})
        else:
            tabs.append({"name":"Funding / Carry ★ (delta-neutral, real edge)",
                         "levels":[fund_block(f"funding_{L}x",[],START,L) for L in LEVELS],"eth_funding_skipped":0})
    except Exception:
        tabs.append({"name":"Funding / Carry ★ (delta-neutral, real edge)",
                     "levels":[fund_block(f"funding_{L}x",[],START,L) for L in LEVELS],"eth_funding_skipped":0})
    pos=[{"coin":c,"strat":"trend","units":round(cs["units"],6),"entry":cs["entry"],"stop":round(cs.get("stop",0),6)}
         for c,cs in states["trend_1x"]["coins"].items() if cs["units"]>0]
    pos+=[{"coin":c,"strat":"flush","units":round(cs["units"],6),"entry":cs["entry"],"stop":"+5%/2bar"}
          for c,cs in states["flush_1x"]["coins"].items() if cs["units"]>0]
    pos+=[{"coin":c,"strat":"crashreb","units":round(cs["units"],6),"entry":cs["entry"],"stop":"+5%/3bar"}
          for c,cs in states["crashreb_1x"]["coins"].items() if cs["units"]>0]
    total_trades=sum(L["trades"] for t in tabs for L in t["levels"])
    data={"updated":now()[:16],"start":START,"n_coins":len(COINS),"tabs":tabs,"positions":pos,
          "regime":"bull" if btc_ok else "bear","bookv2_exposure":1.0 if btc_ok else BEAR_MULT,
          "total_trades":total_trades,"funding_src":FUNDING_SRC,
          "price_src":KLINE_HOSTS[0].replace("https://","")}
    web=HERE.parent/"web"; web.mkdir(exist_ok=True)
    def _clean(o):  # strip NaN/Inf -> 0.0 so the JSON is always valid (else browser res.json() throws, board silently dies)
        if isinstance(o,float): return o if (o==o and o not in (float("inf"),float("-inf"))) else 0.0
        if isinstance(o,dict): return {k:_clean(v) for k,v in o.items()}
        if isinstance(o,list): return [_clean(x) for x in o]
        return o
    (web/"data.json").write_text(json.dumps(_clean(data),allow_nan=False),encoding="utf-8")

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
                cs["peak"]=max(cs["peak"],high); cs["trough"]=min(cs.get("trough") or cs["entry"],low); cs["bars"]=cs.get("bars",0)+1
                stop_hit=low<=cs["stop"]   # TOUCH triggers a stop, not a strict breach (Codex cross-check 2026-10-06)
                if trend_exit or stop_hit:
                    # A stop is an INTRABAR event: it triggers on the bar LOW, so it cannot fill at the
                    # bar CLOSE. Booking the close let a wick-and-recover bar exit ABOVE the stop - a price
                    # the market never offered. The levered accounts stop out more often, harvested that
                    # bias more often, and so showed Sharpe RISING with leverage (2.47/2.60/2.70), which
                    # leverage cannot do (audit 2026-10-03 FINDING 3). min() also keeps the gap-down case
                    # honest: a bar closing below the stop is the worse fill a stop-market would have got.
                    # A Donchian signal exit still fills at the close - that signal IS a close.
                    fill=min(price,cs["stop"]) if stop_hit else price
                    pnl=cs["units"]*fill*(1-COST)-cs["units"]*cs["entry"]*(1+COST); cs["cash"]+=cs["units"]*fill*(1-COST)
                    log_trade([now(),acct("trend",L),c,"SELL",round(fill,6),round(cs["units"],6),"stop" if stop_hit else "exit",round(pnl,2)])
                    log_detail(acct("trend",L),c,cs["entry"],fill,cs.get("stop",0.0),cs["units"],cs.get("bars",0),pnl,cs.get("peak",0.0),cs.get("trough",0.0),"stop" if stop_hit else "exit")
                    if L==1: actions.append(f"trend {c} EXIT")
                    cs.update(units=0.0,entry=0.0,stop=0.0,peak=0.0,trough=0.0,bars=0)
            elif trend_buy:
                sd=av*ATR_STOP; u=L*(cs["cash"]*RISK_PCT/100)/sd; u=min(u,cs["cash"]*0.95*L/price)
                if u>0:
                    cs["cash"]-=u*price*(1+COST); cs.update(units=u,entry=price,stop=price-sd,peak=high,trough=low,bars=0)
                    log_trade([now(),acct("trend",L),c,"BUY",round(price,6),round(u,6),"breakout",""])
                    if L==1: actions.append(f"trend {c} BUY")
            totals[acct("trend",L)]+=cs["cash"]+cs["units"]*price
            # flush
            fs=states[acct("flush",L)]["coins"][c]
            if fs["units"]>0:
                fs["peak"]=max(fs.get("peak") or fs["entry"],high); fs["trough"]=min(fs.get("trough") or fs["entry"],low)
                tgt_hit=high/fs["entry"]-1>=FL_TARGET
                if tgt_hit or fs["held"]>=FL_MAXBARS:
                    # Same bug, mirrored: the target is detected on the bar HIGH, so the fill is the TARGET
                    # (a limit sell resting there fills when touched) - not a close that may sit above it
                    # (free money) or below it (a phantom loss on a trade that really hit its target).
                    # A timeout exit has no resting order, so it fills at the close.
                    fill=fs["entry"]*(1+FL_TARGET) if tgt_hit else price
                    pnl=fs["units"]*fill*(1-COST)-fs["units"]*fs["entry"]*(1+COST); fs["cash"]+=fs["units"]*fill*(1-COST)
                    log_trade([now(),acct("flush",L),c,"SELL",round(fill,6),round(fs["units"],6),"bounce" if tgt_hit else "timeout",round(pnl,2)])
                    log_detail(acct("flush",L),c,fs["entry"],fill,0.0,fs["units"],fs.get("held",0),pnl,fs.get("peak",0.0),fs.get("trough",0.0),"bounce" if tgt_hit else "timeout")
                    if L==1: actions.append(f"flush {c} EXIT")
                    fs.update(units=0.0,entry=0.0,held=0,size=0.0,peak=0.0,trough=0.0)
                else: fs["held"]+=1
            elif flush_buy:
                size=min(3.0,abs(r_prev)/0.10); u=L*size*fs["cash"]*0.95/price; u=min(u,fs["cash"]*0.95*L/price)  # clamp notional <= L*cash (size no longer stacks on L -> kills the ~8.5x over-leverage)
                if u>0:
                    fs["cash"]-=u*price*(1+COST); fs.update(units=u,entry=price,held=1,size=size,peak=high,trough=low)
                    log_trade([now(),acct("flush",L),c,"BUY",round(price,6),round(u,6),f"flush {r_prev*100:.0f}%",""])
                    if L==1: actions.append(f"flush {c} BUY")
            totals[acct("flush",L)]+=fs["cash"]+fs["units"]*price
            # crashreb (BTC-wide crash -> buy alts; BTC itself excluded)
            xs=states[acct("crashreb",L)]["coins"][c]
            if xs["units"]>0:
                xs["peak"]=max(xs.get("peak") or xs["entry"],high); xs["trough"]=min(xs.get("trough") or xs["entry"],low)
                tgt_hit=high/xs["entry"]-1>=CR_TARGET
                if tgt_hit or xs["held"]>=CR_MAXBARS:
                    fill=xs["entry"]*(1+CR_TARGET) if tgt_hit else price   # target fills AT the target, see flush above
                    pnl=xs["units"]*fill*(1-COST)-xs["units"]*xs["entry"]*(1+COST); xs["cash"]+=xs["units"]*fill*(1-COST)
                    log_trade([now(),acct("crashreb",L),c,"SELL",round(fill,6),round(xs["units"],6),"bounce" if tgt_hit else "timeout",round(pnl,2)])
                    log_detail(acct("crashreb",L),c,xs["entry"],fill,0.0,xs["units"],xs.get("held",0),pnl,xs.get("peak",0.0),xs.get("trough",0.0),"bounce" if tgt_hit else "timeout")
                    if L==1: actions.append(f"crashreb {c} EXIT")
                    xs.update(units=0.0,entry=0.0,held=0,size=0.0,peak=0.0,trough=0.0)
                else: xs["held"]+=1
            elif btc_crash and c!="BTCUSDT":
                u=L*xs["cash"]*0.95/price
                if u>0:
                    xs["cash"]-=u*price*(1+COST); xs.update(units=u,entry=price,held=1,size=1.0,peak=high,trough=low)
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
