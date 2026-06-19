"""
gen_scans.py — build web/scans.html: a browsable archive of EVERY daily spike-hunter
report from the brain (research/scans/*.md), with a search bar + date picker.

Open the quant app -> "Daily Scan" tab -> pick or search any day -> read that day's
full report, rendered. Reuses the SAME brain-clone plumbing as gen_stocks.py so the
paper-bot CI rebuilds it every cycle (never stale).

    python web/gen_scans.py   ->  web/scans.html

Brain path resolution: $SECOND_BRAIN env -> D:/second-brain -> ../second-brain -> ./second-brain
"""
import json, os, re, html as _html
from pathlib import Path

try:
    import markdown as _md
except ImportError:
    _md = None


def find_brain():
    cands = [os.environ.get("SECOND_BRAIN"), r"D:/second-brain", "../second-brain", "./second-brain"]
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

    page = TEMPLATE.replace("__DATA__", DATA).replace("__COUNT__", str(len(scans)))
    Path("web/scans.html").write_text(page, encoding="utf-8")
    print(f"wrote web/scans.html ({len(scans)} reports: {', '.join(s['date']+'/'+s['kind'] for s in scans[:6])}{' …' if len(scans)>6 else ''})")


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daily Scan — Spike Hunter reports</title>
<link rel="stylesheet" href="./style.css">
<style>
 .scancols{display:flex;gap:18px;align-items:flex-start}
 .side{flex:0 0 300px;min-width:260px;position:sticky;top:18px}
 .search{width:100%;font-family:var(--mono);font-size:13px;color:var(--txt);background:var(--ink2);
   border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:12px;outline:none}
 .search:focus{border-color:var(--accent)}
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
 @media(max-width:680px){.scancols{flex-direction:column}.side{position:static;flex-basis:auto;width:100%}.daylist{max-height:none}}
</style></head><body>
<div class="wrap">
<p class="eyebrow">Equities · Spike Hunter</p>
<h1>Daily <span class="thin">Scan Archive</span></h1>
<p class="lede">Every daily spike-hunter report, straight from the brain ledger — <b>__COUNT__</b> on file. Search any day, pick a date, read the full report (market state · positions · watchlist · proposed adds · alerts). Not financial advice.</p>
<div id="nav"></div>
<script src="./nav.js"></script>
<div class="scancols">
 <div class="side">
  <input id="q" class="search" placeholder="🔎 search date or text (e.g. 2026-06-19, KTOS, reserve)…" autocomplete="off">
  <div class="daylist" id="list"></div>
 </div>
 <div class="viewer card">
  <div class="vhead"><span class="kind" id="vk"></span><span class="vd" id="vd"></span></div>
  <div class="scan-body" id="body"></div>
 </div>
</div>
<footer>Built from the brain ledger (research/scans) · paper only · not financial advice · Lemonef/Trade</footer>
</div>
<script>
 const DATA=__DATA__; let sel=DATA[0]||null, filt=DATA;
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
 show(sel);
</script>
<script type="module" src="./anim.js"></script>
</body></html>"""


if __name__ == "__main__":
    main()
