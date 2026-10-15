"""Defense layer 1 (code): before any model sees a document, keep only the text a person would see.

A person reads a rendered page, a PDF on screen, or an email in their mail app. Attackers hide
instructions in places the person never sees but a text extractor still reads: CSS that hides text,
zero-size or white text, comments, text placed off the page, invisible characters, or the email part
the mail app doesn't show. This module removes all of those and records what it took out.

It never rewrites what is left, so a clean quote comes through unchanged.
"""

import email
import re
from email import policy
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup, Comment, Tag
from pypdf import PdfReader
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

from models import CleanDocument, RemovedText

MAX_CHARS = 8_000  # longer documents are cut, so a document can't run up the token bill (practice docs: < 1,000)
MIN_FONT_PX = 4  # HTML text smaller than this can't be read on screen
MIN_FONT_PT = 3  # same for PDFs (the practice quotes use 9-20 pt)
MIN_CONTRAST = 1.5  # text this close to its background color is invisible (WCAG's floor for readable text is 4.5)
OFFSCREEN_PX = 500  # pushed this far off the page by negative positioning or indents
INVISIBLE = re.compile("[­᠎​-‏‪-‮⁠-⁤⁦-⁩﻿]")
SKIP_TAGS = ["head", "script", "style", "noscript", "template", "iframe", "object", "embed"]
FILE_TYPES = {".html": "html", ".htm": "html", ".pdf": "pdf", ".eml": "email"}
NAMED_COLORS = {
    "white": (255, 255, 255), "black": (0, 0, 0), "snow": (255, 250, 250), "ivory": (255, 255, 240),
    "ghostwhite": (248, 248, 255), "whitesmoke": (245, 245, 245), "floralwhite": (255, 250, 240),
    "mintcream": (245, 255, 250), "azure": (240, 255, 255), "aliceblue": (240, 248, 255), "seashell": (255, 245, 238),
    "linen": (250, 240, 230), "honeydew": (240, 255, 240), "beige": (245, 245, 220), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "silver": (192, 192, 192), "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211),
    "gainsboro": (220, 220, 220), "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255), "navy": (0, 0, 128),
    "yellow": (255, 255, 0),
}
FONT_KEYWORDS = {"xx-small": 9, "x-small": 10, "small": 13, "medium": 16, "large": 18, "x-large": 24, "xx-large": 32}


# ---------- colors ----------

def parse_color(value: str | None) -> tuple[float, float, float, float] | None:
    """CSS color -> (r, g, b, alpha), or None when it can't be read (treated as visible)."""
    if not value:
        return None
    v = value.strip().lower()
    if v == "transparent":
        return (0, 0, 0, 0)
    if v in NAMED_COLORS:
        return (*NAMED_COLORS[v], 1)
    m = re.fullmatch(r"#([0-9a-f]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) in (6, 8):
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            return (r, g, b, int(h[6:8], 16) / 255 if len(h) == 8 else 1)
        return None
    m = re.fullmatch(r"rgba?\(([^)]*)\)", v)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(1)) if p]
        try:
            rgb = [float(p[:-1]) * 2.55 if p.endswith("%") else float(p) for p in parts[:3]]
            a = float(parts[3][:-1]) / 100 if len(parts) > 3 and parts[3].endswith("%") else float(parts[3]) if len(parts) > 3 else 1
            return (*rgb, a)
        except (ValueError, IndexError):
            return None
    return None


def luminance(rgb) -> float:
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# ---------- HTML ----------

def parse_decls(css: str | None) -> dict[str, str]:
    return {k.strip().lower(): v.strip().lower().replace("!important", "").strip()
            for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+)", css or "")}


def parse_stylesheets(soup: BeautifulSoup) -> list[tuple[str | None, list[str], list[str], dict[str, str]]]:
    """Rules from <style> blocks, reduced to the last simple selector (tag, #ids, .classes) of each."""
    rules = []
    for style in soup.find_all("style"):
        css = re.sub(r"/\*.*?\*/", "", style.get_text(), flags=re.S)
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            decls = parse_decls(body)
            for sel in selectors.split(","):
                last = re.split(r"[\s>+~]+", sel.strip())[-1] if sel.strip() else ""
                last = re.sub(r"::?[\w-]+(\([^)]*\))?", "", last)
                if not last or last.startswith("@"):
                    continue
                tag = re.match(r"[a-zA-Z][\w-]*", last)
                rules.append((tag.group(0).lower() if tag else None, re.findall(r"#([\w-]+)", last),
                              re.findall(r"\.([\w-]+)", last), decls))
    return rules


def element_style(el: Tag, rules) -> dict[str, str]:
    style: dict[str, str] = {}
    classes = set(el.get("class") or [])
    for tag, ids, cls, decls in rules:
        if (tag is None or tag == el.name) and all(i == el.get("id") for i in ids) and all(c in classes for c in cls):
            style.update(decls)
    style.update(parse_decls(el.get("style")))
    return style


def px(value: str, parent_px: float) -> float | None:
    v = value.strip()
    if v in FONT_KEYWORDS:
        return FONT_KEYWORDS[v]
    if v == "smaller":
        return parent_px * 0.83
    if v == "larger":
        return parent_px * 1.2
    m = re.fullmatch(r"(-?[\d.]+)\s*(px|pt|em|rem|%|vw|vh)?", v)
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2) or "px"
    return {"px": n, "pt": n * 4 / 3, "em": n * parent_px, "rem": n * 16, "%": n / 100 * parent_px,
            "vw": n * 12.8, "vh": n * 8}[unit]


def font_size(style: dict[str, str], parent_px: float) -> float:
    if "font-size" in style:
        size = px(style["font-size"], parent_px)
        if size is not None:
            return size
    if "font" in style:  # shorthand such as "font: 0/0 a" or "italic 1px serif"
        m = re.search(r"(?:^|\s)(-?[\d.]+(?:px|pt|em|rem|%)?)(?:/\S+)?(?:\s|$)", style["font"])
        if m:
            size = px(m.group(1), parent_px)
            if size is not None:
                return size
    return parent_px


def background(style: dict[str, str]):
    for key in ("background-color", "background"):
        if key in style:
            for token in re.findall(r"#[0-9a-f]{3,8}|rgba?\([^)]*\)|[a-z]+", style[key]):
                color = parse_color(token)
                if color is not None and color[3] > 0.1:
                    return color
    return None


def hidden_element(el: Tag, style: dict[str, str]) -> str | None:
    """Why this whole element is invisible to a person, or None if it can be seen."""
    if el.has_attr("hidden"):
        return "hidden attribute"
    if el.get("aria-hidden") == "true":
        return 'aria-hidden="true"'
    if el.name == "input" and (el.get("type") or "").lower() == "hidden":
        return "hidden form field"
    if style.get("display") == "none":
        return "display:none"
    if style.get("visibility") in ("hidden", "collapse"):
        return f"visibility:{style['visibility']}"
    try:
        if "opacity" in style and float(style["opacity"].rstrip("%")) / (100 if style["opacity"].endswith("%") else 1) <= 0.1:
            return f"opacity:{style['opacity']}"
    except ValueError:
        pass
    for side in ("width", "height", "max-width", "max-height"):
        if re.fullmatch(r"0(px|pt|em|rem|%)?", style.get(side, "")) and style.get("overflow") in ("hidden", "clip"):
            return f"{side}:0 with overflow hidden"
    if re.search(r"rect\(\s*0", style.get("clip", "")) or re.search(r"inset\(\s*50%|circle\(\s*0", style.get("clip-path", "")):
        return "clipped to nothing"
    if re.search(r"scale\(\s*0(\.0+)?\s*[,)]", style.get("transform", "")):
        return "transform: scale(0)"
    for side in ("left", "top", "right", "bottom", "text-indent", "margin-left", "margin-top"):
        value = px(style.get(side, "0"), 16)
        if value is not None and value <= -OFFSCREEN_PX:
            return f"pushed off screen ({side}:{style[side]})"
    return None


def clean_html(markup: str) -> tuple[str, list[RemovedText]]:
    """Visible text of an HTML page, the way a browser would show it, plus what was hidden."""
    soup = BeautifulSoup(markup, "html.parser")
    rules = parse_stylesheets(soup)
    removed: list[RemovedText] = []

    def note(text: str, why: str) -> None:
        text = " ".join(INVISIBLE.sub("", text).split())
        if text:
            removed.append(RemovedText(text=text, why=why))

    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        note(str(c), "HTML comment (browsers never show comments)")
        c.extract()
    for tag in soup.find_all(SKIP_TAGS):
        if tag.name in ("script", "style", "head"):
            if tag.name == "script":
                note(tag.get_text(), "script code (runs in the browser, never shown)")
        else:
            note(tag.get_text(), f"<{tag.name}> content (not shown on the page)")
        tag.decompose()

    def walk(el: Tag, color, bg, size: float) -> None:
        for child in list(el.children):
            if isinstance(child, Tag):
                style = element_style(child, rules)
                why = hidden_element(child, style)
                if why:
                    note(child.get_text(" "), why)
                    child.decompose()
                    continue
                walk(child, parse_color(style.get("color")) or color, background(style) or bg,
                     font_size(style, size))
            elif isinstance(child, str) and child.strip():
                why = []
                if size < MIN_FONT_PX:
                    why.append(f"font-size {size:g}px")
                if color is not None and color[3] <= 0.1:
                    why.append("transparent text")
                elif color is not None and contrast(color, bg) < MIN_CONTRAST:
                    why.append(f"text color matches its background (contrast {contrast(color, bg):.2f}:1)")
                if why:
                    note(str(child), "; ".join(why))
                    child.replace_with("")

    body = soup.body or soup
    style = element_style(body, rules) if isinstance(body, Tag) and body.name else {}
    walk(body, parse_color(style.get("color")) or (0, 0, 0, 1), background(style) or (255, 255, 255, 1),
         font_size(style, 16))
    lines = (line.strip() for line in body.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line), removed


# ---------- PDF ----------

def pdf_rgb(color) -> tuple[float, float, float]:
    """pdfplumber fill color (gray, RGB, or CMYK, 0-1) -> RGB 0-255. Unknown -> black."""
    c = tuple(color) if isinstance(color, (list, tuple)) else ()
    if len(c) == 1:
        return (c[0] * 255,) * 3
    if len(c) == 3:
        return tuple(v * 255 for v in c)
    if len(c) == 4:
        k = c[3]
        return tuple((1 - v) * (1 - k) * 255 for v in c[:3])
    return (0, 0, 0)


INVISIBLE_RENDER_MODES = {3, 7}  # PDF text render modes that draw no visible glyphs


def invisible_render_mode_text(path: Path) -> list[str]:
    """Text drawn in an invisible render mode (Tr 3 or 7): in the file and read by extractors, but a
    viewer paints nothing. pdfplumber does not expose render mode, so read the content stream directly."""
    found: list[str] = []
    try:
        reader = PdfReader(str(path))
    except Exception:
        return found
    for page in reader.pages:
        contents = page.get_contents()
        if contents is None:
            continue
        mode = 0
        for operands, operator in ContentStream(contents, reader).operations:
            op = operator.decode("latin-1", "ignore") if isinstance(operator, bytes) else str(operator)
            if op == "Tr" and operands:
                try:
                    mode = int(operands[0])
                except (TypeError, ValueError):
                    mode = 0
            elif mode in INVISIBLE_RENDER_MODES and operands:
                if op in ("Tj", "'", '"'):
                    found.append(str(operands[-1]))
                elif op == "TJ":
                    found.append("".join(str(x) for x in operands[0]
                                         if isinstance(x, (TextStringObject, ByteStringObject))))
    return [s for s in (" ".join(s.split()) for s in found) if s]


def clean_pdf(path: Path) -> tuple[str, list[RemovedText]]:
    """Visible text of a PDF, the way a viewer would show it, plus what was hidden."""
    removed: list[RemovedText] = []
    pages = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            x0, top0, x1, bottom0 = page.bbox
            fills = [r for r in page.rects if r.get("fill")]
            hidden_lines: dict[tuple[int, str], list] = {}

            def why_hidden(ch) -> str | None:
                if ch["size"] < MIN_FONT_PT:
                    return f"font size {ch['size']:.1f} pt"
                if ch["top"] > bottom0:
                    return f"placed below the bottom edge ({ch['top']:.0f} pt down a {bottom0 - top0:.0f} pt page)"
                if ch["bottom"] < top0:
                    return "placed above the top edge of the page"
                if ch["x0"] > x1:
                    return "placed past the right edge of the page"
                if ch["x1"] < x0:
                    return "placed past the left edge of the page"
                cx, cy = (ch["x0"] + ch["x1"]) / 2, (ch["top"] + ch["bottom"]) / 2
                under = [r for r in fills if r["x0"] <= cx <= r["x1"] and r["top"] <= cy <= r["bottom"]]
                surface = pdf_rgb(under[-1].get("non_stroking_color")) if under else (255, 255, 255)
                text_color = pdf_rgb(ch.get("non_stroking_color"))
                if contrast(text_color, surface) < MIN_CONTRAST:
                    return "text color matches the page behind it"
                return None

            def keep(obj) -> bool:
                if obj.get("object_type") != "char":
                    return True
                why = why_hidden(obj)
                if why:
                    hidden_lines.setdefault((round(obj["top"]), why), []).append(obj)
                    return False
                return True

            text = page.filter(keep).extract_text() or ""
            for (_, why), chars in sorted(hidden_lines.items()):
                note = "".join(c["text"] for c in sorted(chars, key=lambda c: c["x0"]))
                removed.append(RemovedText(text=" ".join(note.split()), why=f"page {number}: {why}"))
            pages.append(text)

    # Color/size/position can't reveal invisible render mode (pdfplumber omits it); strip it from the text.
    joined = "\n".join(pages)
    for phrase in invisible_render_mode_text(path):
        pattern = re.compile(r"\s*".join(re.escape(word) for word in phrase.split()))
        if pattern.search(joined):
            joined = pattern.sub(" ", joined)
            removed.append(RemovedText(text=phrase, why="invisible text render mode (Tr 3/7): drawn but not painted"))
    joined = re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", joined))
    return joined.strip("\n"), removed


# ---------- email ----------

def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9$.]+", " ", INVISIBLE.sub("", text).lower()).strip()


def clean_email(raw: bytes) -> tuple[str, list[RemovedText]]:
    """What an email app shows: the headers, then the HTML version if there is one, else the plain text."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    lines = [f"{h}: {msg[h]}" for h in ("From", "To", "Subject", "Date") if msg[h]]
    removed: list[RemovedText] = []
    html_part = msg.get_body(preferencelist=("html",))
    plain_part = msg.get_body(preferencelist=("plain",))
    if html_part is not None:
        body, removed = clean_html(html_part.get_content())
        if plain_part is not None:  # text that only the plain version carries never appears in the mail app
            shown = squash(body)
            for line in plain_part.get_content().splitlines():
                if line.strip() and squash(line) not in shown:
                    removed.append(RemovedText(text=line.strip(), why="only in the plain-text version, which "
                                                                       "email apps hide when there is an HTML version"))
    elif plain_part is not None:
        body = plain_part.get_content()
    else:
        body = ""
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            removed.append(RemovedText(text=part.get_filename() or part.get_content_type(), why="attachment not read"))
    return "\n".join(lines + ["", body.strip()]), removed


# ---------- entry point ----------

def clean_document(path: Path) -> CleanDocument:
    """Layer 1: everything a model will ever see of this document."""
    file_type = FILE_TYPES[path.suffix.lower()]
    if file_type == "html":
        text, removed = clean_html(path.read_text(encoding="utf-8", errors="replace"))
    elif file_type == "pdf":
        text, removed = clean_pdf(path)
    else:
        text, removed = clean_email(path.read_bytes())
    invisible = len(INVISIBLE.findall(text))
    text = INVISIBLE.sub("", text).replace(" ", " ")
    text = "".join(ch for ch in text if ch in "\n\t" or ch.isprintable())
    truncated = len(text) > MAX_CHARS
    if truncated:
        removed.append(RemovedText(text=text[MAX_CHARS:MAX_CHARS + 200], why=f"past the {MAX_CHARS:,}-character limit"))
        text = text[:MAX_CHARS]
    return CleanDocument(file=path.name, file_type=file_type, text=text, removed=removed,
                         invisible_characters_removed=invisible, truncated=truncated)
