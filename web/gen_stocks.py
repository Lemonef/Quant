"""
gen_stocks.py — build web/stocks.html from the LIVE ledger (brain memory/paper-trades.md).

Parses ALL open positions (PAPER OWN + REAL OWN) straight from paper-trades.md so the page
NEVER goes stale or shows only one name — re-run it and it reflects the current book exactly.
Prices via yfinance (accurate close, not the routine's intraday bad-ticks).

    python web/gen_stocks.py   ->  web/stocks.html

Brain path resolution order: $SECOND_BRAIN env -> D:/second-brain -> ../second-brain -> ./second-brain
(so it works locally AND in a CI job that clones the brain alongside this repo).
"""
import json, os, re
from pathlib import Path
import yfinance as yf


def find_brain():
    cands = [os.environ.get("SECOND_BRAIN"), r"D:/second-brain", "../second-brain", "./second-brain"]
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
            rows.append(dict(
                ticker=re.sub(r"[^A-Z]", "", tk.upper())[:6],
                name=tk,
                entry_date=cells[1][:10],
                entry=entry,
                flavor=cells[3][:60],
                status="OPEN" if "OPEN" in cells[9].upper() else cells[9][:18],
                target=None, stop=None, exit=None, exit_date=None,
                book=section,
                note=re.sub(r"\s+", " ", cells[4])[:240],
            ))
    return rows


def hist(tkr, days=400):
    try:
        h = yf.Ticker(tkr).history(period=f"{days}d")["Close"]
        return [[str(i.date()), round(float(v), 2)] for i, v in h.items()]
    except Exception:
        return []


def main():
    brain = find_brain()
    if not brain:
        raise SystemExit("paper-trades.md not found — set $SECOND_BRAIN or place brain at D:/second-brain")
    positions = parse_positions(brain)
    out = []
    for h in positions:
        series = hist(h["ticker"])
        cur = series[-1][1] if series else h["entry"]
        ref = h["exit"] if h["exit"] else cur
        pnl = round((ref - h["entry"]) / h["entry"] * 100, 1) if h["entry"] else 0.0
        out.append({**h, "current": cur, "pnl": pnl, "series": series})
    DATA = json.dumps(out)

    html = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Spike Hunter — Stock Paper Trades</title>
<style>
 body{background:#0b0e14;color:#e6e6e6;font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:24px}
 a{color:#60a5fa} h1{font-size:22px;margin:0 0 2px}
 .sub{color:#8b95a5;margin-bottom:16px} .nav{margin-bottom:18px}
 .wrap{display:flex;gap:20px;flex-wrap:wrap}
 .list{flex:0 0 260px;min-width:240px}
 .item{background:#0f141e;border:1px solid #1c2230;border-radius:10px;padding:12px 14px;margin-bottom:10px;cursor:pointer}
 .item:hover{background:#15233a} .item.sel{border-color:#4ade80}
 .item .t{font-weight:700} .item .p{font-size:12px;color:#8b95a5}
 .main{flex:1;min-width:480px}
 .card{background:#0f141e;border:1px solid #1c2230;border-radius:12px;padding:18px}
 .card h2{margin:0 0 2px;font-size:20px} .cnote{color:#8b95a5;font-size:12.5px;margin-bottom:14px;max-width:760px}
 .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:14px}
 .kpi{background:#121826;border-radius:9px;padding:10px 12px}
 .kpi .k{color:#8b95a5;font-size:11px} .kpi .v{font-size:18px;font-weight:700;margin-top:2px}
 canvas{width:100%;height:340px;background:#0b0e14;border-radius:8px}
 table{border-collapse:collapse;width:100%;margin-top:14px}
 th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #1c2230;font-size:13px}
 th{color:#8b95a5} .pos{color:#4ade80} .neg{color:#f87171}
 .tag{font-size:11px;padding:2px 8px;border-radius:10px;background:#16361f;color:#4ade80}
 .closed{background:#2a2030;color:#c084fc}
</style></head><body>
<h1>Spike Hunter — Stock Paper Trades</h1>
<div class="sub">Live paper track of the stock-analysis (spike-hunter) framework, built straight from the brain ledger (paper-trades.md). Real price history · entry markers · P&L. Re-run gen_stocks.py to refresh.</div>
<div class="nav"><a href="./index.html">← QuantBot (crypto)</a> · <a href="./strategy_lab.html">🧪 Strategy Lab</a></div>
<div class="wrap">
 <div class="list" id="list"></div>
 <div class="main"><div class="card">
  <h2 id="nm">—</h2><div class="cnote" id="note"></div>
  <div class="kpis">
   <div class="kpi"><div class="k">Entry</div><div class="v" id="ke">—</div></div>
   <div class="kpi"><div class="k">Current</div><div class="v" id="kc">—</div></div>
   <div class="kpi"><div class="k">P&L</div><div class="v" id="kp">—</div></div>
   <div class="kpi"><div class="k">Status</div><div class="v" id="ks">—</div></div>
   <div class="kpi"><div class="k">Flavor</div><div class="v" id="kf" style="font-size:13px">—</div></div>
  </div>
  <canvas id="cv" width="900" height="680"></canvas>
  <table id="log"><thead><tr><th>Date</th><th>Action</th><th>Price</th><th>Note</th></tr></thead><tbody></tbody></table>
 </div></div>
</div>
<script>
 const DATA=__DATA__; let sel=DATA[0];
 const f=(v,s="")=>{const c=v>0?"pos":(v<0?"neg":"");return `<span class="${c}">${v}${s}</span>`};
 function draw(h){
  document.getElementById("nm").textContent=h.ticker+" — "+h.name;
  document.getElementById("note").textContent=h.note;
  document.getElementById("ke").textContent="$"+h.entry+" ("+h.entry_date+")";
  document.getElementById("kc").textContent="$"+h.current;
  document.getElementById("kp").innerHTML=f(h.pnl,"%");
  document.getElementById("ks").innerHTML='<span class="tag '+(h.status=="OPEN"?'':'closed')+'">'+h.status+'</span>';
  document.getElementById("kf").textContent=h.flavor;
  const cv=document.getElementById("cv"),x=cv.getContext("2d"),W=cv.width,H=cv.height,P=52;
  x.clearRect(0,0,W,H); const s=h.series,n=s.length; if(!n)return;
  const pts=s.map(p=>p[1]),mn=Math.min(...pts,h.entry),mx=Math.max(...pts,h.entry),rng=(mx-mn)||1;
  const X=i=>P+i/(n-1)*(W-2*P),Y=v=>H-P-(v-mn)/rng*(H-2*P);
  x.strokeStyle="#1c2230";x.fillStyle="#6b7585";x.font="12px system-ui";
  for(let g=0;g<=4;g++){const v=mn+rng*g/4,yy=Y(v);x.beginPath();x.moveTo(P,yy);x.lineTo(W-P,yy);x.stroke();x.fillText("$"+Math.round(v),6,yy+4);}
  x.fillText(s[0][0],P,H-16);x.textAlign="right";x.fillText(s[n-1][0],W-P,H-16);x.textAlign="left";
  x.strokeStyle="#fbbf24";x.setLineDash([5,4]);x.beginPath();x.moveTo(P,Y(h.entry));x.lineTo(W-P,Y(h.entry));x.stroke();x.setLineDash([]);
  x.fillStyle="#fbbf24";x.fillText("entry $"+h.entry,P+6,Y(h.entry)-6);
  x.strokeStyle=h.pnl>=0?"#4ade80":"#f87171";x.lineWidth=2;x.beginPath();
  pts.forEach((v,i)=>{i?x.lineTo(X(i),Y(v)):x.moveTo(X(i),Y(v))});x.stroke();
  let ei=s.findIndex(p=>p[0]>=h.entry_date); if(ei<0)ei=n-1;
  x.fillStyle="#fbbf24";x.beginPath();x.arc(X(ei),Y(h.entry),6,0,7);x.fill();
  const tb=document.querySelector("#log tbody");
  let rows=`<tr><td>${h.entry_date}</td><td>BUY</td><td>$${h.entry}</td><td>${h.flavor}</td></tr>`;
  rows+=`<tr><td>${s[n-1][0]}</td><td>mark</td><td>$${h.current}</td><td>${f(h.pnl,"% unrealized")}</td></tr>`;
  tb.innerHTML=rows;
 }
 function list(){const L=document.getElementById("list");L.innerHTML="";
  DATA.forEach(h=>{const d=document.createElement("div");d.className="item"+(sel===h?" sel":"");
   d.innerHTML=`<div class="t">${h.ticker} ${h.pnl>=0?'<span class="pos">+'+h.pnl+'%</span>':'<span class="neg">'+h.pnl+'%</span>'}</div><div class="p">${h.name.replace(/\|/g,' ').slice(0,40)} · ${h.status} · ${h.book}</div>`;
   d.onclick=()=>{sel=h;list();draw(h)};L.appendChild(d);});}
 list();draw(sel);
</script></body></html>"""
    Path("web/stocks.html").write_text(html.replace("__DATA__", DATA), encoding="utf-8")
    print(f"wrote web/stocks.html ({len(out)} positions: {', '.join(p['ticker'] for p in out)})")


if __name__ == "__main__":
    main()
