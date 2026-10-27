#!/usr/bin/env python3
"""Generate the profile SVGs (banner + two architecture diagrams), light and dark.

Run from the output folder:

    uv run --no-project --with fonttools==4.60.1 --with uharfbuzz==0.51.1 python scripts/build_assets.py

Text is shaped with HarfBuzz from the bundled Archivo variable font (SIL OFL,
see scripts/fonts/OFL.txt) and written out as vector paths, so the SVGs look
the same everywhere and need no web fonts. Backgrounds are transparent: the
artwork sits directly on GitHub's own page colour.

The one recurring motif is "the call line": a voice waveform that settles into
a straight line and ends in a filled dot, the outcome.
"""
import math
from pathlib import Path
from xml.sax.saxutils import escape

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONT_PATH = ROOT / "scripts" / "fonts" / "Archivo.ttf"

THEMES = {
    "light": {"ink": "#14182B", "muted": "#5A6383", "accent": "#3150F5", "rule": "#D5DAE8", "knock": "#FFFFFF"},
    "dark": {"ink": "#E9ECF6", "muted": "#8A93B5", "accent": "#8EA2FF", "rule": "#283055", "knock": "#0D1117"},
}

# (weight, width, tracking in font units)
STYLES = {
    "display": (860, 62, -6),
    "lede": (480, 100, -4),
    "title": (640, 100, 0),
    "body": (430, 100, 0),
    "num": (700, 100, 0),
}

_FACE = hb.Face(hb.Blob.from_file_path(str(FONT_PATH)))
_FONTS = {}


def _font(style):
    if style not in _FONTS:
        w, d, _ = STYLES[style]
        f = hb.Font(_FACE)
        f.set_variations({"wght": w, "wdth": d})
        _FONTS[style] = f
    return _FONTS[style]


UPEM = _FACE.upem


def _shape(s, style):
    font = _font(style)
    buf = hb.Buffer()
    buf.add_str(s)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": True})
    track = STYLES[style][2]
    return font, [(i.codepoint, p.x_advance + track, p.x_offset, p.y_offset)
                  for i, p in zip(buf.glyph_infos, buf.glyph_positions)]


def measure(s, size, style):
    _, glyphs = _shape(s, style)
    return sum(g[1] for g in glyphs) * size / UPEM


_GLYPHS = {}  # (style, gid) -> path data in font units; reset per SVG


def _glyph_id(style, gid, font):
    key = (style, gid)
    if key not in _GLYPHS:
        pen = SVGPathPen(None, ntos=lambda v: str(round(v)))
        font.draw_glyph_with_pen(gid, pen)
        _GLYPHS[key] = pen.getCommands()
    return f"{style[0]}{gid}" if _GLYPHS[key] else None


def _fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def text(s, x, y, size, style, fill, anchor="start"):
    """Return SVG for `s` with its baseline at y. Glyph outlines are defined
    once per file and placed with <use>, which keeps the files small."""
    font, glyphs = _shape(s, style)
    k = size / UPEM
    width = sum(g[1] for g in glyphs) * k
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    uses, cx = [], x
    for gid, adv, xo, yo in glyphs:
        ref = _glyph_id(style, gid, font)
        if ref:
            uses.append(f'<use href="#{ref}" x="{_fmt((cx + xo * k) / k)}" y="{_fmt(-(y - yo * k) / k)}"/>')
        cx += adv * k
    if not uses:
        return ""
    return f'<g fill="{fill}" transform="scale({k:.7g} {-k:.7g})">{"".join(uses)}</g>'


def lines(items, x, y, size, style, fill, leading=1.45, anchor="start"):
    return "\n".join(text(s, x, y + i * size * leading, size, style, fill, anchor) for i, s in enumerate(items))


def wave(x0, x1, y, amp, t, width=2.2):
    """Speech-like waveform whose amplitude decays to zero at x1."""
    pts = []
    n = int((x1 - x0) / 1.5)
    f = (x1 - x0) / 420  # keep the same wavelength at any length
    for i in range(n + 1):
        u = i / n
        x = x0 + (x1 - x0) * u
        env = amp * (1 - u) ** 1.6 * (0.55 + 0.45 * math.sin(u * 9.0 * max(f, .3) + 0.6) ** 2)
        v = (math.sin(u * 61 * f) * 0.62 + math.sin(u * 137 * f + 1.3) * 0.28 + math.sin(u * 23 * f + 0.4) * 0.30)
        pts.append(f"{x:.1f},{y - env * v:.1f}")
    return (f'<polyline points="{" ".join(pts)}" fill="none" stroke="{t["accent"]}" '
            f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')


def hline(x0, x1, y, t, color="accent", width=2.2):
    return f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{t[color]}" stroke-width="{width}" stroke-linecap="round"/>'


def stop(x, y, t, n=None, final=False, r=13):
    if final:
        return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{t["accent"]}"/>' + (
            text(str(n), x, y + 5, 14, "num", t["knock"], "middle") if n else "")
    out = f'<circle cx="{x}" cy="{y}" r="{r}" fill="{t["knock"]}" stroke="{t["accent"]}" stroke-width="2.2"/>'
    if n:
        out += text(str(n), x, y + 5, 14, "num", t["accent"], "middle")
    return out


def dot(x, y, t, final=False, r=6):
    if final:
        return f'<circle cx="{x}" cy="{y}" r="{r + 1}" fill="{t["accent"]}"/>'
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{t["knock"]}" stroke="{t["accent"]}" stroke-width="2"/>'


def sequence(x0, x1, y, labels, t, size=17):
    """A short call line: evenly spaced stops with labels underneath."""
    out = [hline(x0, x1, y, t)]
    n = len(labels)
    for i, lab in enumerate(labels):
        x = x0 + (x1 - x0) * i / (n - 1)
        last = i == n - 1
        out.append(dot(x, y, t, final=last))
        anchor = "start" if i == 0 else "end" if last else "middle"
        out.append(text(lab, x - (6 if i == 0 else 0), y + 30, size, "body", t["ink"] if last else t["muted"], anchor))
    return "\n".join(out)


def svg(w, h, body, label):
    defs = "".join(f'<path id="{st[0]}{gid}" d="{d}"/>' for (st, gid), d in sorted(_GLYPHS.items()) if d)
    _GLYPHS.clear()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{escape(label)}">\n<title>{escape(label)}</title>\n'
            f'<defs>{defs}</defs>\n{body}\n</svg>\n')


# ------------------------------------------------------------------ banner
def banner(t):
    W, H = 1280, 330
    b = [text("Ly Yeakkhai", 0, 128, 148, "display", t["ink"])]
    y = 176
    b.append(wave(2, 420, y, 26, t))
    b.append(hline(420, 1262, y, t))
    b.append(f'<circle cx="1266" cy="{y}" r="9" fill="{t["accent"]}"/>')
    b.append(lines(["I build AI systems that take real", "actions, from first call to deploy."], 0, 252, 34, "lede", t["ink"], leading=1.32))
    b.append(lines(["Founder, Dockified", "Computer Science, CADT"], 1280, 252, 21, "body", t["muted"], leading=1.55, anchor="end"))
    return svg(W, H, "\n".join(b), "Ly Yeakkhai. I build AI systems that take real actions, from first call to deploy.")


# ------------------------------------------------------------------ Veaja
def veaja(t):
    W, H = 1000, 470
    y = 150
    b = [wave(0, 64, y, 14, t), hline(64, 950, y, t)]
    stops = [
        (90, "Call comes in", ["telephony webhook"]),
        (285, "Verified", ["signed requests only"]),
        (480, "Recorded once", ["a retried webhook", "can't act twice"]),
        (675, "Agent acts", []),
        (962, "Outcome", ["spoken reply,", "staff alert"]),
    ]
    for i, (x, title, sub) in enumerate(stops):
        last = i == len(stops) - 1
        b.append(stop(x, y, t, n=i + 1, final=last))
        anchor = "end" if last else "start"
        tx = x + 13 if last else x - 13
        b.append(text(title, tx, y - 34, 21, "title", t["ink"], anchor))
        b.append(lines(sub, tx, y + 46, 16, "body", t["muted"], anchor=anchor))

    # tools branching down from stop 4
    tools = [("bookings", ["overlaps rejected", "by Postgres"]), ("orders", ["place and track"]),
             ("catalog", ["product lookup"]), ("knowledge base", ["pgvector with", "an HNSW index"]),
             ("call control", ["transfer to", "a person"])]
    size = 18
    widths = [max(measure(n, size, "title"), *(measure(s, 15, "body") for s in sub)) for n, sub in tools]
    x0, x1 = 330, 1000
    gap = (x1 - x0 - sum(widths)) / (len(tools) - 1)
    ty, cx = 330, x0
    sx, sy = 675, y + 74
    b.append(f'<line x1="{sx}" y1="{y + 13}" x2="{sx}" y2="{sy}" stroke="{t["rule"]}" stroke-width="1.6"/>')
    b.append(text("calls a tool", sx + 14, y + 52, 16, "body", t["muted"]))
    for (name, sub), w in zip(tools, widths):
        mid = cx + w / 2
        b.append(f'<path d="M{sx} {sy} C{sx} {sy + 50}, {mid} {ty - 90}, {mid} {ty - 30}" fill="none" '
                 f'stroke="{t["rule"]}" stroke-width="1.6"/>')
        b.append(dot(mid, ty - 30, t, r=4))
        b.append(text(name, mid, ty, size, "title", t["ink"], "middle"))
        b.append(lines(sub, mid, ty + 24, 15, "body", t["muted"], leading=1.4, anchor="middle"))
        cx += w + gap

    b.append(text("Scheduled work", 0, ty, 18, "title", t["ink"]))
    b.append(lines(["Background jobs hold a Valkey", "lock, so each run happens once", "across every server."], 0, ty + 24, 15, "body", t["muted"], leading=1.4))
    b.append(text("Simplified for public view. Vendor names, endpoints and the data model are left out.", 0, 452, 14, "body", t["muted"]))
    return svg(W, H, "\n".join(b), "Veaja call path: a call arrives by webhook, is verified, recorded once, the agent calls a tool, and the call ends in an outcome.")


# ------------------------------------------------------------------ LiveFlows
def liveflows(t):
    W, H = 1000, 590
    L, C = 0, 190
    b = []

    def row(y_top, name, height):
        b.append(text(name, L, y_top + 34, 19, "title", t["ink"]))
        b.append(f'<line x1="0" y1="{y_top + height}" x2="{W}" y2="{y_top + height}" stroke="{t["rule"]}" stroke-width="1"/>')

    row(0, "Browser", 96)
    b.append(lines(["Canvas, documents, Mermaid and DBML notation, Repo Map", "and the assistant, all in one Next.js app."], C, 34, 18, "body", t["ink"]))

    row(96, "Live sync", 184)
    b.append(text("Every file is a Yjs room on a self-hosted Hocuspocus server.", C, 130, 18, "body", t["ink"]))
    b.append(text("Agents change files through a command API, never directly:", C, 160, 18, "body", t["muted"]))
    b.append(sequence(C + 6, 760, 192, ["read", "dry-run", "apply", "revert"], t))
    b.append(text("Each command carries a short-lived signed token and passes the same access checks as a person.", C, 258, 15, "body", t["muted"]))

    row(280, "API", 96)
    b.append(lines(["NestJS for workspaces, access control, assistant runs and", "personal access tokens. PostgreSQL through Prisma."], C, 314, 18, "body", t["ink"]))

    row(376, "Repo Map", 156)
    b.append(text("Point it at a GitHub repository and get a real import graph.", C, 410, 18, "body", t["ink"]))
    b.append(sequence(C + 6, W - 8, 448, ["fetch", "parse with ts-morph", "framework adapters", "import graph", "AI explanations"], t))
    b.append(text("Adapters for Next.js, NestJS, React and Express. Imports it can't follow say why.", C, 510, 15, "body", t["muted"]))

    b.append(text("Six apps ship as Docker images from GitHub Actions, served behind Caddy.", 0, 570, 14, "body", t["muted"]))
    return svg(W, H, "\n".join(b), "LiveFlows layers: Next.js browser app, Yjs live sync with an agent command API, NestJS API, and the Repo Map pipeline.")


def main():
    (ASSETS / "architecture").mkdir(parents=True, exist_ok=True)
    for name, t in THEMES.items():
        (ASSETS / f"banner-{name}.svg").write_text(banner(t))
        (ASSETS / "architecture" / f"veaja-{name}.svg").write_text(veaja(t))
        (ASSETS / "architecture" / f"liveflows-{name}.svg").write_text(liveflows(t))
    for p in sorted(ASSETS.rglob("*.svg")):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
