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
import json, math, datetime as dt
from pathlib import Path

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
    # --- extended panel (all curve-derived; PF/expectancy/t-stat need a trade log, not here) ---
    gains = sum(r for r in rets if r > 0); pains = -sum(r for r in rets if r < 0)
    gtp = round(gains / pains, 2) if pains > 0 else None          # gain-to-pain (= Omega@0)
    pk = eq[0]; dds = []
    for v in eq:
        pk = max(pk, v); dds.append((v / pk - 1) * 100)
    ulcer = round((sum(x * x for x in dds) / len(dds)) ** 0.5, 1)  # depth×duration of pain
    srt = sorted(rets); k5 = max(1, int(len(srt) * 0.05))
    cvar = round(sum(srt[:k5]) / k5 * 100, 1)                      # avg worst-5% period return
    sdp = sd if sd > 0 else 1e-9
    skew = round(sum(((r - mean) / sdp) ** 3 for r in rets) / len(rets), 2)
    kurt = round(sum(((r - mean) / sdp) ** 4 for r in rets) / len(rets) - 3, 2)
    logs = [math.log(v) for v in eq]; nn = len(logs); xs = list(range(nn))
    xb = sum(xs) / nn; yb = sum(logs) / nn
    sxx = sum((x - xb) ** 2 for x in xs); sxy = sum((xs[i] - xb) * (logs[i] - yb) for i in range(nn))
    slope = sxy / sxx if sxx else 0
    sse = sum((logs[i] - (yb + slope * (xs[i] - xb))) ** 2 for i in range(nn))
    se = (sse / (nn - 2) / sxx) ** 0.5 if nn > 2 and sxx > 0 and sse > 0 else None
    kratio = round(slope / se, 2) if se else None                 # equity-curve smoothness
    pk2 = eq[0]; uws = None; longest = 0
    for i, v in enumerate(eq):
        if v >= pk2: pk2 = v; uws = None
        else:
            if uws is None: uws = i
            longest = max(longest, (dt.date.fromisoformat(series[i][0]) - dt.date.fromisoformat(series[uws][0])).days)
    muw = round(longest / 30.4, 1)                                # longest months underwater
    tstat = round(mean / (sd / len(rets) ** 0.5), 2) if sd > 0 else None  # edge significance (return-stream)
    return {"cagr": cagr, "sharpe": sharpe, "sortino": sortino, "calmar": calmar, "maxdd": mddpct,
            "gtp": gtp, "ulcer": ulcer, "cvar": cvar, "skew": skew, "kurt": kurt, "kratio": kratio,
            "tstat": tstat, "muw": muw, "win": win, "series": series}


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


strats = split(d["strategies"])
# Inject the REAL walk-forward OOS panel (from panel_dump.py → lab_panel.json) as a 3rd period.
lab_path = Path("web/lab_panel.json")
lab = json.loads(lab_path.read_text(encoding="utf-8")) if lab_path.exists() else {}
OOS_MAP = {"Crypto regime-trend": "trend"}          # board strategy name -> lab key
for s in strats:
    k = OOS_MAP.get(s["name"])
    if k and k in lab:
        s["oos"] = lab[k]
# the .55/.25/.20 book isn't in board_data → add it as an OOS-only row.
# Use the HOLDOUT ("blend"), not blend_full. ⚠ even this is quasi-OOS: the weights were
# fit on this window (book_final.py weight-search), so it's optimistic, NOT true walk-forward.
if "blend" in lab:
    strats.append({"name": "Crypto blend .55/.25/.20 (quasi-OOS ⚠)", "category": "deploy",
                   "note": "book_final.py · 2nd-half holdout, BUT weights were fit on this window → quasi-OOS / optimistic, NOT genuine walk-forward (only the trend core is true WF)",
                   "levels": {}, "oos": lab["blend"]})
# The rest have NO params to walk-forward (buy-holds, fixed-weight blends) → their honest
# out-of-sample = the post-2022 HOLDOUT (= the Recent slice). Tag as _holdout so they're
# clearly NOT genuine walk-forward, but the OOS table has full strategy parity.
for s in strats:
    if "oos" not in s:
        rp = (s.get("levels", {}).get("1x") or {}).get("recent")
        if rp and rp.get("sharpe") is not None:
            s["oos"] = dict(rp); s["oos"]["_holdout"] = True
DATA = json.dumps(strats)

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
 .seg button{opacity:.6} .seg button.on{opacity:1}
 .seg button:hover{color:var(--txt);border-color:var(--line2);opacity:1}
 .seg button.on{background:linear-gradient(180deg,#1b2942,#16223a);color:#fff;border-color:var(--accent)}
 .seg button.on.honest{border-color:var(--up);background:linear-gradient(180deg,#15301f,#11271a);color:#bdf0d2}
 .wrap{max-width:1500px}
 .cols{display:block}
 .left{width:100%;margin-bottom:18px;overflow-x:auto} .right{width:100%}
 #t{width:100%;border-collapse:collapse;font-size:11px} #t th,#t td{padding:6px 7px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
 #t th{font-family:var(--mono);color:var(--mut);font-size:9.5px;letter-spacing:.04em;text-transform:uppercase;cursor:pointer} #t td.l,#t th.l{text-align:left}
 #t td{font-family:var(--mono)}
 tr.row{cursor:pointer} tr.row:hover td{background:rgba(124,196,255,.04)}
 tr.grouphl td{background:rgba(124,196,255,.07)}                                  /* hover → whole strategy group lights up */
 tr.selgroup td{background:rgba(124,196,255,.07)}                                 /* same strategy, other leverage rows */
 tr.selgroup td:first-child{box-shadow:inset 3px 0 0 rgba(124,196,255,.5)}
 tr.selopen td{background:rgba(232,161,75,.16)}                                   /* the EXACT open row (its chart is shown) — amber */
 tr.selopen td:first-child{box-shadow:inset 3px 0 0 var(--amber);color:var(--amber)}
 .pos{color:var(--up)} .neg{color:var(--dn)}
 .tag{font-family:var(--mono);font-size:10px;font-weight:700;padding:2px 8px;border-radius:6px}
 .deploy{background:rgba(39,211,138,.13);color:var(--up);border:1px solid rgba(39,211,138,.3)}
 .diversifier{background:rgba(124,196,255,.12);color:var(--accent);border:1px solid rgba(124,196,255,.3)}
 .benchmark{background:rgba(183,156,255,.12);color:var(--accent2);border:1px solid rgba(183,156,255,.3)}
 .research{background:rgba(244,184,96,.12);color:var(--warn);border:1px dashed rgba(244,184,96,.5)}
 #cv{width:100%;height:300px;background:var(--ink2);border:1px solid var(--line);border-radius:10px}
 .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:10px}
 .kpi{background:var(--ink2);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
 .kpi .k{font-family:var(--mono);color:var(--mut);font-size:10px;letter-spacing:.1em;text-transform:uppercase} .kpi .v{font-family:var(--mono);font-size:19px;font-weight:700;margin-top:2px}
 .bnote{font-family:var(--mono);font-size:12px;color:var(--warn);margin-top:10px}
 .banner{border-radius:10px;padding:10px 14px;margin:0 0 10px;max-width:920px;font-size:12.5px;line-height:1.5}
 .banner.gross{border-left:3px solid var(--warn);background:rgba(244,184,96,.06);color:#e8c98a}
 .banner.live{border-left:3px solid var(--up);background:rgba(39,211,138,.06);color:#9fe3bd}
 .kpis2{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:8px 0 4px}
 .kpis2 .kpi{padding:8px 10px} .kpis2 .v{font-size:15px}
 .extranote{font-family:var(--mono);font-size:10px;color:var(--dim);margin:2px 0 8px;line-height:1.4}
 .heat{margin-top:14px;overflow-x:auto}
 .heat .ht{font-family:var(--mono);font-size:11px;color:var(--mut);margin:0 0 4px}
 .heat table{border-collapse:collapse;font-family:var(--mono);font-size:11px;width:100%;max-width:940px}
 .heat td,.heat th{min-width:42px}
 .heat td,.heat th{padding:4px 4px;text-align:center;border:1px solid var(--ink)}
 .heat th{color:var(--mut);font-weight:500} .heat td.y{color:var(--mut);text-align:right;padding-right:7px}
 .heat .ann{font-weight:700;border-left:2px solid var(--line2)}
 #oospanel{width:100%;border-collapse:collapse;font-size:11px}
 #oospanel td,#oospanel th{padding:8px 8px;text-align:right;border-bottom:1px solid var(--line);font-family:var(--mono);white-space:nowrap}
 #oospanel th{color:var(--mut);font-size:10px;letter-spacing:.05em;text-transform:uppercase}
 #oospanel td.l,#oospanel th.l{text-align:left;font-family:var(--sans)}
 @media(max-width:560px){.left,.right{min-width:0} .kpis{grid-template-columns:repeat(2,1fr)} .kpis2{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="wrap">
 <p class="eyebrow">Backtests · Full vs Recent</p>
 <h1>Backtest <span class="thin">Board</span></h1>
 <p class="lede">Toggle <b>period</b> + <b>leverage</b>. <b style="color:var(--up)">OOS</b> = walk-forward — but only the <b>trend core</b> is genuinely walk-forward (the rest are the post-2022 holdout = Recent). <b style="color:var(--up)">Recent (2022→now)</b> strips the 2018–21 mega-bull (current-regime, still in-sample). <b style="color:var(--warn)">Full (2018–26)</b> = bull-inflated gross ceiling. <b>"deploy" = passed the gauntlet, NOT live yet</b> (paper stage). <b>One wide table, full metric panel.</b> Click any row for its chart + heatmap.</p>
 <div id="nav"></div>
 <script src="./nav.js"></script>
 <div class="banner live" id="periodbanner"></div>

 <div class="toggles">
  <div class="seg" id="per"><span class="lbl">Period</span><button data-p="recent" class="on honest">Recent · 2022→ (honest)</button><button data-p="full">Full · 2018–26 (gross)</button><button data-p="oos">OOS · walk-forward (1 genuine)</button></div>
  <div class="seg" id="lev"><span class="lbl">Leverage</span><button data-l="1x" class="on">1×</button><button data-l="2x">2×</button><button data-l="3x">3×</button><button data-l="all">ALL ⊞</button></div>
  <div style="margin-left:auto;display:flex;gap:7px;align-items:center;font-family:var(--mono);font-size:10px">
    <span style="color:var(--mut);letter-spacing:.1em">ALL VIEW →</span>
    <span style="padding:3px 10px;border-radius:999px;background:rgba(124,196,255,.15);color:#7cc4ff;border:1px solid rgba(124,196,255,.4);font-weight:700">1×</span>
    <span style="padding:3px 10px;border-radius:999px;background:rgba(39,211,138,.15);color:#27d38a;border:1px solid rgba(39,211,138,.4);font-weight:700">2×</span>
    <span style="padding:3px 10px;border-radius:999px;background:rgba(232,161,75,.15);color:#e8a14b;border:1px solid rgba(232,161,75,.4);font-weight:700">3×</span>
  </div>
 </div>
 <div class="cols">
  <div class="left"><table id="t"><thead id="th"></thead><tbody></tbody></table>
   <div class="extranote" style="margin-top:8px"><b>PF</b> = trade-level (gross win$ ÷ loss$), only defined for bots that place DISCRETE trades (open→close) → only the <b>trend core</b> (1.3). Blends &amp; buy-holds are continuous return streams (no trades) → PF n/a. <b>Win%</b> ≠ same measure across rows: trend = % winning TRADES (33%, low is normal for trend-following — few big winners); the rest = % winning PERIODS/bars (~50%) — <b>don't compare the two</b>. All return-based metrics (Sharpe/Calmar/DD/skew…) apply to everything. · <b>Dimmed cols</b> at 2×/3× = unchanged by leverage.</div>
  </div>
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
   <div class="kpis2">
    <div class="kpi"><div class="k">Gain/Pain</div><div class="v" id="kgp">—</div></div>
    <div class="kpi"><div class="k">Ulcer</div><div class="v" id="kul">—</div></div>
    <div class="kpi"><div class="k">CVaR 5%</div><div class="v" id="kcv">—</div></div>
    <div class="kpi"><div class="k">K-ratio</div><div class="v" id="kkr">—</div></div>
    <div class="kpi"><div class="k">Skew</div><div class="v" id="ksk">—</div></div>
    <div class="kpi"><div class="k">Kurtosis</div><div class="v" id="kku">—</div></div>
    <div class="kpi"><div class="k">Mo. u/w</div><div class="v" id="kuw">—</div></div>
   </div>
   <div class="extranote">Detail for the selected row. Full/Recent = curve-derived (in-sample); OOS = real walk-forward (trade-level PF/Win/t-stat where the bot places discrete trades). *Sharpe/Sortino curve-derived.</div>
   <canvas id="cv" width="860" height="560"></canvas>
   <div id="heat" class="heat"></div>
   <div class="bnote" id="warn"></div>
  </div></div>
 </div>
 <h2><span class="n">02</span> The gauntlet <span class="mut" style="font-family:var(--mono);font-size:12px;font-weight:400">— every bot must pass</span></h2>
 <div class="card" style="font-family:var(--mono);font-size:12px;color:var(--mut);line-height:1.9">
   <b>1.</b> Walk-forward OOS · <b>2.</b> Real DD ≈ 2× close-DD · <b>3.</b> Black-swan / regime survival (2020/2022/2026) · <b>4.</b> Year-by-year (bull-flattered?) · <b>5.</b> Survivorship / PIT universe · <b>6.</b> Fees / funding / slippage · <b>7.</b> Block-bootstrap p05 · <b>8.</b> ≥100 trades · <b>9.</b> Random-entry + inversion baseline · <b>10.</b> Beat buy-hold-BTC · <b>11.</b> Mechanism-backed, not curve-fit · <b>12.</b> Leverage ≤2× · <b>13.</b> CRITIQUE + AUDIT (audit verifies the critique too).
 </div>

 <h2><span class="n">03</span> Honest caveats <span class="mut" style="font-family:var(--mono);font-size:12px;font-weight:400">— apply to ALL</span></h2>
 <div class="banner gross" style="line-height:1.75">
   • <b>Bull-flattered:</b> year-by-year the book LOSES in bear; the regime filter (→cash) limits damage, doesn't make it a bear winner.<br>
   • <b>Real DD ≈ 2× close DD</b> (intrabar + leverage); &gt;2× risks liquidation.<br>
   • <b>Survivorship:</b> backtests use surviving coins → optimistic ceiling (PIT universe is the fix).<br>
   • <b>Funding NOT modeled</b> → any leveraged CAGR is optimistic; 1× spot properly costed.<br>
   • <b>Real gate unmet:</b> none has run live through a regime change — that, not any backtest, unlocks real money (3-6mo paper + 1 regime shift).<br>
   • <b>Honest live expectation:</b> ~15–25% CAGR moderate leverage, real DD ~2× — beats index, not magic.
 </div>

 <h2><span class="n">04</span> Rejected <span class="mut" style="font-family:var(--mono);font-size:12px;font-weight:400">— failed the gauntlet (discipline, not findings)</span></h2>
 <div class="card" style="font-family:var(--mono);font-size:12px;color:var(--mut);line-height:1.7">
   Bear-short sleeve · Donchian ensemble SSRN (OOS 0.73&lt;0.86) · AdaptiveTrend arXiv 2.41 (shorts+survivorship) · vol-targeting (double-counts) · funding market-timing (fade thesis false) · on-chain/liquidation (decayed) · XS-mom/lowvol/short-reversal (neg OOS) · RTN-Core rotational (0.53, killed) · HFT lead-lag AVAX +1523% (dies on fees) · halving/Q4 seasonality (small caveated tilt only). <b class="amber" style="color:var(--amber)">Frontier exhausted — gains now come from construction + execution, not new signals.</b>
 </div>

 <footer>Full/Recent = curve-derived (in-sample). OOS = real walk-forward (trustworthy). Backtests, not live · gross of funding · plan real DD ≈ 2× · not financial advice · Lemonef/Trade</footer>
</div>
<script>
 const DATA=__DATA__; let L="1x", P="recent", key="cagr", dir=-1, sel=DATA[0], selLev="1x";
 const f=(v,s="")=>{if(v===null||v===undefined||Number.isNaN(v))return `<span style="color:var(--dim)">—</span>`;const c=v>0?"pos":(v<0?"neg":"");return `<span class="${c}">${v}${s}</span>`};
 const fp=(v,s="")=>(v===null||v===undefined||Number.isNaN(v))?`<span style="color:var(--dim)">—</span>`:v+s;  // plain, no sign-color
 function projLev(p,lev){const n=lev==='all'?1:(parseInt(lev)||1);if(n<=1)return p;
   const sig=p.sharpe?Math.abs(p.cagr/p.sharpe)/100:0.25;      // annual vol (decimal) ≈ CAGR/Sharpe
   const drag=((n*n-n)/2)*sig*sig*100;                          // leverage VOLATILITY DRAG (%)
   const cagr=Math.round((n*p.cagr-(n-1)*10-drag)*10)/10;       // N×ret − financing − vol drag
   const maxdd=Math.round(p.maxdd*n*10)/10;
   const liq=(maxdd*2)<=-100;                                   // real DD≈2× → wipeout
   return Object.assign({},p,{cagr,maxdd,calmar:maxdd?Math.round(cagr/Math.abs(maxdd)*100)/100:null,_proj:true,ruin:liq});}
 function cell(s,lev){ if(P==='oos'){ return s.oos?projLev(s.oos,lev):null; } const lv=s.levels[lev]; return lv?lv[P]:null; }
 function monthlyGrid(series){
  if(!series||series.length<3) return '';
  const m={};
  for(let i=1;i<series.length;i++){const ym=series[i][0].slice(0,7);m[ym]=(m[ym]||1)*(series[i][1]/series[i-1][1]);}
  const yr={}; Object.keys(m).forEach(ym=>{const a=ym.split('-');(yr[a[0]]=yr[a[0]]||{})[+a[1]]=(m[ym]-1)*100;});
  const ys=Object.keys(yr).sort(), MO=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const col=v=>{if(v==null)return 'background:transparent';const a=Math.min(1,Math.abs(v)/15);return v>=0?`background:rgba(39,211,138,${a*.55});color:#d6f5e4`:`background:rgba(255,90,106,${a*.55});color:#ffd9de`;};
  let h='<div class="ht">Monthly returns (approx, from the periodic curve) — green = up, red = down</div><table><tr><th></th>'+MO.map(x=>`<th>${x}</th>`).join('')+'<th class="ann">Year</th></tr>';
  ys.forEach(y=>{let ann=1;for(let mo=1;mo<=12;mo++){if(yr[y][mo]!=null)ann*=(1+yr[y][mo]/100);}ann=(ann-1)*100;
   h+=`<tr><td class="y">${y}</td>`;
   for(let mo=1;mo<=12;mo++){const v=yr[y][mo];h+=`<td style="${col(v)}">${v==null?'':(v>=0?'+':'')+v.toFixed(1)}</td>`;}
   h+=`<td class="ann" style="${col(ann)}">${(ann>=0?'+':'')+ann.toFixed(0)}%</td></tr>`;});
  return h+'</table>';
 }
 function draw(s,lv){
  const isR=s.category==="research";
  const L2=isR?"1x":(lv||(L==="all"?"1x":L)); const k=cell(s,L2);
  document.getElementById("nm").textContent=s.name+"  @"+L2+(isR?"  (1× only)":"")+"  ·  "+(P==="oos"?"OOS walk-forward":(P==="recent"?"2022→now":"2018–26"));
  document.getElementById("bnote2").textContent=(k&&k.ruin?"⛔ LIQUIDATED at "+L2+" — equity hit zero. Not survivable. ":"")+(s.note||"");
  if(!k){return;}
  document.getElementById("kc").innerHTML=f(k.cagr,"%");
  document.getElementById("ks").innerHTML=f(k.sharpe);
  document.getElementById("kso").innerHTML=f(k.sortino);
  document.getElementById("kca").innerHTML=f(k.calmar);
  document.getElementById("kd").innerHTML=f(k.maxdd,"%");
  document.getElementById("kw").textContent=((k.wr!=null?k.wr:k.win)||0)+"%";
  document.getElementById("kgp").innerHTML=f(k.gtp);
  document.getElementById("kul").innerHTML=fp(k.ulcer,"%");
  document.getElementById("kcv").innerHTML=f(k.cvar,"%");
  document.getElementById("kkr").innerHTML=f(k.kratio);
  document.getElementById("ksk").innerHTML=fp(k.skew);
  document.getElementById("kku").innerHTML=fp(k.kurt);
  document.getElementById("kuw").textContent=(k.muw!=null?k.muw+" mo":"—");
  document.getElementById("heat").innerHTML=monthlyGrid(k.series);
  const cv=document.getElementById("cv"),x=cv.getContext("2d"),Pd=58;
  const dpr=window.devicePixelRatio||1; cv.width=(cv.clientWidth||860)*dpr; cv.height=(cv.clientHeight||300)*dpr; x.scale(dpr,dpr);
  const W=cv.clientWidth||860,H=cv.clientHeight||300; x.clearRect(0,0,W,H);
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
  document.getElementById("periodbanner").innerHTML = P==="oos"
    ? "✅ <b>OOS</b> — only <b>Trend core</b> is GENUINE walk-forward (tagged <b>WF✓</b>). <b>Blend = quasi-OOS</b> (weights fit on-sample). Rows tagged <b>holdout</b> = buy-holds / fixed-weight blends with no params to walk-forward → their out-of-sample is just the post-2022 slice (= Recent). Trend PF/Win/$ = fixed config (illustrative). 2×/3× = projection (vol-drag); real DD ≈ 2×, ⛔ = wipeout."
    : P==="recent"
    ? "✅ <b>Recent (2022→now)</b> — 2018–21 explosion removed; current-regime proxy, but STILL in-sample + gross. Real forward truth = the live bot on the <b>Strategy Book</b>."
    : "⚠ <b>Full (2018–26)</b> — includes the 2020–21 mega-bull. Optimistic CEILING; not for forward expectation. Flip to <b>OOS</b> for the walk-forward view (only the trend core is genuine).";
  const th=document.getElementById("th"),tb=document.querySelector("#t tbody");
  const hl=(L==='2x'||L==='3x')?' style="color:var(--accent);text-shadow:0 0 6px rgba(124,196,255,.4)"':'';   // mark the cols leverage actually moves
  th.innerHTML=`<tr><th class="l" data-k="name">Strategy</th><th data-k="cagr"${hl}>CAGR%${hl?' ▲':''}</th><th data-k="sharpe">Sharpe</th><th data-k="sortino">Sortino</th><th data-k="calmar"${hl}>Calmar${hl?' ▲':''}</th><th data-k="maxdd"${hl}>MaxDD%${hl?' ▲':''}</th><th data-k="tstat">t-stat</th><th data-k="pf">PF</th><th data-k="win">Win%</th><th data-k="gtp">Gain/Pain</th><th data-k="ulcer">Ulcer</th><th data-k="cvar">CVaR</th><th data-k="skew">Skew</th><th data-k="kurt">Kurt</th><th data-k="muw">Mo u/w</th><th class="l" data-k="category">Type</th></tr>`;
  let rows=[];
  const LVC={'1x':'124,196,255','2x':'39,211,138','3x':'232,161,75'};
  const levTag=lv=>{if(L!=='all')return '';const c=LVC[lv];return ' <span style="padding:1px 8px;border-radius:999px;background:rgba('+c+',.15);color:rgb('+c+');border:1px solid rgba('+c+',.4);font-weight:700;font-size:9.5px">'+lv+'</span>';};
  if(P==='oos'){
    DATA.filter(s=>s.oos).forEach(s=>{(L==='all'?['1x','2x','3x']:[L]).forEach(lv=>{if(s.category==='research'&&lv!=='1x')return;const k=cell(s,lv);if(!k)return;const tag=k._holdout?'  · holdout':(s.name.includes('quasi')?'':'  · WF✓');rows.push({label:s.name+levTag(lv)+tag,k,category:s.category,s,lv});});});
  } else if(L==="all"){
    DATA.forEach(s=>{ if(!s.levels||!Object.keys(s.levels).length)return; (s.category==="research"?["1x"]:["1x","2x","3x"]).forEach(lv=>{const k=cell(s,lv);if(k)rows.push({label:s.name+levTag(lv),k,category:s.category,s,lv});});});
  } else {
    DATA.forEach(s=>{ if(!s.levels||!Object.keys(s.levels).length)return; if(s.category==="research"&&L!=="1x"){rows.push({label:s.name,k:null,category:s.category,s,lv:"1x"});return;} const k=cell(s,L);if(k)rows.push({label:s.name,k,category:s.category,s,lv:L});});
  }
  const kv=r=> key==="name"?r.label : key==="category"?r.category : (r.k?r.k[key]:null);
  rows.sort((a,b)=>{let av=kv(a),bv=kv(b); if(typeof av==="string")return (av||"").localeCompare(bv||"")*dir; av=(av==null||Number.isNaN(av))?-Infinity:av; bv=(bv==null||Number.isNaN(bv))?-Infinity:bv; return (av-bv)*dir;});
  const na='<span class="mut">n/a</span>';
  const cells=k=>{ if(!k) return '<td colspan="14" class="mut">— no data this period</td>';
    const d=h=>k._proj?`<span style="opacity:.5">${h}</span>`:h;   // dim metrics leverage doesn't change (readable but secondary)
    return `<td>${f(k.cagr,'%')}</td><td>${d(f(k.sharpe))}</td><td>${d(f(k.sortino))}</td><td>${f(k.calmar)}</td><td class="neg">${f(k.maxdd,'%')}${k.ruin?' ⛔':''}</td>`
     +`<td>${d(k.tstat==null?na:(Math.abs(k.tstat)>=2?f(k.tstat):'<span style="color:var(--warn)" title="not statistically significant (|t|<2)">'+k.tstat+'</span>'))}</td><td>${d(k.pf!=null?f(k.pf):na)}</td><td>${d((k.wr!=null||k.win!=null)?((k.wr!=null?k.wr:k.win)+'%'):na)}</td>`
     +`<td>${d(f(k.gtp))}</td><td>${d(fp(k.ulcer,'%'))}</td><td>${d(f(k.cvar,'%'))}</td><td style="color:${k.skew<0?'var(--dn)':'var(--up)'}">${d(fp(k.skew))}</td><td>${d(fp(k.kurt))}</td><td>${d(k.muw!=null?k.muw+'mo':'—')}</td>`; };
  tb.innerHTML="";
  rows.forEach(r=>{const tr=document.createElement("tr");const isOpen=sel===r.s&&selLev===r.lv,inGroup=sel===r.s;
   tr.className="row"+(isOpen?" selopen":(inGroup?" selgroup":""));
   tr.dataset.strat=DATA.indexOf(r.s);
   tr.innerHTML=`<td class="l">${isOpen?'▸ ':''}${r.label}</td>`+cells(r.k)+`<td class="l"><span class="tag ${r.category}">${({deploy:'paper',benchmark:'bench',diversifier:'divers'})[r.category]||r.category}</span></td>`;
   tr.onmouseenter=()=>document.querySelectorAll('#t tbody tr[data-strat="'+tr.dataset.strat+'"]').forEach(x=>x.classList.add('grouphl'));
   tr.onmouseleave=()=>document.querySelectorAll('#t tbody tr.grouphl').forEach(x=>x.classList.remove('grouphl'));
   tr.onclick=()=>{sel=r.s; selLev=r.lv; draw(r.s,r.lv); render();};tb.appendChild(tr);});
  const sh=document.querySelector('#t th[data-k="'+key+'"]'); if(sh) sh.insertAdjacentHTML('beforeend', dir<0?' ↓':' ↑');
  document.querySelectorAll("#t th").forEach(t=>{if(t.dataset.k)t.onclick=()=>{const kk=t.dataset.k;dir=(kk===key)?-dir:-1;key=kk;render();};});
  document.getElementById("warn").textContent = P==='oos'
    ? "OOS: trend = genuine walk-forward; blend = quasi-OOS (weights fit on-sample). PF/Win/$ = fixed-config illustrative. 2×/3× = projection (vol-drag, real DD≈2×, ⛔=wipeout)."
    : "⚠ Full/Recent skew/kurt/CVaR are COARSE-sampled (~24d curve) — not comparable to OOS native-frequency. "
      + ((L==="all") ? "ALL = one row per strategy×leverage; 2×/3× include ~10% financing + vol-drag."
         : (L!=="1x" ? L+" includes ~10% financing + vol-drag; real DD≈2×, >2× risks liquidation. Dimmed cols = unchanged by leverage (only CAGR/MaxDD/Calmar move). ⚠ Sharpe shown FLAT — real levered Sharpe is LOWER (financing + liquidation gaps); leverage is not free." : ""));
 }
 document.querySelectorAll("#per button").forEach(b=>b.onclick=()=>{P=b.dataset.p;document.querySelectorAll("#per button").forEach(x=>{x.classList.remove("on");x.classList.toggle("honest",x.dataset.p==="recent"||x.dataset.p==="oos");});b.classList.add("on");render();draw(sel);});
 document.querySelectorAll("#lev button").forEach(b=>b.onclick=()=>{L=b.dataset.l;document.querySelectorAll("#lev button").forEach(x=>x.classList.remove("on"));b.classList.add("on");render();draw(sel);});
 render();draw(sel,selLev);
 let _rt; window.addEventListener('resize',()=>{clearTimeout(_rt);_rt=setTimeout(()=>draw(sel,selLev),150);});
</script>
<script type="module" src="./anim.js"></script>
</body></html>"""
open("web/board.html", "w", encoding="utf-8").write(HTML.replace("__DATA__", DATA))
print("wrote web/board.html")
