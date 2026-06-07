"""
Paper-trading bot for the validated strategy:
  Donchian 55/20 breakout + 200-MA filter, long-only, ATR stop, ATR-risk sizing.
  ~20-coin Binance basket, 4H. Each coin = its own equal-capital sub-account (mirrors backtest).

NO REAL MONEY. Fetches Binance klines via public REST (no API key). Persists state to state.json,
appends equity to equity_log.csv. Run once per 4H bar (cron / Task Scheduler) or with --loop.

  python paper_bot.py            # run one cycle
  python paper_bot.py --loop     # run forever, cycle every 4h
"""
import sys, os, json, time, csv
from datetime import datetime, timezone
from pathlib import Path
import requests, numpy as np, pandas as pd

HERE = Path(__file__).parent
STATE = HERE / "state.json"
EQLOG = HERE / "equity_log.csv"
TRADELOG = HERE / "trades.csv"

# ---- config (matches validated core) ----
COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","LINKUSDT",
         "LTCUSDT","DOGEUSDT","MATICUSDT","DOTUSDT","ATOMUSDT","NEARUSDT","FILUSDT","UNIUSDT",
         "ETCUSDT","XLMUSDT","ALGOUSDT","ICPUSDT"]
INTERVAL   = "4h"
ENTRY      = 55       # Donchian high
EXIT       = 20       # Donchian low
MA_LEN     = 200
ADX_MIN    = 25
ATR_LEN    = 14
ATR_STOP   = 2.5
RISK_PCT   = 5.0
LEVERAGE   = 3.0      # aggressive (≈full-Kelly): ~50-57% DD expected. 1.0 safe, 2.0 = half-Kelly sweet spot
START_EQUITY = 10000.0
COST = 0.001 + 0.0005 # commission + slippage per side
BASE = "https://api.binance.com/api/v3/klines"

# ---- Telegram alerts (optional) ----
# 1) message @BotFather -> /newbot -> copy the token below
# 2) message your new bot once, then open
#    https://api.telegram.org/bot<TOKEN>/getUpdates  -> copy "chat":{"id":NUMBER}
TG_TOKEN = os.environ.get("TG_TOKEN", "")   # or paste bot token here ("...")
TG_CHAT  = os.environ.get("TG_CHAT", "")    # or paste your chat id here ("...")

def tg(msg):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT, "text": msg}, timeout=10)
    except Exception:
        pass


def fetch(sym, limit=400):
    r = requests.get(BASE, params={"symbol": sym, "interval": INTERVAL, "limit": limit}, timeout=20)
    r.raise_for_status()
    d = r.json()
    df = pd.DataFrame(d, columns=["t","o","h","l","c","v","ct","q","n","tb","tq","ig"])
    for x in ["o","h","l","c"]:
        df[x] = df[x].astype(float)
    return df


def rma(s, n): return s.ewm(alpha=1/n, adjust=False).mean()

def indicators(df):
    h,l,c = df.h, df.l, df.c
    pc = c.shift()
    tr = pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    atr = rma(tr, ATR_LEN)
    up = h.diff(); dn = -l.diff()
    plus = np.where((up>dn)&(up>0),up,0.0); minus=np.where((dn>up)&(dn>0),dn,0.0)
    atrx = rma(tr,14)
    pdi = 100*rma(pd.Series(plus,index=df.index),14)/atrx.replace(0,np.nan)
    mdi = 100*rma(pd.Series(minus,index=df.index),14)/atrx.replace(0,np.nan)
    dx = 100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    adx = rma(dx.fillna(0),14)
    ma = c.rolling(MA_LEN).mean()
    donHi = h.rolling(ENTRY).max()
    donLo = l.rolling(EXIT).min()
    return atr, adx, ma, donHi, donLo


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    sub = START_EQUITY/len(COINS)
    return {"created": now(), "coins": {c: {"cash": sub, "units": 0.0, "entry": 0.0,
            "stop": 0.0, "peak": 0.0} for c in COINS}}

def save_state(s): STATE.write_text(json.dumps(s, indent=2))
def now(): return datetime.now(timezone.utc).isoformat()

def log_trade(row):
    new = not TRADELOG.exists()
    with open(TRADELOG,"a",newline="") as f:
        w=csv.writer(f)
        if new: w.writerow(["time","coin","action","price","units","sub_equity","reason"])
        w.writerow(row)


def write_dashboard(st, total):
    # read equity history
    times, eqs = [], []
    if EQLOG.exists():
        with open(EQLOG) as f:
            next(f, None)
            for line in f:
                p = line.strip().split(",")
                if len(p) == 2:
                    times.append(p[0][:16]); eqs.append(p[1])
    # open positions table
    rows = ""
    for c, cs in st["coins"].items():
        if cs["units"] > 0:
            rows += f"<tr><td>{c}</td><td>{cs['units']:.4f}</td><td>{cs['entry']:.4f}</td><td>{cs['stop']:.4f}</td></tr>"
    if not rows:
        rows = "<tr><td colspan=4 style='text-align:center;color:#888'>no open positions (holding cash)</td></tr>"
    start = 10000.0
    pnl = (total/start - 1)*100
    color = "#16c784" if pnl >= 0 else "#ea3943"
    html = f"""<!doctype html><html><head><meta charset=utf-8><title>QuantPaperBot</title>
<meta http-equiv=refresh content=300>
<script src=https://cdn.jsdelivr.net/npm/chart.js></script>
<style>body{{font-family:system-ui;background:#0e1116;color:#e6e6e6;margin:24px}}
h1{{font-size:20px}} .big{{font-size:34px;font-weight:700;color:{color}}}
table{{border-collapse:collapse;margin-top:16px;width:100%;max-width:640px}}
td,th{{border:1px solid #2a2f3a;padding:6px 10px;text-align:left}} th{{background:#1a1f2b}}
.card{{background:#151a22;padding:18px;border-radius:10px;max-width:900px}}</style></head>
<body><div class=card>
<h1>QuantPaperBot — Donchian 55/20 + 200MA basket (paper, 3x)</h1>
<div>Equity <span class=big>${total:,.2f}</span> &nbsp; ({pnl:+.2f}%) &nbsp; <span style='color:#888'>updated {now()[:16]}</span></div>
<canvas id=c height=90></canvas>
<h3>Open positions</h3>
<table><tr><th>Coin</th><th>Units</th><th>Entry</th><th>Stop</th></tr>{rows}</table>
</div>
<script>
new Chart(document.getElementById('c'),{{type:'line',
data:{{labels:{times},datasets:[{{label:'Equity $',data:{eqs},borderColor:'{color}',
backgroundColor:'rgba(22,199,132,.1)',fill:true,pointRadius:0,tension:.25}}]}},
options:{{plugins:{{legend:{{display:false}}}},scales:{{x:{{ticks:{{color:'#888',maxTicksLimit:8}}}},y:{{ticks:{{color:'#888'}}}}}}}}}});
</script></body></html>"""
    (HERE/"dashboard.html").write_text(html, encoding="utf-8")


def cycle():
    st = load_state()
    total = 0.0; actions = []
    for c in COINS:
        cs = st["coins"][c]
        try:
            df = fetch(c)
        except Exception as e:
            print(f"{c}: fetch fail {e}");
            total += cs["cash"] + cs["units"]*0  # can't mark; skip
            continue
        atr,adx,ma,donHi,donLo = indicators(df)
        i = len(df)-2          # last CLOSED bar (last row is still forming)
        price = df.c.iloc[i]; low = df.l.iloc[i]; high = df.h.iloc[i]
        a = atr.iloc[i]
        sub_eq = cs["cash"] + cs["units"]*price

        if cs["units"] > 0:    # manage open position
            cs["peak"] = max(cs["peak"], high)
            exit_now = (price < donLo.iloc[i-1]) or (low < cs["stop"])
            if exit_now:
                cs["cash"] += cs["units"]*price*(1-COST)
                log_trade([now(),c,"SELL",round(price,6),round(cs["units"],6),round(cs["cash"],2),"exit"])
                actions.append(f"{c} EXIT @ {price:.4f}")
                cs.update(units=0.0, entry=0.0, stop=0.0, peak=0.0)
        else:                  # look for entry
            breakout = price > donHi.iloc[i-1] and adx.iloc[i] > ADX_MIN and price > ma.iloc[i]
            if breakout and a > 0:
                stop_dist = a*ATR_STOP
                units = LEVERAGE*(cs["cash"]*RISK_PCT/100)/stop_dist
                units = min(units, cs["cash"]*0.95*LEVERAGE/price)
                if units > 0:
                    cs["cash"] -= units*price*(1+COST)
                    cs.update(units=units, entry=price, stop=price-stop_dist, peak=high)
                    log_trade([now(),c,"BUY",round(price,6),round(units,6),round(cs["cash"],2),"breakout"])
                    actions.append(f"{c} BUY @ {price:.4f}")
        total += cs["cash"] + cs["units"]*price
    st["last_run"] = now(); st["equity"] = round(total,2)
    save_state(st)
    new = not EQLOG.exists()
    with open(EQLOG,"a",newline="") as f:
        w=csv.writer(f)
        if new: w.writerow(["time","equity"])
        w.writerow([now(), round(total,2)])
    write_dashboard(st, total)
    summary = f"PaperBot ${total:,.2f} ({(total/START_EQUITY-1)*100:+.1f}%) | " + (", ".join(actions) if actions else "no trades")
    tg(summary)
    print(f"{now()}  {summary}")
    return total


if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            try: cycle()
            except Exception as e: print("cycle error:", e)
            time.sleep(4*3600)
    else:
        cycle()
