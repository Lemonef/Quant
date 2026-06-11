"""
build_board.py — Backtest Board page for the Trade site (Quant/web).
Leverage toggle (1x/2x/3x) + PERIOD toggle:
  • Full   = whole 2018-26 sample (gross ceiling, bull-inflated)
  • Recent = 2022-01-01 -> now (post-2021-bull; the honest-er forward gauge)
All metrics (CAGR / MaxDD / Sharpe) are recomputed straight from each equity
curve for the chosen window, so the table always matches the chart. Leverage
levels that liquidate (equity <= 0) are capped + flagged.

    python web/build_board.py   ->  web/board.html
"""
import json, datetime as dt

RECENT_FROM = "2022-01-01"   # strip the 2018-21 mega-bull
d = json.load(open("web/board_data.json", encoding="utf-8"))


def metrics(series, win):
    if not series or len(series) < 3:
        return {"cagr": None, "sharpe": None, "maxdd": None, "win": win, "series": series or []}
    series = [list(p) for p in series]
    eq = [p[1] for p in series]
    if any(v <= 0 for v in eq):                                   # liquidation
        ci = next(i for i, v in enumerate(eq) if v <= 0)
        series = series[:ci + 1]; series[ci][1] = 0.0
        return {"cagr": None, "sharpe": None, "sortino": None, "calmar": None, "maxdd": -100.0, "win": win, "series": series, "ruin": True}
    d0 = dt.date.fromisoformat(series[0][0]); d1 = dt.date.fromisoformat(series[-1][0])
    days = (d1 - d0).days or 1
    cagr = round(((eq[-1] / eq[0]) ** (365 / days) - 1) * 100, 1)
    peak = eq[0]; mdd = 0.0
    for v in eq:
        peak = max(peak, v); mdd = min(mdd, (v - peak) / peak)
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq))]
    mean = sum(rets) / len(rets)
    sd = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5
    ppy = 365 / (days / len(rets))
    sharpe = round(mean / sd * (ppy ** 0.5), 2) if sd > 0 else 0.0
    downs = [min(0.0, r) for r in rets]
    dsd = (sum(x * x for x in downs) / len(rets)) ** 0.5
    sortino = round(mean / dsd * (ppy ** 0.5), 2) if dsd > 0 else None
    mddpct = round(mdd * 100, 1)
    calmar = round(cagr / abs(mddpct), 2) if mddpct else None
    return {"cagr": cagr, "sharpe": sharpe, "sortino": sortino, "calmar": calmar, "maxdd": mddpct, "win": win, "series": series}


def split(strats):
    for s in strats:
        for lev, k in list(s.get("levels", {}).items()):
            full = k.get("series") or []
            rec_raw = [p for p in full if p[0] >= RECENT_FROM]
            if len(rec_raw) >= 2:                                  # rebase recent curve to $10k start
                f = 10000.0 / rec_raw[0][1]
                rec = [[p[0], round(p[1] * f, 2)] for p in rec_raw]
            else:
                rec = []
            s["levels"][lev] = {"full": metrics(full, k.get("win")),
                                "recent": metrics(rec, k.get("win"))}
    return strats


DATA = json.dumps(split(d["strategies"]))

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Backtest Board — full vs recent (honest)</title>
<link rel="stylesheet" href="./style.css">
<style>
 .toggles{display:flex;gap:18px;flex-wrap:wrap;margin:0 0 16px;align-items:center}
 .seg{display:flex;gap:6px;flex-wrap:wrap} .seg .lbl{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);align-self:center;margin-right:2px}
 .seg button{font-family:var(--mono);font-size:12.5px;font-weight:600;background:var(--ink2);border:1px solid var(--line);color:var(--mut);border-radius:9px;padding:7px 14px;cursor:pointer;transition:.15s}
 .seg button:hover{color:var(--txt);border-color:var(--line2)}
 .seg button.on{background:linear-gradient(180deg,#1b2942,#16223a);color:#fff;border-color:var(--accent)}
 .seg button.on.honest{border-color:var(--up);background:linear-gradient(180deg,#15301f,#11271a);color:#bdf0d2}
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
 .kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px}
 .kpi{background:var(--ink2);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
 .kpi .k{font-family:var(--mono);color:var(--mut);font-size:10px;letter-spacing:.1em;text-transform:uppercase} .kpi .v{font-family:var(--mono);font-size:19px;font-weight:700;margin-top:2px}
 .bnote{font-family:var(--mono);font-size:12px;color:var(--warn);margin-top:10px}
 .banner{border-radius:10px;padding:10px 14px;margin:0 0 10px;max-width:920px;font-size:12.5px;line-height:1.5}
 .banner.gross{border-left:3px solid var(--warn);background:rgba(244,184,96,.06);color:#e8c98a}
 .banner.live{border-left:3px solid var(--up);background:rgba(39,211,138,.06);color:#9fe3bd}
 @media(max-width:560px){.left,.right{min-width:0} .kpis{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="wrap">
 <p class="eyebrow">Backtests · Full vs Recent</p>
 <h1>Backtest <span class="thin">Board</span></h1>
 <p class="lede">Toggle <b>period</b> + <b>leverage</b>. <b style="color:var(--up)">Recent (2022→now)</b> strips the 2018–21 mega-bull — the honest-er guide to what these do in the <i>current</i> regime. <b style="color:var(--warn)">Full (2018–26)</b> is the bull-inflated gross ceiling. All CAGR/MaxDD/Sharpe recomputed from each curve for the chosen window (table matches chart). Still backtests — not live.</p>
 <div class="nav">
  <a href="./index.html">◆ Strategy Book</a>
  <a href="./stocks.html">📈 Stocks — Spike Hunter</a>
  <a href="./strategy_lab.html">🧪 Strategy Lab — the gauntlet</a>
  <a class="home" href="./board.html">📊 Backtest Board</a>
 </div>
 <div class="banner live" id="periodbanner"></div>

 <div class="toggles">
  <div class="seg" id="per"><span class="lbl">Period</span><button data-p="recent" class="on honest">Recent · 2022→ (honest)</button><button data-p="full">Full · 2018–26 (gross)</button></div>
  <div class="seg" id="lev"><span class="lbl">Leverage</span><button data-l="1x" class="on">1×</button><button data-l="2x">2×</button><button data-l="3x">3×</button><button data-l="all">ALL ⊞</button></div>
 </div>
 <div class="cols">
  <div class="left"><table id="t"><thead id="th"></thead><tbody></tbody></table></div>
  <div class="right"><div class="card">
   <h2 id="nm" style="margin:0 0 4px">—</h2><div class="note" id="bnote2" style="margin-bottom:12px"></div>
   <div class="kpis">
    <div class="kpi"><div class="k">CAGR</div><div class="v" id="kc">—</div></div>
    <div class="kpi"><div class="k">Sharpe*</div><div class="v" id="ks">—</div></div>
    <div class="kpi"><div class="k">Sortino*</div><div class="v" id="kso">—</div></div>
    <div class="kpi"><div class="k">Calmar</div><div class="v" id="kca">—</div></div>
    <div class="kpi"><div class="k">Max DD</div><div class="v" id="kd">—</div></div>
    <div class="kpi"><div class="k">Win%</div><div class="v" id="kw">—</div></div>
   </div>
   <canvas id="cv" width="860" height="560"></canvas>
   <div class="bnote" id="warn"></div>
  </div></div>
 </div>
 <footer>*Sharpe is curve-derived (consistent across both windows), not the native-frequency OOS figure — for that + net-of-fees see Strategy Lab. Backtests, not live · gross of funding · plan real DD ≈ 2× · not financial advice · Lemonef/Trade</footer>
</div>
<script>
 const DATA=__DATA__; let L="1x", P="recent", key="cagr", dir=-1, sel=DATA[0];
 const f=(v,s="")=>{if(v===null||v===undefined||Number.isNaN(v))return `<span style="color:var(--dim)">—</span>`;const c=v>0?"pos":(v<0?"neg":"");return `<span class="${c}">${v}${s}</span>`};
 function cell(s,lev){const lv=s.levels[lev]; return lv?lv[P]:null;}
 function draw(s,lv){
  const isR=s.category==="research";
  const L2=isR?"1x":(lv||(L==="all"?"1x":L)); const k=cell(s,L2);
  document.getElementById("nm").textContent=s.name+"  @"+L2+(isR?"  (1× only)":"")+"  ·  "+(P==="recent"?"2022→now":"2018–26");
  document.getElementById("bnote2").textContent=(k&&k.ruin?"⛔ LIQUIDATED at "+L2+" — equity hit zero. Not survivable. ":"")+(s.note||"");
  if(!k){return;}
  document.getElementById("kc").innerHTML=f(k.cagr,"%");
  document.getElementById("ks").innerHTML=f(k.sharpe);
  document.getElementById("kso").innerHTML=f(k.sortino);
  document.getElementById("kca").innerHTML=f(k.calmar);
  document.getElementById("kd").innerHTML=f(k.maxdd,"%");
  document.getElementById("kw").textContent=(k.win||0)+"%";
  const cv=document.getElementById("cv"),x=cv.getContext("2d"),W=cv.width,H=cv.height,Pd=58; x.clearRect(0,0,W,H);
  const pts=(k.series||[]).map(p=>p[1]),n=pts.length; if(!n)return;
  const mn=Math.min(...pts),mx=Math.max(...pts),rng=(mx-mn)||1;
  const X=i=>Pd+i/(n-1)*(W-2*Pd),Y=v=>H-Pd-(v-mn)/rng*(H-2*Pd);
  x.strokeStyle="#222c3d";x.fillStyle="#8a97aa";x.font="13px 'JetBrains Mono',monospace";
  for(let g=0;g<=4;g++){const v=mn+rng*g/4,yy=Y(v);x.beginPath();x.moveTo(Pd,yy);x.lineTo(W-Pd,yy);x.stroke();x.fillText("$"+Math.round(v).toLocaleString(),6,yy+4);}
  if(mn<=10000&&mx>=10000){x.strokeStyle="#2c3a50";x.setLineDash([4,4]);x.beginPath();x.moveTo(Pd,Y(10000));x.lineTo(W-Pd,Y(10000));x.stroke();x.setLineDash([]);}
  x.strokeStyle=(k.cagr==null)?"#ff5a6a":(k.cagr>=0?"#27d38a":"#ff5a6a");x.lineWidth=2;x.beginPath();
  pts.forEach((v,i)=>{i?x.lineTo(X(i),Y(v)):x.moveTo(X(i),Y(v))});x.stroke();
 }
 function render(){
  document.getElementById("periodbanner").innerHTML = P==="recent"
    ? "✅ <b>Recent (2022→now)</b> — the 2018–21 explosion removed. Closest backtest proxy for the current regime, but STILL backtest + gross. The real forward truth is the live paper bot on the <b>Strategy Book</b>."
    : "⚠ <b>Full (2018–26)</b> — includes the 2020–21 mega-bull that won't repeat. Optimistic CEILING; do NOT use for forward expectation. Flip to <b>Recent</b> for the honest-er view.";
  const th=document.getElementById("th"),tb=document.querySelector("#t tbody");
  th.innerHTML=`<tr><th class="l" data-k="name">Strategy</th><th data-k="cagr">CAGR%</th><th data-k="sharpe">Sharpe*</th><th data-k="calmar">Calmar</th><th data-k="maxdd">MaxDD%</th><th data-k="win">Win%</th><th class="l" data-k="category">Type</th></tr>`;
  let rows=[];
  if(L==="all"){ DATA.forEach(s=>(s.category==="research"?["1x"]:["1x","2x","3x"]).forEach(lv=>{const k=cell(s,lv);if(k)rows.push({label:s.name+" ("+lv+")",cagr:k.cagr,sharpe:k.sharpe,calmar:k.calmar,maxdd:k.maxdd,win:k.win||0,category:s.category,s:s,lv:lv});}));}
  else { rows=DATA.map(s=>{
    if(s.category==="research" && L!=="1x") return {label:s.name,cagr:null,sharpe:null,calmar:null,maxdd:null,win:null,category:s.category,s:s,lv:"1x"};
    const k=cell(s,L);return {label:s.name,cagr:k.cagr,sharpe:k.sharpe,calmar:k.calmar,maxdd:k.maxdd,win:k.win||0,category:s.category,s:s,lv:L};});}
  rows.sort((a,b)=>{let av=key==="name"?a.label:(key==="category"?a.category:a[key]),bv=key==="name"?b.label:(key==="category"?b.category:b[key]);
    if(typeof av==="string")return av.localeCompare(bv)*dir;
    av=(av==null||Number.isNaN(av))?-Infinity:av; bv=(bv==null||Number.isNaN(bv))?-Infinity:bv; return (av-bv)*dir;});
  tb.innerHTML="";
  rows.forEach(r=>{const tr=document.createElement("tr");tr.className="row"+(sel===r.s?" sel":"");
   tr.innerHTML=`<td class="l">${r.label}</td><td>${f(r.cagr)}</td><td>${f(r.sharpe)}</td><td>${f(r.calmar)}</td><td>${f(r.maxdd)}</td><td>${r.win==null?'<span style="color:var(--dim)">—</span>':r.win}</td><td class="l"><span class="tag ${r.category}">${r.category}</span></td>`;
   tr.onclick=()=>{sel=r.s; draw(r.s, r.lv); render();};tb.appendChild(tr);});
  document.querySelectorAll("#t th").forEach(t=>{if(t.dataset.k)t.onclick=()=>{const kk=t.dataset.k;dir=(kk===key)?-dir:-1;key=kk;render();};});
  document.getElementById("warn").textContent = (L==="all") ? "ALL view: one row per strategy × leverage — click a header to sort. 2×/3× include ~10% financing; DD scales, >2× risks liquidation."
    : (L!=="1x" ? "⚠ "+L+" includes ~10% financing. Plan ~2× this maxDD live; >2× risks liquidation." : "");
 }
 document.querySelectorAll("#per button").forEach(b=>b.onclick=()=>{P=b.dataset.p;document.querySelectorAll("#per button").forEach(x=>{x.classList.remove("on");x.classList.toggle("honest",x.dataset.p==="recent");});b.classList.add("on");render();draw(sel);});
 document.querySelectorAll("#lev button").forEach(b=>b.onclick=()=>{L=b.dataset.l;document.querySelectorAll("#lev button").forEach(x=>x.classList.remove("on"));b.classList.add("on");render();draw(sel);});
 render();draw(sel);
</script>
<script type="module" src="./anim.js"></script>
</body></html>"""
open("web/board.html", "w", encoding="utf-8").write(HTML.replace("__DATA__", DATA))
print("wrote web/board.html")
