"""
gen_stocks.py — build web/stocks.html: a BIG per-stock paper-trade dashboard
(price history chart + entry/exit markers + P&L + trade log). Mirrors the
spike-hunter tracker in the second brain (memory/paper-trades.md).

Data embedded inline so it works on GitHub Pages with no fetch/CORS.
Re-run to refresh: python web/gen_stocks.py

    python web/gen_stocks.py   ->  web/stocks.html
"""
import json
import yfinance as yf

# Open + closed paper positions (mirror of brain memory/paper-trades.md).
HOLDINGS = [
    dict(ticker="LEU", name="Centrus Energy", entry_date="2026-06-08", entry=166.30,
         flavor="franchise / re-rating", target=None, stop=None, status="OPEN",
         exit_date=None, exit=None,
         note="Only US-owned HALEU enricher (Russia ban + DOE >$3.4B + post-2030 SMR). "
              "Entered mid −16%/wk selloff; our deepdive = cautious-bearish on valuation. Paper-tracking which call wins."),
]


def hist(tkr, days=400):
    h = yf.Ticker(tkr).history(period=f"{days}d")["Close"]
    return [[str(i.date()), round(float(v), 2)] for i, v in h.items()]


def main():
    out = []
    for h in HOLDINGS:
        series = hist(h["ticker"])
        cur = series[-1][1] if series else h["entry"]
        ref = h["exit"] if h["exit"] else cur
        pnl = round((ref - h["entry"]) / h["entry"] * 100, 1)
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
<div class="sub">Live paper track of the stock-analysis (spike-hunter) framework. Real price history · entry/exit markers · P&L. Updated by the daily routine + on demand.</div>
<div class="nav"><a href="./index.html">← back to QuantBot (crypto)</a></div>
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
  // chart
  const cv=document.getElementById("cv"),x=cv.getContext("2d"),W=cv.width,H=cv.height,P=52;
  x.clearRect(0,0,W,H); const s=h.series,n=s.length; if(!n)return;
  const pts=s.map(p=>p[1]),mn=Math.min(...pts,h.entry),mx=Math.max(...pts,h.entry),rng=(mx-mn)||1;
  const X=i=>P+i/(n-1)*(W-2*P),Y=v=>H-P-(v-mn)/rng*(H-2*P);
  x.strokeStyle="#1c2230";x.fillStyle="#6b7585";x.font="12px system-ui";
  for(let g=0;g<=4;g++){const v=mn+rng*g/4,yy=Y(v);x.beginPath();x.moveTo(P,yy);x.lineTo(W-P,yy);x.stroke();x.fillText("$"+Math.round(v),6,yy+4);}
  x.fillText(s[0][0],P,H-16);x.textAlign="right";x.fillText(s[n-1][0],W-P,H-16);x.textAlign="left";
  // entry line
  x.strokeStyle="#fbbf24";x.setLineDash([5,4]);x.beginPath();x.moveTo(P,Y(h.entry));x.lineTo(W-P,Y(h.entry));x.stroke();x.setLineDash([]);
  x.fillStyle="#fbbf24";x.fillText("entry $"+h.entry,P+6,Y(h.entry)-6);
  // price line
  x.strokeStyle=h.pnl>=0?"#4ade80":"#f87171";x.lineWidth=2;x.beginPath();
  pts.forEach((v,i)=>{i?x.lineTo(X(i),Y(v)):x.moveTo(X(i),Y(v))});x.stroke();
  // entry marker (nearest date)
  let ei=s.findIndex(p=>p[0]>=h.entry_date); if(ei<0)ei=n-1;
  x.fillStyle="#fbbf24";x.beginPath();x.arc(X(ei),Y(h.entry),6,0,7);x.fill();
  if(h.exit){let xi=s.findIndex(p=>p[0]>=h.exit_date);if(xi<0)xi=n-1;x.fillStyle="#c084fc";x.beginPath();x.arc(X(xi),Y(h.exit),6,0,7);x.fill();}
  // log
  const tb=document.querySelector("#log tbody");
  let rows=`<tr><td>${h.entry_date}</td><td>BUY</td><td>$${h.entry}</td><td>${h.flavor}</td></tr>`;
  if(h.exit)rows+=`<tr><td>${h.exit_date}</td><td>SELL</td><td>$${h.exit}</td><td>closed</td></tr>`;
  rows+=`<tr><td>${s[n-1][0]}</td><td>mark</td><td>$${h.current}</td><td>${f(h.pnl,"% unrealized")}</td></tr>`;
  tb.innerHTML=rows;
 }
 function list(){const L=document.getElementById("list");L.innerHTML="";
  DATA.forEach(h=>{const d=document.createElement("div");d.className="item"+(sel===h?" sel":"");
   d.innerHTML=`<div class="t">${h.ticker} ${h.pnl>=0?'<span class="pos">+'+h.pnl+'%</span>':'<span class="neg">'+h.pnl+'%</span>'}</div><div class="p">${h.name} · ${h.status}</div>`;
   d.onclick=()=>{sel=h;list();draw(h)};L.appendChild(d);});}
 list();draw(sel);
</script></body></html>"""
    open("web/stocks.html", "w", encoding="utf-8").write(html.replace("__DATA__", DATA))
    print(f"wrote web/stocks.html ({len(out)} holdings)")


if __name__ == "__main__":
    main()
