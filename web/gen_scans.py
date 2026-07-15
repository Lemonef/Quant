"""
gen_scans.py — build web/scans.html: a browsable archive of EVERY daily spike-hunter
report from the brain (research/scans/*.md), with a search bar + date picker.

Open the quant app -> "Daily Scan" tab -> pick or search any day -> read that day's
full report, rendered. Reuses the SAME brain-clone plumbing as gen_stocks.py so the
paper-bot CI rebuilds it every cycle (never stale).

    python web/gen_scans.py   ->  web/scans.html

Brain path resolution: $SECOND_BRAIN env -> ~/SecondBrain -> D:/second-brain -> ../second-brain -> ./second-brain
"""
import json, os, re, datetime, html as _html
from pathlib import Path

try:
    import markdown as _md
except ImportError:
    _md = None


def find_brain():
    cands = [os.environ.get("SECOND_BRAIN"), os.path.expanduser("~/SecondBrain"), r"D:/second-brain", "../second-brain", "./second-brain"]
    for c in cands:
        if c and (Path(c) / "research" / "scans").is_dir():
            return Path(c)
    return None


DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def kind_of(name):
    n = name.lower()
    if n.startswith("spike-scan"):   return ("Daily", "kind-daily")
    if n.startswith("weekly"):       return ("Weekly", "kind-weekly")
    if n.startswith("sweep"):        return ("Sweep", "kind-sweep")
    if n.startswith("dryrun"):       return ("Dry-run", "kind-dry")
    return ("Scan", "kind-other")


def render_md(text):
    """Markdown -> HTML. Prefer the `markdown` lib (good GFM tables); fall back to a
    minimal renderer so the page still builds if the dep is missing in CI."""
    if _md is not None:
        return _md.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    return _mini_md(text)


def _mini_md(text):
    """Tiny fallback renderer: headings, bold/italic/code, hr, blockquote, pipe-tables, lists, paragraphs."""
    def inline(s):
        s = _html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    lines = text.splitlines()
    out, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lvl = len(m.group(1)); out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>"); i += 1; continue
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", ln):
            out.append("<hr>"); i += 1; continue
        if ln.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(inline(re.sub(r"^\s*>\s?", "", lines[i]))); i += 1
            out.append("<blockquote>" + "<br>".join(buf) + "</blockquote>"); continue
        if "|" in ln and i + 1 < n and re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", lines[i + 1]):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2; body = []
            while i < n and "|" in lines[i] and lines[i].strip():
                body.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            t = ["<table><thead><tr>"] + [f"<th>{inline(h)}</th>" for h in head] + ["</tr></thead><tbody>"]
            for r in body:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table>"); out.append("".join(t)); continue
        if re.match(r"^\s*[-*]\s+", ln):
            out.append("<ul>")
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                out.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "", lines[i])) + "</li>"); i += 1
            out.append("</ul>"); continue
        buf = []
        while i < n and lines[i].strip() and not re.match(r"^(#{1,6}\s|>|\s*[-*]\s)", lines[i]) and "|" not in lines[i]:
            buf.append(inline(lines[i])); i += 1
        out.append("<p>" + "<br>".join(buf) + "</p>")
    return "\n".join(out)


def summarise(text):
    """One-line summary for the picker list: prefer the **Read:** call line, else the first prose paragraph."""
    m = re.search(r"\*\*Read:\*\*\s*(.+)", text)
    if m:
        s = m.group(1)
    else:
        s = ""
        for ln in text.splitlines():
            t = ln.strip()
            if not t or t.startswith("#") or t.startswith(">") or t.startswith("|") or t.startswith("_") or t.startswith("-"):
                continue
            s = t; break
    s = re.sub(r"[*`#>_]", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:160] + "…") if len(s) > 160 else s


def title_of(text, fallback):
    for ln in text.splitlines():
        m = re.match(r"^#\s+(.*)$", ln)
        if m:
            return re.sub(r"[*`]", "", m.group(1)).strip()
    return fallback


def _write_health(component, info):
    """Merge this component's status into web/health.json (shared heartbeat)."""
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
        raise SystemExit("research/scans not found — set $SECOND_BRAIN or place brain at D:/second-brain")
    scans = []
    for p in sorted((brain / "research" / "scans").glob("*.md")):
        dm = DATE_RE.search(p.name)
        if not dm:
            continue
        text = p.read_text(encoding="utf-8")
        kind, kcls = kind_of(p.name)
        scans.append({
            "date": dm.group(1),
            "kind": kind, "kcls": kcls,
            "file": p.name,
            "title": title_of(text, p.stem),
            "summary": summarise(text),
            "html": render_md(text),
            "search": (p.name + " " + text).lower(),
        })
    # newest first; if same date, Daily before Weekly/etc.
    scans.sort(key=lambda s: (s["date"], s["kind"] != "Daily"), reverse=True)
    DATA = json.dumps(scans, ensure_ascii=False)
    build_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    newest = scans[0]["date"] if scans else "no-data"
    oldest = scans[-1]["date"] if scans else "no-data"

    page = (TEMPLATE.replace("__DATA__", DATA).replace("__COUNT__", str(len(scans)))
                    .replace("__NEWEST__", newest).replace("__OLDEST__", oldest).replace("__BUILT__", build_utc))
    Path("web/scans.html").write_text(page, encoding="utf-8")
    _write_health("scans", {"built_utc": build_utc, "newest_report": newest, "n_reports": len(scans),
                            "ok": bool(scans)})
    print(f"wrote web/scans.html ({len(scans)} reports; newest {newest})")


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daily Scan — Spike Hunter reports</title>
<link rel="stylesheet" href="./style.css">
<style>
 .scancols{display:flex;gap:18px;align-items:flex-start}
 .side{flex:0 0 300px;min-width:260px;position:sticky;top:18px}
 .searchrow{display:flex;gap:7px;align-items:center;margin-bottom:12px}
 .search{flex:1;min-width:0;font-family:var(--mono);font-size:13px;color:var(--txt);background:var(--ink2);
   border:1px solid var(--line);border-radius:10px;padding:10px 12px;outline:none}
 .search:focus{border-color:var(--accent)}
 .calbtn{flex:0 0 auto;font-size:16px;line-height:1;cursor:pointer;background:var(--ink2);border:1px solid var(--line);
   border-radius:10px;padding:8px 10px;transition:.15s}
 .calbtn:hover{border-color:var(--accent);transform:translateY(-1px)}
 .dp{flex:0 0 auto;width:38px;opacity:0;position:absolute;right:0;pointer-events:none;color-scheme:dark}
 .daylist{max-height:72vh;overflow:auto;padding-right:4px}
 .day{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:11px;
   padding:10px 12px;margin-bottom:9px;cursor:pointer;transition:.15s}
 .day:hover{border-color:var(--line2);transform:translateY(-1px)}
 .day.sel{border-color:var(--accent)}
 .day .dh{display:flex;align-items:center;gap:8px}
 .day .dt{font-family:var(--mono);font-weight:700;font-size:13.5px}
 .day .sm{font-size:11.5px;color:var(--dim);margin-top:4px;line-height:1.45}
 .kind{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
   padding:2px 7px;border-radius:5px;border:1px solid var(--line2);color:var(--mut)}
 .kind-daily{background:rgba(124,196,255,.13);color:var(--accent);border-color:rgba(124,196,255,.3)}
 .kind-weekly{background:rgba(183,156,255,.13);color:var(--accent2);border-color:rgba(183,156,255,.3)}
 .kind-sweep{background:rgba(244,184,96,.13);color:var(--warn);border-color:rgba(244,184,96,.3)}
 .kind-dry,.kind-other{background:var(--ink2)}
 .viewer{flex:1;min-width:0}
 .vhead{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:6px}
 .vhead .vd{font-family:var(--mono);font-size:13px;color:var(--amber);font-weight:600}
 .scan-body{font-size:14px;line-height:1.62}
 .scan-body h1{font-family:var(--serif);font-size:27px;margin:2px 0 12px}
 .scan-body h2{font-size:20px;margin:26px 0 10px;border-top:1px solid var(--line);padding-top:16px}
 .scan-body h3{font-family:var(--mono);font-size:13px;letter-spacing:.04em;color:var(--accent);text-transform:uppercase;margin:18px 0 8px}
 .scan-body table{margin:12px 0}
 .scan-body blockquote{border-left:3px solid var(--amber);background:rgba(232,161,75,.06);
   margin:12px 0;padding:10px 16px;border-radius:0 10px 10px 0;color:var(--txt)}
 .scan-body code{font-size:12px}
 .scan-body hr{border:none;border-top:1px solid var(--line);margin:20px 0}
 .empty{color:var(--dim);font-family:var(--mono);font-size:13px;padding:30px 0}
 .freshbar{font-family:var(--mono);font-size:12.5px;font-weight:600;border-radius:10px;padding:9px 14px;margin:0 0 18px;border:1px solid var(--line);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
 .freshbar.ok{background:rgba(39,211,138,.08);border-color:rgba(39,211,138,.35);color:var(--up)}
 .freshbar.stale{background:rgba(255,90,106,.12);border-color:var(--dn);color:var(--dn)}
 .freshbar .sub{color:var(--mut);font-weight:500}
 @media(max-width:680px){.scancols{flex-direction:column}.side{position:static;flex-basis:auto;width:100%}.daylist{max-height:none}}
</style></head><body>
<div class="wrap">
<p class="eyebrow">Equities · Spike Hunter</p>
<h1>Daily <span class="thin">Scan Archive</span></h1>
<p class="lede">Every daily spike-hunter report, straight from the brain ledger — <b>__COUNT__</b> on file. Search any day, pick a date, read the full report (market state · positions · watchlist · proposed adds · alerts). Not financial advice.</p>
<div id="nav"></div>
<script src="./nav.js"></script>
<div id="fresh" class="freshbar"></div>
<div class="scancols">
 <div class="side">
  <div class="searchrow">
   <input id="q" class="search" placeholder="🔎 search date or text…" autocomplete="off">
   <button id="cal" class="calbtn" title="Pick a date" aria-label="Pick a date">📅</button>
   <input id="dp" type="date" class="dp" min="__OLDEST__" max="__NEWEST__" title="Jump to date">
  </div>
  <div class="daylist" id="list"></div>
 </div>
 <div class="viewer card">
  <div class="vhead"><span class="kind" id="vk"></span><span class="vd" id="vd"></span></div>
  <div class="scan-body" id="body"></div>
 </div>
</div>
<footer>Built from the brain ledger (research/scans) · paper only · not financial advice · Lemonef/Quant</footer>
</div>
<script>
 const DATA=__DATA__, NEWEST="__NEWEST__", BUILT="__BUILT__"; let sel=DATA[0]||null, filt=DATA;
 (function(){const fb=document.getElementById("fresh");if(!fb)return;
  const d=new Date(NEWEST+"T00:00:00Z"),now=new Date();
  const days=isNaN(d)?999:Math.floor((now-d)/864e5);
  const stale=days>3;   // a daily report should never be >3 days old
  fb.className="freshbar "+(stale?"stale":"ok");
  fb.innerHTML=(stale?"⚠️ STALE — newest report "+days+" days old (the daily routine may have stopped)":"✓ Fresh — newest report "+NEWEST)+
    ' <span class="sub">· newest '+NEWEST+' · page built '+BUILT+'</span>';
 })();
 function show(s){sel=s;
  document.getElementById("vk").textContent=s?s.kind:"";
  document.getElementById("vk").className="kind "+(s?s.kcls:"");
  document.getElementById("vd").textContent=s?(s.date+"  ·  "+s.file):"";
  document.getElementById("body").innerHTML=s?s.html:'<div class="empty">No report selected.</div>';
  paint();
 }
 function paint(){const L=document.getElementById("list");L.innerHTML="";
  if(!filt.length){L.innerHTML='<div class="empty">No match.</div>';return;}
  filt.forEach(s=>{const d=document.createElement("div");d.className="day"+(sel===s?" sel":"");
   d.innerHTML=`<div class="dh"><span class="kind ${s.kcls}">${s.kind}</span><span class="dt">${s.date}</span></div>`+
               `<div class="sm">${s.summary||""}</div>`;
   d.onclick=()=>show(s);L.appendChild(d);});
 }
 document.getElementById("q").addEventListener("input",e=>{
  const q=e.target.value.trim().toLowerCase();
  filt=q?DATA.filter(s=>s.search.includes(q)):DATA;
  if(filt.length&&!filt.includes(sel))show(filt[0]);else paint();
 });
 // calendar date-picker: click 📅 -> native calendar -> jump to that day's report (or nearest earlier)
 const dp=document.getElementById("dp"), cal=document.getElementById("cal");
 cal.addEventListener("click",()=>{ if(dp.showPicker){try{dp.showPicker();return}catch(e){}} dp.style.opacity=1;dp.style.pointerEvents="auto";dp.focus(); });
 dp.addEventListener("change",()=>{ const v=dp.value; if(!v)return;
  const hit=DATA.find(s=>s.date===v)||DATA.find(s=>s.date<=v)||DATA[DATA.length-1];
  document.getElementById("q").value=""; filt=DATA; show(hit);
  const el=document.querySelector(".day.sel"); if(el)el.scrollIntoView({block:"nearest"});
 });
 show(sel);
</script>
<script type="module" src="./anim.js"></script>
</body></html>"""


if __name__ == "__main__":
    main()
