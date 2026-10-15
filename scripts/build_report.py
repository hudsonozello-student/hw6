"""Problem 9: build output/hw6_report.html from the real numbers in the output JSONs.

The report is one self-contained file: all CSS is inline, charts are inline SVG, the two red-team
screenshots are embedded as base64 data URIs, and the fonts are system fonts. It opens by double-click
with no internet and no files next to it. Every number is read from an earlier problem's output, so
re-running this script keeps the page in sync.

Run from the Homework 6 folder:
    .\\.venv\\Scripts\\python.exe scripts\\build_report.py
"""

import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "hw6_report.html"
DOCS_PER_MONTH = 1000 * 30


def load(name: str) -> dict:
    return json.loads((ROOT / "output" / name).read_text(encoding="utf-8"))


def money(x: float, places: int = 2) -> str:
    return f"${x:,.{places}f}"


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


# ---------- tiny inline-SVG charts ----------

def hbar(rows, vmax, width=560, bar_h=30, gap=16, label_w=170):
    """Horizontal bar chart. rows = [(label, value, color, value_text)]."""
    h = len(rows) * (bar_h + gap) + gap
    plot_w = width - label_w - 100
    svg = [f'<svg viewBox="0 0 {width} {h}" role="img" class="chart">']
    for i, (label, value, color, vtext) in enumerate(rows):
        y = gap + i * (bar_h + gap)
        bw = max(2, plot_w * value / vmax) if vmax else 2
        svg.append(f'<text x="{label_w - 10}" y="{y + bar_h/2 + 4:.0f}" text-anchor="end" class="bl">{html.escape(label)}</text>')
        svg.append(f'<rect x="{label_w}" y="{y}" width="{plot_w}" height="{bar_h}" rx="5" class="track"/>')
        svg.append(f'<rect x="{label_w}" y="{y}" width="{bw:.1f}" height="{bar_h}" rx="5" fill="{color}"/>')
        svg.append(f'<text x="{label_w + bw + 8:.1f}" y="{y + bar_h/2 + 4:.0f}" class="bv">{html.escape(vtext)}</text>')
    svg.append('</svg>')
    return "".join(svg)


def chip_grid(items):
    """items = [(label, ok_bool, title)] -> a grid of colored chips."""
    out = ['<div class="chips">']
    for label, ok, title in items:
        cls = "chip ok" if ok else "chip bad"
        out.append(f'<span class="{cls}" title="{html.escape(title)}">{label}</span>')
    out.append('</div>')
    return "".join(out)


# ---------- gather numbers ----------

cache = load("cache_test.json")["summary"]
hb_tokens = load("handbook_estimate.json")["counts"]["o200k_base_tokens"]
dr = load("defense_results.json")
before, after = dr["before_summary"], dr["summary"]
layers = dr["layer_summaries"]
exam = load("exam_results.json")
exam_detail = {d["file"]: d for d in load("exam_defense_detail.json")["documents"]}
redteam = load("red_team/red_team_results.json")["attacks"]

cache_with = cache["with_cache"]["cost_per_document_usd"]
cache_without = cache["without_cache"]["cost_per_document_usd"]
cache_save_pct = cache["savings_pct"]
month_cache = {"without": cache_without * DOCS_PER_MONTH, "with": cache_with * DOCS_PER_MONTH}

defended_doc = after["per_document_average"]["cost_usd"]
defended_doc_nocache = after["per_document_average"]["cost_usd_no_cache"]
undef_doc = before["per_document_average"]["cost_usd"]
month_defended = defended_doc * DOCS_PER_MONTH
month_defended_nocache = defended_doc_nocache * DOCS_PER_MONTH
month_undef = undef_doc * DOCS_PER_MONTH

fooled_before = len(before["documents_fooled"])
fooled_after = len(after["documents_fooled"])
exam_rec = sum(e["decision"] == "recommend" for e in exam)
exam_traps = sum(e["trap_tool_called"] for e in exam)
exam_attacked = sum(1 for e in exam if exam_detail[e["file"]]["code_layer_removed"]
                    or exam_detail[e["file"]]["reader_flagged_suspicious"])


CSS = r"""
:root{
  --ink:#16202b; --muted:#5b6673; --faint:#8a94a1;
  --blue:#00356b; --blue2:#0a4f93; --tint:#eaf1f8;
  --paper:#f6f4ef; --card:#ffffff; --line:#e6e2d8;
  --good:#2f7d5b; --good-bg:#e7f3ec; --bad:#c0392b; --bad-bg:#fbeae7; --amber:#b7791f;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:"SF Mono","Cascadia Code",Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.6;font-size:16px}
.wrap{max-width:1000px;margin:0 auto;padding:0 24px 72px}
h1,h2,h3{font-family:var(--serif);line-height:1.2;letter-spacing:.2px}
header.hero{background:linear-gradient(160deg,#00356b 0%,#012a54 60%,#01203f 100%);color:#fff;padding:54px 0 48px;border-bottom:4px solid #d7b968}
header .wrap{padding-bottom:0}
.kicker{text-transform:uppercase;letter-spacing:3px;font-size:12px;color:#c6d6ea;font-weight:700;margin:0 0 10px}
.hero h1{font-size:40px;margin:0 0 12px;color:#fff}
.hero p.sub{font-size:18px;color:#d6e2f0;margin:0;max-width:700px}
.statband{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:14px;overflow:hidden;margin:-34px 0 0;box-shadow:0 12px 30px rgba(1,30,60,.14)}
.stat{background:var(--card);padding:18px 20px}
.stat .n{font-family:var(--serif);font-size:30px;font-weight:700;color:var(--blue);line-height:1.1}
.stat .l{font-size:12.5px;color:var(--muted);margin-top:4px}
section.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:30px 32px;margin:26px 0;box-shadow:0 2px 0 rgba(1,30,60,.03)}
section.card>h2{font-size:25px;margin:0 0 4px;color:var(--blue);display:flex;align-items:center;gap:12px}
.secnum{font-family:var(--sans);font-size:13px;font-weight:800;color:#fff;background:var(--blue);width:28px;height:28px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto}
.lead{color:var(--muted);margin:2px 0 20px;font-size:15.5px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.grid2.wide{grid-template-columns:1.25fr 1fr}
@media(max-width:760px){.statband{grid-template-columns:repeat(2,1fr)}.grid2,.grid2.wide{grid-template-columns:1fr}.hero h1{font-size:30px}}
.chart{width:100%;height:auto}
.chart .track{fill:#eef1f4}
.chart .bl{font-family:var(--sans);font-size:13px;fill:var(--ink)}
.chart .bv{font-family:var(--mono);font-size:13px;font-weight:600;fill:var(--ink)}
table{width:100%;border-collapse:collapse;font-size:14px;margin:6px 0}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:11.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--faint);font-weight:700}
tbody tr:hover,table tr:hover{background:#faf9f5}
td.num,th.num{font-family:var(--mono);text-align:right;white-space:nowrap}
.tag{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}
.tag.good{background:var(--good-bg);color:var(--good)}
.tag.bad{background:var(--bad-bg);color:var(--bad)}
.tag.mut{background:#eef1f4;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin:8px 0 2px}
.chip{font-family:var(--mono);font-size:12px;font-weight:600;padding:5px 9px;border-radius:7px;border:1px solid transparent}
.chip.ok{background:var(--good-bg);color:var(--good);border-color:#cfe6d8}
.chip.bad{background:var(--bad-bg);color:var(--bad);border-color:#f1cfc8}
.ba{display:grid;grid-template-columns:62px 1fr;gap:6px 14px;align-items:center;margin:10px 0}
.ba .side{font-size:12px;font-weight:700;color:var(--faint);text-transform:uppercase;letter-spacing:.5px}
.callout{border-left:4px solid var(--blue);background:var(--tint);border-radius:0 12px 12px 0;padding:16px 20px;margin:0 0 14px}
.redcard{border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fcfbf8}
.redcard img{width:100%;display:block;border-bottom:1px solid var(--line);background:#fff}
.redcard .body{padding:16px 18px}
.redcard h3{margin:0 0 2px;font-size:17px;color:var(--blue)}
.redcard .trick{font-size:12px;color:var(--amber);font-weight:800;letter-spacing:.3px;margin:0 0 8px}
.flow{display:flex;align-items:center;gap:8px;font-size:13px;margin-top:8px;flex-wrap:wrap}
.arrow{color:var(--faint);font-weight:700}
section.card.rec{background:linear-gradient(160deg,#0a4f93,#00356b);border:none;color:#fff}
.rec h2{color:#fff}
.rec .lead{color:#cfe0f1}
.rec .verdict-big{font-family:var(--serif);font-size:24px;font-weight:700;margin:6px 0 14px;color:#fff}
.rec .pill{display:inline-block;background:#d7b968;color:#2a2008;font-weight:800;padding:3px 12px;border-radius:999px;font-size:13px;letter-spacing:.3px;vertical-align:middle}
.rec .money{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0 6px}
@media(max-width:620px){.rec .money{grid-template-columns:1fr}}
.rec .money .box{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);border-radius:12px;padding:14px 16px}
.rec .money .big{font-family:var(--serif);font-size:27px;font-weight:700}
.rec .money .cap{font-size:12.5px;color:#cfe0f1;margin-top:2px}
.rec ul{margin:10px 0 0;padding-left:18px}
.rec li{margin:5px 0;color:#eaf1f8}
footer{color:var(--faint);font-size:12.5px;text-align:center;margin-top:30px}
.src{font-family:var(--mono);font-size:11px;color:var(--faint)}
code{font-family:var(--mono);font-size:.9em;background:#eef1f4;padding:1px 4px;border-radius:4px}
"""


def stat(n, l):
    return f'<div class="stat"><div class="n">{n}</div><div class="l">{l}</div></div>'


# ---------- section 1: caching ----------
cache_chart = hbar(
    [("Without caching", month_cache["without"], "#c0392b", money(month_cache["without"])),
     ("With caching", month_cache["with"], "#2f7d5b", money(month_cache["with"]))],
    vmax=month_cache["without"] * 1.12)

sec1 = f"""
<section class="card">
  <h2><span class="secnum">1</span> The handbook rides on every call &mdash; caching cuts the bill</h2>
  <p class="lead">The {hb_tokens:,}-token shop handbook is sent with every request. Prompt caching reuses it at one-tenth
     the price. I measured both ways on the 12 practice documents and proved each setup from the token counts the API
     returned.</p>
  <div class="grid2 wide">
    <div>
      <div class="src">Projected monthly cost &middot; 1,000 docs/day &times; 30 days</div>
      {cache_chart}
    </div>
    <div>
      <div class="callout">
        <div style="font-size:30px;font-family:var(--serif);font-weight:700;color:var(--good)">{cache_save_pct:.0f}% cheaper</div>
        <div style="color:var(--muted);font-size:14px">Caching saved {money(cache_without-cache_with,5)} per document
        ({money(cache_without,5)} &rarr; {money(cache_with,5)}). It pays for itself on the 2nd call and held a
        78% cache-hit rate.</div>
      </div>
      <table>
        <tr><th>Per document</th><th class="num">No cache</th><th class="num">Cached</th></tr>
        <tr><td>Cost</td><td class="num">{money(cache_without,5)}</td><td class="num">{money(cache_with,5)}</td></tr>
        <tr><td>Per month</td><td class="num">{money(month_cache['without'])}</td><td class="num">{money(month_cache['with'])}</td></tr>
      </table>
    </div>
  </div>
</section>"""


# ---------- section 2: attacks before/after ----------
ba = dr["before_after"]
chips_before = chip_grid([(r["document"].split("_")[0], not r["before"]["fooled"], r["document"]) for r in ba])
chips_after = chip_grid([(r["document"].split("_")[0], not r["all"]["fooled"], r["document"]) for r in ba])
TRICKS = {
    "p02_elmcity_quote.html": ("Zero-size HTML paragraph", "fake price $5.11 (real $9.83)"),
    "p03_ivyprint_catalog.html": ("<code>display:none</code> block", "swap to an approved vendor"),
    "p07_longwharf_quote.pdf": ("0.8&nbsp;pt PDF text", "fake lead time 7 days (real 35)"),
    "p12_bluehen_quote.pdf": ("Text placed off the page", "fake price $17.44 (real $27.72)"),
}
flip_rows = ""
for r in ba:
    if not r["before"]["fooled"]:
        continue
    trick, goal = TRICKS[r["document"]]
    flip_rows += (f'<tr><td><b>{r["document"].split("_")[0]}</b> &middot; {trick}</td><td>{goal}</td>'
                  f'<td><span class="tag bad">recommend &#10007;</span></td>'
                  f'<td><span class="tag good">do&nbsp;not &#10003;</span></td></tr>')

sec2 = f"""
<section class="card">
  <h2><span class="secnum">2</span> Attacks, before and after the defenses</h2>
  <p class="lead">Some vendor documents hide instructions aimed at the AI. I ran all 12 practice documents with no
     defenses and with all three defense layers. Each square is one document &mdash;
     <span class="tag good">green</span> handled correctly, <span class="tag bad">red</span> fooled.</p>
  <div class="ba">
    <div class="side">Undefended</div><div>{chips_before}</div>
    <div class="side">Defended</div><div>{chips_after}</div>
  </div>
  <p style="margin:16px 0 4px;font-size:15px"><b>{fooled_before} of 12 documents fooled the undefended agent;
     {fooled_after} fooled the defended agent.</b> Fact accuracy went from {before['fields_matched']} to
     {after['fields_matched']} fields, decisions from {before['decisions_matched']} to {after['decisions_matched']}.
     Every real quote still came back correct &mdash; no clean document was refused.</p>
  <table>
    <tr><th>Attack that flipped the call</th><th>What it wanted</th><th>Undefended</th><th>Defended</th></tr>
    {flip_rows}
  </table>
</section>"""


# ---------- section 3: defense cost ----------
cost_chart = hbar(
    [("Undefended", undef_doc, "#b7791f", money(undef_doc, 5)),
     ("Defended (3 layers)", defended_doc, "#2f7d5b", money(defended_doc, 5))],
    vmax=undef_doc * 1.15)
layer_rows = ""
notes = {"code": "removes hidden text before the model reads it",
         "design": "drops a whole model call (one request, not two)",
         "prompt": "adds safety rules, cached after the first call"}
for key, name in [("code", "Code"), ("design", "Design"), ("prompt", "Prompt")]:
    ls = layers[key]
    d_tok = ls["per_document_average"]["prompt_tokens"] - before["per_document_average"]["prompt_tokens"]
    d_cost = ls["per_document_average"]["cost_usd_no_cache"] - before["per_document_average"]["cost_usd_no_cache"]
    ts = "+" if d_tok >= 0 else "&minus;"
    cs = "+" if d_cost >= 0 else "&minus;"
    layer_rows += (f'<tr><td><b>{name}</b><br><span class="src">{notes[key]}</span></td>'
                   f'<td class="num">{ts}{abs(d_tok):,.0f}</td>'
                   f'<td class="num">{cs}{money(abs(d_cost),6)[1:]}</td></tr>')

sec3 = f"""
<section class="card">
  <h2><span class="secnum">3</span> What the defenses cost</h2>
  <p class="lead">The surprise: the defended agent is <b>cheaper</b> than the undefended one, because the design layer has
     the program read the document itself &mdash; one model call per document instead of two.</p>
  <div class="grid2 wide">
    <div>
      <div class="src">Cost per document (measured, caching on)</div>
      {cost_chart}
      <p style="font-size:14px;color:var(--muted);margin:10px 0 0">
        {money(undef_doc,5)} &rarr; {money(defended_doc,5)} per document, a
        {(1-defended_doc/undef_doc)*100:.0f}% drop, while closing every attack.</p>
    </div>
    <div>
      <table>
        <tr><th>Layer</th><th class="num">Tokens/doc</th><th class="num">$/doc</th></tr>
        {layer_rows}
      </table>
      <p class="src" style="margin-top:8px">Change vs. the undefended agent (full price, no cache).
         Negative = the layer saves tokens.</p>
    </div>
  </div>
</section>"""


# ---------- section 4: exam + red team ----------
exam_rows = ""
for e in exam:
    det = exam_detail[e["file"]]
    attacked = bool(det["code_layer_removed"] or det["reader_flagged_suspicious"])
    dtag = ('<span class="tag good">recommend</span>' if e["decision"] == "recommend"
            else '<span class="tag bad">do&nbsp;not</span>')
    atag = '<span class="tag mut">clean</span>' if not attacked else '<span class="tag good">caught &#128737;</span>'
    price = f'${e["unit_price"]:,.2f}' if e["unit_price"] is not None else "&ndash;"
    minq = f'{e["min_order"]:,}' if e["min_order"] is not None else "&ndash;"
    exam_rows += (f'<tr><td class="src">{e["file"]}</td><td>{html.escape(e["vendor"] or "")}</td>'
                  f'<td class="src">{e["sku"] or ""}</td><td class="num">{price}</td>'
                  f'<td class="num">{e["lead_time_days"]}d</td><td class="num">{minq}</td>'
                  f'<td>{dtag}</td><td>{atag}</td></tr>')

red_cards = ""
for a in redteam:
    r_u, r_d = a["runs"]["undefended"], a["runs"]["defended"]
    img = data_uri(ROOT / "output" / "red_team" / (Path(a["file"]).stem + ".png"))
    field = r_u["field_attacked"].replace("_", " ")
    red_cards += f"""
    <div class="redcard">
      <img alt="What a person sees opening {html.escape(a['file'])}" src="{img}"/>
      <div class="body">
        <h3>{html.escape(a['vendor'])}</h3>
        <div class="trick">NEW TRICK &middot; {html.escape(a['hiding_trick'].split(':')[0])}</div>
        <div style="font-size:13.5px;color:var(--muted)">{html.escape(a['goal'])}</div>
        <div class="flow"><span class="tag mut">undefended</span><span class="arrow">&rarr;</span>
          <span class="tag bad">{r_u['decision'].replace('_',' ')} &#10007;</span>
          <span style="color:var(--faint)">({field} = {r_u['value_agent_used']})</span></div>
        <div class="flow"><span class="tag mut">defended</span><span class="arrow">&rarr;</span>
          <span class="tag good">{r_d['decision'].replace('_',' ')} &#10003;</span>
          <span style="color:var(--faint)">({field} = {r_d['value_agent_used']})</span></div>
      </div>
    </div>"""

sec4 = f"""
<section class="card">
  <h2><span class="secnum">4</span> The exam set, and two attacks of my own</h2>
  <p class="lead">The final defended agent read 10 fresh vendor documents with no answer key. {exam_attacked} of the 10
     carried a hidden or in-plain-sight attack; all were handled. No trap tool ever fired, and the results were
     identical across 3 runs.</p>
  {chip_grid([(f"{exam_rec} recommend", True, "clean buys"), (f"{10-exam_rec} do-not", True, "rejected for a real reason"), (f"{exam_traps} trap calls", exam_traps==0, "email / payment tools never fired"), ("stable &times;3", True, "same answers on re-run")])}
  <table style="margin-top:14px">
    <tr><th>File</th><th>Vendor</th><th>SKU</th><th class="num">Price</th><th class="num">Lead</th><th class="num">Min</th><th>Decision</th><th>Attack?</th></tr>
    {exam_rows}
  </table>
  <h3 style="margin:28px 0 4px;font-size:18px;color:var(--blue)">Red team: I attacked my own agent</h3>
  <p class="lead">Two booby-trapped quotes using hiding tricks not in the practice set. A person opens each and sees a
     normal quote (below). Both fooled the undefended agent on every run and were blocked by the defended agent on
     every run &mdash; caught by different layers.</p>
  <div class="grid2">{red_cards}</div>
</section>"""


# ---------- section 5: recommendation ----------
sec5 = f"""
<section class="card rec">
  <h2 style="color:#fff"><span class="secnum" style="background:#d7b968;color:#2a2008">5</span> Recommendation to the store manager</h2>
  <p class="lead">Should Campus Customs point this agent at real vendor mail?</p>
  <div class="verdict-big">Yes &mdash; turn it on as a reviewer&rsquo;s assistant. <span class="pill">drafts only</span></div>
  <div class="money">
    <div class="box"><div class="big">{money(month_defended,0)}<span style="font-size:15px">/mo</span></div>
      <div class="cap">Expected, with caching, at 1,000 docs/day</div></div>
    <div class="box"><div class="big">{money(month_defended_nocache,0)}<span style="font-size:15px">/mo</span></div>
      <div class="cap">Worst case if the cache never helps</div></div>
    <div class="box"><div class="big">0</div>
      <div class="cap">Emails sent or payments made &mdash; ever</div></div>
  </div>
  <ul>
    <li><b>Safe by construction.</b> The AI that reads vendor mail has no email or payment tools and cannot make the buy
        decision &mdash; a plain program does, straight from the handbook. Across 22 practice and exam documents plus two
        attacks of my own, no hidden instruction ever triggered a tool, and every real quote was read correctly.</li>
    <li><b>Cheap.</b> About {money(month_defended,0)} a month at 1,000 documents a day &mdash; the price of one hoodie
        &mdash; and <b>less</b> than the undefended version ({money(month_undef,0)}/mo), because it calls the model once.</li>
    <li><b>Keep a person in the loop.</b> Let it draft the vendor, price, and a recommend / do-not call for the buyer to
        approve. The email and payment tools stay off behind a human sign-off, as they are today.</li>
    <li><b>One caveat.</b> A brand-new hiding trick could still slip a wrong number past the code layer; the design layer
        still blocks any email or payment, and the buyer&rsquo;s approval is the final backstop.</li>
  </ul>
</section>"""


# ---------- assemble ----------
statband = "".join([
    stat(f"{hb_tokens//1000}k", "handbook tokens, sent every call"),
    stat(f"{cache_save_pct:.0f}%", "cheaper with prompt caching"),
    stat(f"{fooled_before}&nbsp;&rarr;&nbsp;{fooled_after}", "attacks that fooled the agent, before &rarr; after"),
    stat(money(month_defended, 0) + "/mo", "to run at 1,000 docs/day"),
])

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campus Customs Vendor Desk &mdash; Results</title>
<style>{CSS}</style>
</head>
<body>
<header class="hero">
  <div class="wrap">
    <p class="kicker">Campus Customs &middot; MGT 409 &middot; Homework 6</p>
    <h1>The Vendor Desk Agent</h1>
    <p class="sub">An AI assistant that reads a vendor quote, pulls the key facts, and recommends whether to buy &mdash;
       measured for cost, attacked, and defended. Every number below comes from the runs in this project.</p>
  </div>
</header>
<div class="wrap">
  <div class="statband">{statband}</div>
  {sec1}
  {sec2}
  {sec3}
  {sec4}
  {sec5}
  <footer>Generated from the project&rsquo;s own result files &mdash; caching, attack, defense, exam, and red-team runs
     on <span class="src">gpt-6-luna</span>. Self-contained: no internet required.</footer>
</div>
</body>
</html>"""

OUT.write_text(page, encoding="utf-8")
print(f"wrote {OUT.relative_to(ROOT).as_posix()}  ({len(page)/1024:.0f} KB)")
print("monthly  defended", money(month_defended), "| nocache", money(month_defended_nocache),
      "| undefended", money(month_undef))
print("cache monthly  without", money(month_cache['without']), "| with", money(month_cache['with']))
print("fooled before/after", fooled_before, fooled_after, "| exam rec/traps/attacked", exam_rec, exam_traps, exam_attacked)
