"""
build_board.py — Backtest Board page for the Trade site (Quant/web).
Full-sample GROSS backtest scoreboard with leverage toggle. Self-contained data
(embedded from board_data.json so it works as a static GitHub Pages file).

    python web/build_board.py   ->  web/board.html

Sanitize step makes the table match the chart (recompute CAGR/MaxDD from each
equity curve) and caps any leverage level that liquidates (equity <= 0).
"""
import json, datetime as dt

d = json.load(open("web/board_data.json", encoding="utf-8"))


def sanitize(strats):
    for s in strats:
        for _lev, k in s.get("levels", {}).items():
            ser = k.get("series") or []
            if len(ser) < 3:
                continue
            eq = [p[1] for p in ser]
            if any(v <= 0 for v in eq):                      # liquidation / ruin
                ci = next(i for i, v in enumerate(eq) if v <= 0)
                ser = ser[:ci + 1]; ser[ci][1] = 0.0
                k["series"] = ser
                k["ruin"] = True; k["cagr"] = None; k["maxdd"] = -100.0
                continue
            d0 = dt.date.fromisoformat(ser[0][0]); d1 = dt.date.fromisoformat(ser[-1][0])
            days = (d1 - d0).days or 1
            k["cagr"] = round(((eq[-1] / eq[0]) ** (365 / days) - 1) * 100, 1)
            peak = eq[0]; mdd = 0.0
            for v in eq:
                peak = max(peak, v); mdd = min(mdd, (v - peak) / peak)
            k["maxdd"] = round(mdd * 100, 1)
    return strats


DATA = json.dumps(sanitize(d["strategies"]))

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Backtest Board — full-sample gross ceiling</title>
<link rel="stylesheet" href="./style.css">
<style>
 .lev{display:flex;gap:8px;margin:0 0 18px;flex-wrap:wrap}
 .lev button{font-family:var(--mono);font-size:12.5px;font-weight:600;background:var(--ink2);border:1px solid var(--line);color:var(--mut);border-radius:9px;padding:7px 16px;cursor:pointer;transition:.15s}
 .lev button:hover{color:var(--txt);border-color:var(--line2)}
 .lev button.on{background:linear-gradient(180deg,#1b2942,#16223a);color:#fff;border-color:var(--accent)}
 .cols{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}
 .left{flex:1;min-width:430px} .right{flex:1;min-width:430px}
 #t{width:100%;border-collapse:collapse;font-size:13px} #t th,#t td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line)}
 #t th{font-family:var(--mono);color:var(--mut);font-size:11px;letter-spacing:.06em;text-transform:uppercase;cursor:pointer} #t td.l,#t th.l{text-align:left}
 #t td{font-family:var(--mono)}
 tr.row{cursor:pointer} tr.row:hover td{background:rgba(124,196,255,.03)} tr.sel td{background:rgba(124,196,255,.06)}
 .pos{color:var(--up)} .neg{color:var(--dn)}
 .tag{font-family:var(--mono);font-size:10px;font-weight:700;padding:2px 8px;border-radius:6px}
 .deploy{background:rgba(39,211,138,.13);color:var(--up);border:1px solid rgba(39,211,138,.3)}
 .diversifier{background:rgba(124,196,255,.12);color:var(--accent);border:1px solid rgba(124,196,255,.3)}
 .benchmark{background:rgba(183,156,255,.12);color:var(--accent2);border:1px solid rgba(183,156,255,.3)}
 .research{background:rgba(244,184,96,.12);color:var(--warn);border:1px dashed rgba(244,184,96,.5)}
 #cv{width:100%;height:300px;background:var(--ink2);border:1px solid var(--line);border-radius:10px}
 .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px}
 .kpi{background:var(--ink2);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
 .kpi .k{font-family:var(--mono);color:var(--mut);font-size:10px;letter-spacing:.1em;text-transform:uppercase} .kpi .v{font-family:var(--mono);font-size:19px;font-weight:700;margin-top:2px}
 .bnote{font-family:var(--mono);font-size:12px;color:var(--warn);margin-top:10px}
 .banner{border-radius:10px;padding:10px 14px;margin:0 0 10px;max-width:900px;font-size:12.5px;line-height:1.5}
 .banner.gross{border-left:3px solid var(--warn);background:rgba(244,184,96,.06);color:#e8c98a}
 .banner.live{border-left:3px solid var(--up);background:rgba(39,211,138,.06);color:#9fe3bd}
 .banner.research{border-left:3px dashed var(--warn);background:rgba(244,184,96,.05);color:var(--warn)}
 @media(max-width:560px){.left,.right{min-width:0} .kpis{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="wrap">
 <p class="eyebrow">Backtests · Gross Ceiling</p>
 <h1>Backtest <span class="thin">Board</span></h1>
 <p class="lede">Measured ~8y (2018–26, yfinance), leverage-toggle. <b>These are FULL-SAMPLE GROSS results — the optimistic ceiling, not live, not net-of-funding.</b> CAGR &amp; MaxDD are recomputed straight from each equity curve (table matches chart); Sharpe at native frequency.</p>
 <div class="nav">
  <a href="./index.html">◆ Strategy Book</a>
  <a href="./stocks.html">📈 Stocks — Spike Hunter</a>
  <a href="./strategy_lab.html">🧪 Strategy Lab — the gauntlet</a>
  <a class="home" href="./board.html">📊 Backtest Board</a>
 </div>
 <div class="banner live">✅ <b>Honest / audited numbers</b> (OOS Sharpe, net of fees, real DD) are on the <b>Strategy Lab</b> + live <b>Strategy Book</b> — e.g. the crypto blend is <b>1.28 OOS</b> there, not the gross figure here.</div>
 <div class="banner gross">⚠ <b>Plan real DD ≈ 2× shown</b>; out-of-sample &amp; funding-adjusted returns are LOWER. Leverage rows include ~10% APR financing on borrowed notional.</div>
 <div class="banner research">⚠ Amber <b>research</b> rows = R3 backtests pending live validation, 1× only. <b>3× rows that blow past zero show ⛔ LIQUIDATED</b> (financing + drawdown wiped the account — not survivable).</div>

 <div class="lev" id="lev"><button data-l="1x" class="on">1×</button><button data-l="2x">2×</button><button data-l="3x">3×</button><button data-l="all">ALL ⊞</button></div>
 <div class="cols">
  <div class="left"><table id="t"><thead id="th"></thead><tbody></tbody></table></div>
  <div class="right"><div class="card">
   <h2 id="nm" style="margin:0 0 4px">—</h2><div class="note" id="bnote2" style="margin-bottom:12px"></div>
   <div class="kpis">
    <div class="kpi"><div class="k">CAGR</div><div class="v" id="kc">—</div></div>
    <div class="kpi"><div class="k">Sharpe</div><div class="v" id="ks">—</div></div>
    <div class="kpi"><div class="k">Max DD</div><div class="v" id="kd">—</div></div>
    <div class="kpi"><div class="k">Win%</div><div class="v" id="kw">—</div></div>
   </div>
   <canvas id="cv" width="860" height="560"></canvas>
   <div class="bnote" id="warn"></div>
  </div></div>
 </div>
 <footer>Full-sample gross backtest (2018–26) · the optimistic ceiling · honest/live numbers on Strategy Lab + Strategy Book · not financial advice · Lemonef/Trade</footer>
</div>
<script>
 const DATA=__DATA__; let L="1x", key="cagr", dir=-1, sel=DATA[0];
 const f=(v,s="")=>{if(v===null||v===undefined||Number.isNaN(v))return `<span style="color:var(--dim)">—</span>`;const c=v>0?"pos":(v<0?"neg":"");return `<span class="${c}">${v}${s}</span>`};
 function lvl(s){return s.levels[L]}
 function draw(s,lv){
  const isR=s.category==="research";
  const L2=isR?"1x":(lv||(L==="all"?"1x":L)); const k=s.levels[L2];
  document.getElementById("nm").textContent=s.name+"  @"+L2+(isR?"  (1× only — backtest)":"");
  document.getElementById("bnote2").textContent=(k.ruin?"⛔ LIQUIDATED at "+L2+" — equity hit zero (financing + drawdown). Not survivable. ":"")+(s.note||"");
  document.getElementById("kc").innerHTML=f(k.cagr,"%");
  document.getElementById("ks").innerHTML=f(k.sharpe);
  document.getElementById("kd").innerHTML=f(k.maxdd,"%");
  document.getElementById("kw").textContent=(k.win||0)+"%";
  const cv=document.getElementById("cv"),x=cv.getContext("2d"),W=cv.width,H=cv.height,P=58; x.clearRect(0,0,W,H);
  const pts=(k.series||[]).map(p=>p[1]),n=pts.length; if(!n)return;
  const mn=Math.min(...pts),mx=Math.max(...pts),rng=(mx-mn)||1;
  const X=i=>P+i/(n-1)*(W-2*P),Y=v=>H-P-(v-mn)/rng*(H-2*P);
  x.strokeStyle="#222c3d";x.fillStyle="#8a97aa";x.font="13px 'JetBrains Mono',monospace";
  for(let g=0;g<=4;g++){const v=mn+rng*g/4,yy=Y(v);x.beginPath();x.moveTo(P,yy);x.lineTo(W-P,yy);x.stroke();x.fillText("$"+Math.round(v).toLocaleString(),6,yy+4);}
  if(mn<=10000&&mx>=10000){x.strokeStyle="#2c3a50";x.setLineDash([4,4]);x.beginPath();x.moveTo(P,Y(10000));x.lineTo(W-P,Y(10000));x.stroke();x.setLineDash([]);}
  x.strokeStyle=(k.cagr==null)?"#ff5a6a":(k.cagr>=0?"#27d38a":"#ff5a6a");x.lineWidth=2;x.beginPath();
  pts.forEach((v,i)=>{i?x.lineTo(X(i),Y(v)):x.moveTo(X(i),Y(v))});x.stroke();
 }
 function render(){
  const th=document.getElementById("th"),tb=document.querySelector("#t tbody");
  th.innerHTML=`<tr><th class="l" data-k="name">Strategy</th><th data-k="cagr">CAGR%</th><th data-k="sharpe">Sharpe</th><th data-k="maxdd">MaxDD%</th><th data-k="win">Win%</th><th class="l" data-k="category">Type</th></tr>`;
  let rows=[];
  if(L==="all"){ DATA.forEach(s=>(s.category==="research"?["1x"]:["1x","2x","3x"]).forEach(lv=>{const k=s.levels[lv];rows.push({label:s.name+" ("+lv+")",cagr:k.cagr,sharpe:k.sharpe,maxdd:k.maxdd,win:k.win||0,category:s.category,s:s,lv:lv});}));}
  else { rows=DATA.map(s=>{
    if(s.category==="research" && L!=="1x") return {label:s.name,cagr:null,sharpe:null,maxdd:null,win:null,category:s.category,s:s,lv:"1x"};
    const k=lvl(s);return {label:s.name,cagr:k.cagr,sharpe:k.sharpe,maxdd:k.maxdd,win:k.win||0,category:s.category,s:s,lv:L};});}
  rows.sort((a,b)=>{let av=key==="name"?a.label:(key==="category"?a.category:a[key]),bv=key==="name"?b.label:(key==="category"?b.category:b[key]);
    if(typeof av==="string")return av.localeCompare(bv)*dir;
    av=(av==null||Number.isNaN(av))?-Infinity:av; bv=(bv==null||Number.isNaN(bv))?-Infinity:bv; return (av-bv)*dir;});
  tb.innerHTML="";
  rows.forEach(r=>{const tr=document.createElement("tr");tr.className="row"+(sel===r.s?" sel":"");
   tr.innerHTML=`<td class="l">${r.label}</td><td>${f(r.cagr)}</td><td>${f(r.sharpe)}</td><td>${f(r.maxdd)}</td><td>${r.win==null?'<span style="color:var(--dim)">—</span>':r.win}</td><td class="l"><span class="tag ${r.category}">${r.category}</span></td>`;
   tr.onclick=()=>{sel=r.s; draw(r.s, r.lv); render();};tb.appendChild(tr);});
  document.querySelectorAll("#t th").forEach(t=>{if(t.dataset.k)t.onclick=()=>{const kk=t.dataset.k;dir=(kk===key)?-dir:-1;key=kk;render();};});
  document.getElementById("warn").textContent = (L==="all") ? "ALL view: one row per strategy × leverage — click a header to sort. 2×/3× include ~10% financing; Sharpe ~flat across leverage, DD scales, >2× risks liquidation."
    : (L!=="1x" ? "⚠ "+L+" includes ~10% financing. Plan ~2× this maxDD live; >2× risks liquidation." : "");
 }
 document.querySelectorAll("#lev button").forEach(b=>b.onclick=()=>{L=b.dataset.l;document.querySelectorAll("#lev button").forEach(x=>x.classList.remove("on"));b.classList.add("on");render();draw(sel);});
 render();draw(sel);
</script>
<script type="module" src="./anim.js"></script>
</body></html>"""
open("web/board.html", "w", encoding="utf-8").write(HTML.replace("__DATA__", DATA))
print("wrote web/board.html")
