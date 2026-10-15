"""Problem 5: open each practice document the way a person would, and compare with what the agent reads.

HTML pages and emails are rendered in headless Chrome (emails as an email app shows them: the headers,
then the HTML version if there is one, otherwise the plain text). PDFs are rendered with PDFium, the
engine inside Chrome's PDF viewer. For each document this saves a screenshot to output/human_view/ and
splits the text into what a person can see and what is hidden, using the browser's own layout and
colors (HTML and email) or the PDF's drawing instructions (color, font size, position on the page).

No API calls. Run from the Homework 6 folder:
    .\\.venv\\Scripts\\python.exe scripts\\human_view.py
"""

import email
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from email import policy
from pathlib import Path

import pdfplumber
import pypdfium2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import FILE_TYPES, OUTPUT_DIR, email_to_text, html_to_text, pdf_to_text  # noqa: E402

DOCS = sorted((ROOT / "data" / "practice_docs").iterdir())
OUT_DIR = OUTPUT_DIR / "human_view"
BROWSERS = [Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")]
INVISIBLE = re.compile(r"[\u200b-\u200f\u2060\ufeff]")  # zero-width characters

# Runs inside the rendered page: sorts every piece of text into visible or hidden, with the reason.
VISIBILITY_JS = r"""
<script id="__hv">
(function () {
  function rgb(c) { const m = c.match(/[\d.]+/g) || []; return m.map(Number); }
  function lum(c) {
    const [r, g, b] = rgb(c).slice(0, 3).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  function background(el) {
    for (let e = el; e; e = e.parentElement) {
      const c = getComputedStyle(e).backgroundColor, a = rgb(c);
      if (a.length < 4 || a[3] > 0) return c;
    }
    return 'rgb(255, 255, 255)';
  }
  const visible = [], hidden = [];
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    const el = n.parentElement;
    if (['SCRIPT', 'STYLE'].includes(el.tagName)) continue;
    const text = n.textContent.replace(/[\u200b-\u200f\u2060\ufeff]/g, '').trim();
    if (!text) continue;
    const s = getComputedStyle(el), range = document.createRange();
    range.selectNodeContents(n);
    const r = range.getBoundingClientRect(), why = [];
    if (r.width <= 1 || r.height <= 1) why.push('takes no space on screen (' + r.width.toFixed(1) + 'x' + r.height.toFixed(1) + ' px, display: ' + s.display + ', font-size: ' + s.fontSize + ')');
    else if (parseFloat(s.fontSize) < 4) why.push('font-size ' + s.fontSize);
    if (s.visibility !== 'visible') why.push('visibility: ' + s.visibility);
    const clip = s.clip || 'auto', clipPath = s.clipPath || 'none';
    if (/rect\(\s*0px/.test(clip) || /inset\(\s*(?:50|100)%|circle\(\s*0/.test(clipPath)) why.push('clipped to nothing (' + (clip !== 'auto' ? 'clip: ' + clip : 'clip-path: ' + clipPath) + ')');
    let opacity = 1;
    for (let e = el; e; e = e.parentElement) opacity *= parseFloat(getComputedStyle(e).opacity);
    if (opacity < 0.1) why.push('opacity ' + opacity);
    const bg = background(el), l1 = lum(s.color), l2 = lum(bg);
    if ((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05) < 1.5) why.push('text color ' + s.color + ' on background ' + bg);
    if (r.right < 0 || r.bottom < 0) why.push('positioned off screen');
    if (why.length) hidden.push({text: text, why: why.join('; '), element: el.tagName.toLowerCase(), style: el.getAttribute('style')});
    else visible.push(text);
  }
  const comments = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_COMMENT);
  let c;
  while ((c = comments.nextNode())) hidden.push({text: c.textContent.trim(), why: 'HTML comment (browsers never display comments)', element: 'comment', style: null});
  for (const sc of document.querySelectorAll('script:not(#__hv)'))
    if (sc.textContent.trim()) hidden.push({text: sc.textContent.trim(), why: 'script code (runs in the browser, never displayed)', element: 'script', style: null});
  const pre = document.createElement('pre');
  pre.id = '__visibility';
  pre.textContent = JSON.stringify({visible: visible, hidden: hidden});
  document.body.appendChild(pre);
})();
</script>
"""


def browser() -> Path:
    for b in BROWSERS:
        if b.exists():
            return b
    sys.exit("No Chrome or Edge found for rendering HTML.")


def run_browser(args: list[str], profile: Path) -> str:
    cmd = [str(browser()), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           "--hide-scrollbars", f"--user-data-dir={profile}", *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=90).stdout


def email_view(raw: bytes) -> tuple[str, str]:
    """An email app's view: headers, then the HTML part if any (apps prefer it), else the plain text."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    head = "".join(f"<b>{h}:</b> {html.escape(str(msg[h]))}<br>" for h in ("From", "To", "Subject", "Date") if msg[h])
    html_part = msg.get_body(preferencelist=("html",))
    if html_part is not None:
        body, shown = html_part.get_content(), "HTML part"
    else:
        body = f'<div style="white-space:pre-wrap">{html.escape(msg.get_body(preferencelist=("plain",)).get_content())}</div>'
        shown = "plain-text part"
    page = (f'<html><head><meta charset="utf-8"></head><body style="font-family:Segoe UI,Arial,sans-serif;'
            f'margin:24px;max-width:760px;color:#1d2733"><div style="border-bottom:1px solid #c9d1da;'
            f'padding-bottom:10px;margin-bottom:14px">{head}</div><div>{body}</div></body></html>')
    return page, shown


def html_like(doc: Path, work: Path) -> dict:
    """Render an HTML page or an email in the browser: screenshot plus visible/hidden text."""
    if doc.suffix.lower() == ".eml":
        page, shown = email_view(doc.read_bytes())
        view = f"email app view ({shown} shown, as email apps prefer the HTML version)"
    else:
        page, view = doc.read_text(encoding="utf-8"), "web browser"
    plain = work / f"{doc.stem}.html"
    plain.write_text(page, encoding="utf-8")
    shot = OUT_DIR / f"{doc.stem}.png"
    run_browser([f"--screenshot={shot}", "--window-size=900,760", plain.as_uri()], work / "profile")

    probe = work / f"{doc.stem}_probe.html"
    probe.write_text(page.replace("</body>", VISIBILITY_JS + "</body>") if "</body>" in page else page + VISIBILITY_JS,
                     encoding="utf-8")
    dom = run_browser(["--dump-dom", probe.as_uri()], work / "profile")
    found = re.search(r'<pre id="__visibility">(.*?)</pre>', dom, re.S)
    data = json.loads(html.unescape(found.group(1)))
    return {"opened_in": view, "screenshot": shot.relative_to(ROOT).as_posix(), "visible_text": data["visible"],
            "hidden": data["hidden"]}


def pdf(doc: Path) -> dict:
    """Render the PDF like a viewer does, and classify each text line by color, size, and position."""
    shot = OUT_DIR / f"{doc.stem}.png"
    pdfium = pypdfium2.PdfDocument(doc)
    pdfium[0].render(scale=1.25).to_pil().save(shot)
    pdfium.close()
    visible, hidden = [], []
    with pdfplumber.open(doc) as d:
        for number, page in enumerate(d.pages, 1):
            lines = defaultdict(list)
            for ch in page.chars:
                key = (round(ch["top"]), round(ch["size"], 1), tuple(round(v, 2) for v in (ch["non_stroking_color"] or ())))
                lines[key].append(ch)
            for (top, size, color), chars in sorted(lines.items()):
                text = "".join(c["text"] for c in sorted(chars, key=lambda c: c["x0"])).strip()
                why = []
                if color and min(color) >= 0.95 and not page.rects and not page.images:
                    why.append(f"white text (color {color}) on a white page")
                if size < 2:
                    why.append(f"font size {size} pt (normal text here is 11 pt)")
                if top > page.height or top < 0:
                    why.append(f"placed {top} pt from the top of a {page.height:.0f} pt page, below the bottom edge")
                if why:
                    hidden.append({"text": text, "why": "; ".join(why), "page": number, "y_from_top_pt": top,
                                   "font_size_pt": size, "color": list(color)})
                else:
                    visible.append(text)
    return {"opened_in": "PDF viewer (PDFium, the engine in Chrome's PDF viewer)",
            "screenshot": shot.relative_to(ROOT).as_posix(), "visible_text": visible, "hidden": hidden}


def agent_text(doc: Path) -> str:
    """Exactly what read_document hands the model."""
    kind = FILE_TYPES[doc.suffix.lower()]
    if kind == "html":
        return html_to_text(doc.read_text(encoding="utf-8"))
    if kind == "pdf":
        return pdf_to_text(doc)
    return email_to_text(doc.read_bytes())


def squash(text: str) -> str:
    return " ".join(INVISIBLE.sub("", text).split())


def source_line(doc: Path, snippet: str) -> int | None:
    """Line number of the hidden text in the raw file, when it is stored as plain text."""
    if doc.suffix.lower() == ".pdf":
        return None
    raw = doc.read_text(encoding="utf-8", errors="replace").splitlines()
    probe = squash(snippet)[:25]
    for i, line in enumerate(raw, 1):
        if probe and probe in INVISIBLE.sub("", line):
            return i
    return None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="hv_"))
    results = {}
    try:
        for doc in DOCS:
            view = pdf(doc) if doc.suffix.lower() == ".pdf" else html_like(doc, work)
            read = agent_text(doc)
            for h in view["hidden"]:
                h["agent_read_it"] = squash(h["text"])[:60] in squash(read)
                h["source_line"] = source_line(doc, h["text"])
            results[doc.name] = {**view, "agent_text": read}
            print(f"{doc.name:30} hidden pieces: {len(view['hidden'])}  "
                  + "; ".join(f"[{'READ' if h['agent_read_it'] else 'not read'}] {h['why'][:60]}" for h in view["hidden"]))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    (OUT_DIR / "human_view.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
