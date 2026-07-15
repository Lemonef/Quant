"""
gen_stocks.py — build web/stocks.html from the LIVE ledger (brain memory/paper-trades.md).

Parses ALL open positions (PAPER OWN + REAL OWN) straight from paper-trades.md so the page
NEVER goes stale or shows only one name — re-run it and it reflects the current book exactly.
Prices via yfinance (accurate close, not the routine's intraday bad-ticks).

    python web/gen_stocks.py   ->  web/stocks.html

Brain path resolution order: $SECOND_BRAIN env -> ~/SecondBrain -> D:/second-brain -> ../second-brain -> ./second-brain
(so it works locally AND in a CI job that clones the brain alongside this repo).
"""
import json, os, re, datetime
from pathlib import Path
import yfinance as yf
try:
    import requests
except ImportError:
    requests = None


def find_brain():
    cands = [os.environ.get("SECOND_BRAIN"), os.path.expanduser("~/SecondBrain"), r"D:/second-brain", "../second-brain", "./second-brain"]
    for c in cands:
        if c and (Path(c) / "memory" / "paper-trades.md").exists():
            return Path(c)
    return None


def first_price(cell):
    """Extract the entry price from a messy Entry$ cell. Prefer 'avg ~$X' if present."""
    m = re.search(r"avg\s*~?\$?\s*([0-9]+(?:\.[0-9]+)?)", cell, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", cell)
    return float(m.group(1)) if m else None


def parse_positions(brain):
    """Parse PAPER OWN + REAL OWN table rows from paper-trades.md."""
    text = (brain / "memory" / "paper-trades.md").read_text(encoding="utf-8")
    rows = []
    section = None
    for line in text.splitlines():
        if "PAPER OWN" in line and line.startswith("##"):
            section = "PAPER"; continue
        if "REAL OWN" in line and line.startswith("##"):
            section = "REAL"; continue
        if line.startswith("##"):
            section = None; continue
        if section and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 10:
                continue
            tk = cells[0]
            if tk in ("Ticker", "") or tk.startswith("-") or tk.startswith("_") or "none yet" in tk.lower():
                continue
            entry = first_price(cells[2])
            if entry is None:
                continue
            sc = cells[9]
            head = sc[:45].upper()                          # detect CLOSED on the LEADING status, not "open-market" later in the cell
            closed = ("CLOSED" in head) or ("SOLD" in head)
            exit_px = None
            if closed:
                m = re.search(r"@\s*~?\$?\s*([0-9]+(?:\.[0-9]+)?)", sc)   # "SOLD ... @ ~$8.91"
                if m:
                    exit_px = float(m.group(1))
            sm = re.search(r"([0-9][0-9,]*)\s*฿", cells[2])              # deployed size (baht) from the entry cell
            size_baht = int(sm.group(1).replace(",", "")) if sm else None
            rows.append(dict(
                ticker=re.sub(r"[^A-Z]", "", tk.upper())[:6],
                name=tk,
                entry_date=cells[1][:10],
                entry=entry,
                flavor=cells[3][:60],
                closed=closed,
                status="EXITED" if closed else "OPEN",
                exit=exit_px, exit_date=None,
                size_baht=size_baht,
                book=section,
                note=re.sub(r"\s+", " ", cells[4])[:240],
            ))
    return rows


def parse_capital(brain):
    """Pull the money headline from paper-trades.md RUNNING TOTAL (sleeve / dry / realized, in ฿)."""
    text = (brain / "memory" / "paper-trades.md").read_text(encoding="utf-8")
    def baht(pat):
        m = re.search(pat, text)
        if not m:
            return None
        return int(m.group(1).replace(",", "").replace("−", "-").replace("−", "-"))
    return {
        "sleeve":   baht(r"[Ss]leeve value[^0-9~]*~?\s*([0-9,]+)\s*฿"),
        "dry":      baht(r"[Dd]ry powder[^0-9~]*~?\s*([0-9,]+)\s*฿"),
        "realized": baht(r"[Rr]ealized P&L[^0-9\-−]*([\-−]?[0-9,]+)\s*฿"),
    }


def _drop_glitches(out, jump=0.25):
    """Drop lone bad-tick bars: a close that jumps >`jump` from BOTH neighbors in
    opposite directions (a spike that immediately reverts = data glitch, e.g. the
    RCAT $14.98 tick). Real gaps/trends move ONE direction and survive — only a
    spike-and-revert is removed. Keeps the last price honest for %P&L."""
    if len(out) < 3:
        return out
    keep = [out[0]]
    for i in range(1, len(out) - 1):
        prev, cur, nxt = out[i - 1][1], out[i][1], out[i + 1][1]
        up = cur > prev * (1 + jump) and cur > nxt * (1 + jump)            # spike up then back
        dn = cur < prev * (1 - jump) and cur < nxt * (1 - jump)            # spike down then back
        if not (up or dn):
            keep.append(out[i])
    keep.append(out[-1])
    return keep


def _stooq_hist(tkr, days=400):
    """Fallback price source — stooq daily CSV. Works from GitHub Actions cloud IPs,
    where Yahoo/yfinance is frequently rate-limited/blocked (the silent-freeze cause)."""
    if requests is None:
        return []
    try:
        url = f"https://stooq.com/q/d/l/?s={tkr.lower()}.us&i=d"
        r = requests.get(url, timeout=20)
        if r.status_code != 200 or "Date" not in r.text[:50]:
            return []
        out = []
        for ln in r.text.strip().splitlines()[1:]:
            p = ln.split(",")
            if len(p) < 5:
                continue
            try:
                fv = float(p[4])
            except ValueError:
                continue
            if fv == fv and fv > 0:
                out.append([p[0], round(fv, 2)])
        return out[-days:]
    except Exception:
        return []


def hist(tkr, days=400):
    out = []
    try:
        h = yf.Ticker(tkr).history(period=f"{days}d")["Close"].dropna()   # drop NaN closes
        for i, v in h.items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv == fv and fv > 0:                                       # fv==fv filters NaN
                out.append([str(i.date()), round(fv, 2)])
    except Exception:
        out = []
    if not out:                                                           # yfinance empty/blocked -> stooq
        out = _stooq_hist(tkr, days)
    return _drop_glitches(out)                                            # strip lone bad-tick bars


def _write_health(component, info):
    """Heartbeat: merge this component's status into web/health.json so there's ONE
    machine-readable record of when each piece last successfully updated (stocks /
    scans / crypto bot). A page can show it; you can eyeball it; CI can alert on it."""
    p = Path("web/health.json")
    h = {}
    if p.exists():
        try:
            h = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            h = {}
    h[component] = info
    p.write_text(json.dumps(h, indent=2), encoding="utf-8")


def main():
    brain = find_brain()
    if not brain:
        raise SystemExit("paper-trades.md not found — set $SECOND_BRAIN or place brain at D:/second-brain")
    positions = parse_positions(brain)
    out = []
    for h in positions:
        series = hist(h["ticker"])
        cur = series[-1][1] if series else h["entry"]                     # no valid prices → fall back to entry (never NaN)
        if cur is None or cur != cur:                                     # cur!=cur catches NaN
            cur = h["entry"]
        ref = h["exit"] if h["exit"] else cur                            # closed → realized vs exit; open → unrealized vs current
        pnl = round((ref - h["entry"]) / h["entry"] * 100, 1) if (h["entry"] and ref is not None) else 0.0
        out.append({**h, "current": cur, "pnl": pnl, "series": series})
    # open positions first, then exited; within each newest entry first
    out.sort(key=lambda o: (o["closed"], o["entry_date"]), reverse=False)
    DATA = json.dumps(out)
    cap = parse_capital(brain)
    cap["n_open"]   = sum(1 for o in out if not o["closed"])
    cap["n_closed"] = sum(1 for o in out if o["closed"])
    cap["holding"]  = round(sum((o["size_baht"] or 0) * (1 + o["pnl"]/100) for o in out if not o["closed"]))
    cap["deployed"] = sum((o["size_baht"] or 0) for o in out if not o["closed"])
    cap["unreal"]   = round(sum((o["size_baht"] or 0) * (o["pnl"]/100) for o in out if not o["closed"]))
    CAP = json.dumps(cap)
    build_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    asof = max((o["series"][-1][0] for o in out if o["series"]), default="no-data")

    html = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spike Hunter — stock paper trades</title>
<link rel="stylesheet" href="./style.css">
<style>
 .cols{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}
 .list{flex:0 0 270px;min-width:240px}
 .item{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:10px;cursor:pointer;transition:.16s}
 .item:hover{border-color:var(--line2);transform:translateY(-1px)} .item.sel{border-color:var(--up)}
 .item .t{font-family:var(--mono);font-weight:700;font-size:14px} .item .p{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:2px}
 .main{flex:1;min-width:460px}
 .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:16px}
 .summary{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:0 0 16px}
 .scard{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:11px;padding:11px 13px}
 .scard .k{font-family:var(--mono);color:var(--mut);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase}
 .scard .v{font-family:var(--mono);font-size:17px;font-weight:700;margin-top:3px}
 .postabs{display:flex;gap:7px;margin:0 0 12px}
 .ptab{font-family:var(--mono);font-size:12.5px;background:var(--ink2);border:1px solid var(--line);color:var(--mut);padding:7px 14px;border-radius:9px;cursor:pointer;transition:.15s}
 .ptab:hover{color:var(--txt);border-color:var(--line2)} .ptab.active{background:linear-gradient(180deg,#1b2942,#16223a);color:#fff;border-color:var(--accent)}
 @media(max-width:560px){.summary{grid-template-columns:repeat(2,1fr)}}
 .kpi{background:var(--ink2);border:1px solid var(--line);border-radius:10px;padding:11px 13px}
 .kpi .k{font-family:var(--mono);color:var(--mut);font-size:10px;letter-spacing:.1em;text-transform:uppercase}
 .kpi .v{font-family:var(--mono);font-size:19px;font-weight:700;margin-top:3px}
 canvas{width:100%;height:340px;background:var(--ink2);border:1px solid var(--line);border-radius:10px;margin-top:6px}
 .pos{color:var(--up)} .neg{color:var(--dn)}
 .freshbar{font-family:var(--mono);font-size:12.5px;font-weight:600;border-radius:10px;padding:9px 14px;margin:0 0 18px;border:1px solid var(--line);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
 .freshbar.ok{background:rgba(39,211,138,.08);border-color:rgba(39,211,138,.35);color:var(--up)}
 .freshbar.stale{background:rgba(255,90,106,.12);border-color:var(--dn);color:var(--dn)}
 .freshbar .sub{color:var(--mut);font-weight:500}
 .tag{font-family:var(--mono);font-size:10.5px;font-weight:700;padding:3px 9px;border-radius:6px;background:rgba(39,211,138,.13);color:var(--up);border:1px solid rgba(39,211,138,.3)}
 .tag.closed{background:rgba(183,156,255,.13);color:var(--accent2);border-color:rgba(183,156,255,.3)}
 @media(max-width:560px){.main{min-width:0} .kpis{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<div class="wrap">
<p class="eyebrow">Equities · Spike Hunter</p>
<h1>Stock <span class="thin">Paper Trades</span></h1>
<p class="lede">Live paper track of the spike-hunter framework, built straight from the brain ledger (<code>paper-trades.md</code>) — never stale. Real price history (yfinance close), entry markers, unrealized P&amp;L.</p>
<div id="nav"></div>
<script src="./nav.js"></script>
<div id="fresh" class="freshbar"></div>
<div id="summary" class="summary"></div>
<div id="postabs" class="postabs"></div>
<div class="cols">
 <div class="list" id="list"></div>
 <div class="main"><div class="card">
  <h2 id="nm" style="margin:0 0 4px">—</h2><div class="note" id="note" style="margin-bottom:14px"></div>
  <div class="kpis">
   <div class="kpi"><div class="k">Entry</div><div class="v" id="ke">—</div></div>
   <div class="kpi"><div class="k">Size</div><div class="v" id="kz">—</div></div>
   <div class="kpi"><div class="k" id="kcl">Current</div><div class="v" id="kc">—</div></div>
   <div class="kpi"><div class="k" id="kpl">P&amp;L</div><div class="v" id="kp">—</div></div>
   <div class="kpi"><div class="k">Status</div><div class="v" id="ks">—</div></div>
   <div class="kpi"><div class="k">Flavor</div><div class="v" id="kf" style="font-size:12px">—</div></div>
  </div>
  <canvas id="cv" width="900" height="680"></canvas>
  <table id="log" style="margin-top:14px"><thead><tr><th>Date</th><th>Action</th><th>Price</th><th>Note</th></tr></thead><tbody></tbody></table>
 </div></div>
</div>
<footer>Built from the brain ledger · prices via yfinance · paper only · not financial advice · Lemonef/Quant</footer>
</div>
<script>
 const DATA=__DATA__, CAP=__CAP__, ASOF="__ASOF__", BUILT="__BUILT__";
 let posTab="current";
 let sel=DATA.find(o=>!o.closed)||DATA[0];
 const B=v=>(v==null?"—":(v<0?"-":"")+"฿"+Math.abs(v).toLocaleString());
 (function(){const s=document.getElementById("summary");if(!s||!CAP)return;
  const cells=[["Sleeve",B(CAP.sleeve)],["Holding (open)",B(CAP.holding)],["Cash / dry",B(CAP.dry)],
    ["Unrealized",`<span class="${(CAP.unreal||0)>=0?'pos':'neg'}">${B(CAP.unreal)}</span>`],
    ["Realized",`<span class="${(CAP.realized||0)>=0?'pos':'neg'}">${B(CAP.realized)}</span>`],
    ["Open / Exited",`${CAP.n_open} / ${CAP.n_closed}`]];
  s.innerHTML=cells.map(([k,v])=>`<div class="scard"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
 })();
 (function(){const fb=document.getElementById("fresh");if(!fb)return;
  const d=new Date(ASOF+"T00:00:00Z"),now=new Date();
  // TRADING-day aware: weekends + holidays produce NO new closes, so count WEEKDAYS elapsed, not calendar
  // days (Thu close -> Mon after a Fri holiday = 4 cal days but 0-1 trading days = NOT stale, the 06-22 bug).
  let wd=0; if(!isNaN(d)){let t=new Date(d);t.setUTCDate(t.getUTCDate()+1);while(t<now){const g=t.getUTCDay();if(g!==0&&g!==6)wd++;t.setUTCDate(t.getUTCDate()+1);}}
  const stale=wd>2;   // >2 trading days with no new close = genuinely stale (tolerates a single holiday)
  fb.className="freshbar "+(stale?"stale":"ok");
  fb.innerHTML=(stale?"⚠️ STALE — no new close in "+wd+" trading days":"✓ Fresh — last close "+ASOF)+
    ' <span class="sub">· data as-of '+ASOF+' · page built '+BUILT+(stale?' · auto-rebuild may have failed — prices below are NOT current, do not trade off them':'')+'</span>';
 })();
 const f=(v,s="")=>{const c=v>0?"pos":(v<0?"neg":"");return `<span class="${c}">${v}${s}</span>`};
 function draw(h){
  document.getElementById("nm").textContent=h.ticker+" — "+h.name;
  document.getElementById("note").textContent=h.note;
  document.getElementById("ke").textContent="$"+h.entry;
  document.getElementById("kz").textContent=h.size_baht?("฿"+h.size_baht.toLocaleString()):"—";
  document.getElementById("kcl").textContent=h.closed?"Exit":"Current";
  document.getElementById("kc").textContent="$"+(h.closed?(h.exit!=null?h.exit:h.current):h.current);
  document.getElementById("kpl").textContent=h.closed?"Realized P&L":"P&L";
  document.getElementById("kp").innerHTML=f(h.pnl,"%");
  document.getElementById("ks").innerHTML='<span class="tag '+(h.closed?'closed':'')+'">'+h.status+'</span>';
  document.getElementById("kf").textContent=h.flavor;
  const cv=document.getElementById("cv"),x=cv.getContext("2d"),P=52;
  // HiDPI: scale backing store by devicePixelRatio so text/lines render SHARP (was blurry — canvas upscaled by the browser)
  const dpr=window.devicePixelRatio||1,_r=cv.getBoundingClientRect(),W=Math.round(_r.width)||cv.width,H=Math.round(_r.height)||cv.height;
  cv.width=W*dpr;cv.height=H*dpr;cv.style.width=W+"px";cv.style.height=H+"px";x.setTransform(dpr,0,0,dpr,0,0);
  x.clearRect(0,0,W,H); const s=h.series,n=s.length; if(!n)return;
  const pts=s.map(p=>p[1]),rmn=Math.min(...pts,h.entry),rmx=Math.max(...pts,h.entry);
  // LOG y-scale: names that spike then crash (LEU 8x'd to $436) squish the actionable near-entry range into the bottom ~15% on a linear axis. Log spreads it out (3% pad).
  const lmn=Math.log(rmn*0.97),lmx=Math.log(rmx*1.03),lrng=(lmx-lmn)||1;
  const X=i=>P+i/(n-1)*(W-2*P),Y=v=>H-P-(Math.log(v)-lmn)/lrng*(H-2*P);
  x.strokeStyle="#1c2532";x.fillStyle="#8a97aa";x.font="13px 'JetBrains Mono',monospace";
  // snap gridline labels to CLEAN round numbers (was ugly log values like $90.2/$154/$263/$449)
  const niceN=v=>{const s=v<5?0.5:v<20?1:v<50?5:v<200?10:v<500?25:v<2000?100:v<10000?500:1000;return Math.round(v/s)*s;};
  const seenY=new Set();
  for(let g=0;g<=4;g++){const v=niceN(Math.exp(lmn+lrng*g/4));if(v<=0||seenY.has(v))continue;seenY.add(v);const yy=Y(v);x.beginPath();x.moveTo(P,yy);x.lineTo(W-P,yy);x.stroke();x.fillText("$"+(v>=1000?(v/1000).toFixed(v%1000?1:0)+"k":v),6,yy+4);}
  x.fillText(s[0][0],P,H-16);x.textAlign="right";x.fillText(s[n-1][0],W-P,H-16);x.textAlign="left";
  x.strokeStyle="#e8a14b";x.setLineDash([5,4]);x.beginPath();x.moveTo(P,Y(h.entry));x.lineTo(W-P,Y(h.entry));x.stroke();x.setLineDash([]);
  x.fillStyle="#e8a14b";x.fillText("entry $"+h.entry,P+6,Y(h.entry)-6);
  const col=h.pnl>=0?"#27d38a":"#ff5a6a";x.strokeStyle=col;x.lineWidth=2.2;x.beginPath();
  pts.forEach((v,i)=>{i?x.lineTo(X(i),Y(v)):x.moveTo(X(i),Y(v))});x.stroke();
  x.lineTo(X(n-1),H-P);x.lineTo(X(0),H-P);x.closePath();  // close to baseline -> subtle area fill for readability
  const gr=x.createLinearGradient(0,0,0,H);gr.addColorStop(0,h.pnl>=0?"rgba(39,211,138,0.16)":"rgba(255,90,106,0.16)");gr.addColorStop(1,"rgba(0,0,0,0)");x.fillStyle=gr;x.fill();
  let ei=s.findIndex(p=>p[0]>=h.entry_date); if(ei<0)ei=n-1;
  x.fillStyle="#e8a14b";x.beginPath();x.arc(X(ei),Y(h.entry),6,0,7);x.fill();
  const tb=document.querySelector("#log tbody");
  let rows=`<tr><td class="mono">${h.entry_date}</td><td class="mono">BUY</td><td class="mono">$${h.entry}</td><td>${h.size_baht?'฿'+h.size_baht.toLocaleString()+' · ':''}${h.flavor}</td></tr>`;
  if(h.closed) rows+=`<tr><td class="mono">${s[n-1][0]}</td><td class="mono">SELL</td><td class="mono">$${h.exit!=null?h.exit:h.current}</td><td>${f(h.pnl,"% realized — position closed")}</td></tr>`;
  else rows+=`<tr><td class="mono">${s[n-1][0]}</td><td class="mono">mark (now)</td><td class="mono">$${h.current}</td><td>${f(h.pnl,"% unrealized — not sold")}</td></tr>`;
  tb.innerHTML=rows;
 }
 function tabs(){const t=document.getElementById("postabs");
  const nO=DATA.filter(o=>!o.closed).length,nC=DATA.filter(o=>o.closed).length;
  t.innerHTML=[["current","Current · "+nO],["exited","Exited · "+nC]].map(([k,l])=>
    `<button class="ptab${posTab===k?' active':''}" data-k="${k}">${l}</button>`).join("");
  t.querySelectorAll(".ptab").forEach(b=>b.onclick=()=>{posTab=b.dataset.k;
    const fr=DATA.filter(o=>posTab==="exited"?o.closed:!o.closed); if(fr.length)sel=fr[0]; render();});
 }
 function list(){const L=document.getElementById("list");
  const rows=DATA.filter(o=>posTab==="exited"?o.closed:!o.closed);
  L.innerHTML = rows.length ? "" : '<div class="note" style="padding:10px 4px">No '+posTab+' positions.</div>';
  rows.forEach(h=>{const d=document.createElement("div");d.className="item"+(sel===h?" sel":"");
   d.innerHTML=`<div class="t">${h.ticker} ${h.pnl>=0?'<span class="pos">+'+h.pnl+'%</span>':'<span class="neg">'+h.pnl+'%</span>'}</div><div class="p">${h.name.replace(/\|/g,' ').slice(0,30)} · ${h.status} · ${h.book}</div>`;
   d.onclick=()=>{sel=h;render()};L.appendChild(d);});}
 function render(){tabs();list();if(sel)draw(sel);}
 render();
</script>
<script type="module" src="./anim.js"></script>
</body></html>"""
    page = html.replace("__DATA__", DATA).replace("__CAP__", CAP).replace("__ASOF__", asof).replace("__BUILT__", build_utc)
    Path("web/stocks.html").write_text(page, encoding="utf-8")
    _write_health("stocks", {"built_utc": build_utc, "data_asof": asof,
                             "n_positions": len(out),
                             "tickers": [p["ticker"] for p in out],
                             "ok": asof != "no-data"})
    print(f"wrote web/stocks.html ({len(out)} positions: {', '.join(p['ticker'] for p in out)}; data as-of {asof})")


if __name__ == "__main__":
    main()
