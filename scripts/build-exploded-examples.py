#!/usr/bin/env python3
"""Build the exploded axonometric examples from one projection.

Every coordinate in the generated files comes from ``iso(x, y, z)``, the 2:1
dimetric projection documented in
``skills/diagram-design/references/type-exploded.md``. Nothing is placed by
hand, so the examples can be rebuilt after any change to the model and
``scripts/verify-exploded.py`` can recompute every silhouette from the
attributes each part declares.

    python3 scripts/build-exploded-examples.py          # write the examples
    python3 scripts/build-exploded-examples.py --check  # fail if any file is stale
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
MOTION_TEMPLATE = ASSETS / "template-motion.html"
S2 = math.sqrt(2)

# Face tones per skin. Every value is a style-guide role or an rgba() of one.
SKINS = {
    "light": dict(
        paper="#f5f5f5", ink="#2d3142", muted="#4f5d75", soft="#7a8399", accent="#eb6c36",
        ink_rgb="45,49,66", acc_rgb="235,108,54", base="#ffffff", rule="rgba(45,49,66,0.12)",
        shade=(None, "rgba(45,49,66,0.07)", "rgba(45,49,66,0.15)"),
        focal=("rgba(235,108,54,0.10)", "rgba(235,108,54,0.20)", "rgba(235,108,54,0.32)"),
        cavity="rgba(45,49,66,0.10)", floor="rgba(45,49,66,0.04)", well="rgba(45,49,66,0.14)",
        screen="#2d3142", island="#111111", chip_top="#4f5d75", chip_side="#2d3142",
        sil="#2d3142", inner="rgba(45,49,66,0.55)", trace="rgba(45,49,66,0.30)",
        lead="rgba(45,49,66,0.40)", lead_acc="rgba(235,108,54,0.60)", inner_acc="rgba(235,108,54,0.70)",
        lens="#2d3142", lens_ring="rgba(245,245,245,0.35)",
    ),
    "dark": dict(
        paper="#2d3142", ink="#f5f5f5", muted="#bfc0c0", soft="#8e98ac", accent="#f08a59",
        ink_rgb="245,245,245", acc_rgb="240,138,89", base="#393e53", rule="rgba(245,245,245,0.12)",
        shade=("rgba(245,245,245,0.10)", None, "rgba(45,49,66,0.45)"),
        focal=("rgba(240,138,89,0.18)", None, "rgba(45,49,66,0.45)"),
        cavity="rgba(45,49,66,0.55)", floor="rgba(45,49,66,0.25)", well="rgba(45,49,66,0.40)",
        screen="#111111", island="#2d3142", chip_top="#8e98ac", chip_side="#2d3142",
        sil="#f5f5f5", inner="rgba(245,245,245,0.45)", trace="rgba(245,245,245,0.30)",
        lead="rgba(245,245,245,0.40)", lead_acc="rgba(240,138,89,0.60)", inner_acc="rgba(240,138,89,0.70)",
        lens="#111111", lens_ring="rgba(245,245,245,0.35)",
    ),
}


# ---------------------------------------------------------------- projection


def f(value: float) -> str:
    rounded = round(value, 2)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:g}"


class Proj:
    """iso(x, y, z) = [x - y, (x + y) / 2 - z], shifted to the drawing origin."""

    def __init__(self, ox: float, oy: float):
        self.ox, self.oy = ox, oy

    def iso(self, x, y, z):
        return (self.ox + x - y, self.oy + (x + y) / 2 - z)


@dataclass
class Rect:
    """A rounded-rectangle footprint. r = 0 is a box; r = w/2 = d/2 is a cylinder."""

    x0: float
    y0: float
    x1: float
    y1: float
    r: float = 0

    def centers(self):
        r = self.r
        return [(self.x1 - r, self.y1 - r), (self.x0 + r, self.y1 - r),
                (self.x0 + r, self.y0 + r), (self.x1 - r, self.y0 + r)]

    def inset(self, m, r=None):
        return Rect(self.x0 + m, self.y0 + m, self.x1 - m, self.y1 - m,
                    max(0, self.r - m) if r is None else r)

    def attr(self):
        return " ".join(f(v) for v in (self.x0, self.y0, self.x1, self.y1, self.r))


def corner(theta):
    return int(math.floor(theta / 90)) % 4


def point(P, rect, theta, z, k=None):
    k = corner(theta) if k is None else k
    cx, cy = rect.centers()[k]
    t = math.radians(theta)
    return P.iso(cx + rect.r * math.cos(t), cy + rect.r * math.sin(t), z)


def walk(P, rect, a, b, z):
    """Path commands from outline angle a to b. Each corner is a quarter of one 2:1 ellipse."""
    cmds = []
    rx, ry = rect.r * S2, rect.r / S2
    rising = b > a
    th = a
    while (b - th) * (1 if rising else -1) > 1e-9:
        nxt = min(b, (math.floor(th / 90) + 1) * 90) if rising else max(b, (math.ceil(th / 90) - 1) * 90)
        k = corner((th + nxt) / 2)
        end = point(P, rect, nxt, z, k)
        if rect.r > 0:
            cmds.append(f"A {f(rx)} {f(ry)} 0 0 {1 if rising else 0} {f(end[0])} {f(end[1])}")
        else:
            cmds.append(f"L {f(end[0])} {f(end[1])}")
        th = nxt
        if (b - th) * (1 if rising else -1) > 1e-9:
            nx = point(P, rect, th, z, corner(th + (1 if rising else -1)))
            cmds.append(f"L {f(nx[0])} {f(nx[1])}")
    return " ".join(cmds)


def M(p):
    return f"M {f(p[0])} {f(p[1])}"


def L(p):
    return f"L {f(p[0])} {f(p[1])}"


def outline(P, rect, z):
    return f"{M(point(P, rect, 0, z, 0))} {walk(P, rect, 0, 360, z)} Z"


def prism(P, rect, z0, z1):
    """Top face, the two visible side bands, the silhouette, the top-front edge, and the label anchor."""
    lt, ft, rt = point(P, rect, 135, z1), point(P, rect, 45, z1), point(P, rect, -45, z1)
    lb, fb, rb = point(P, rect, 135, z0), point(P, rect, 45, z0), point(P, rect, -45, z0)
    edge = f"{M(lt)} {walk(P, rect, 135, -45, z1)}"
    if rect.r == 0:
        edge += f" {M(ft)} {L(fb)}"
    n = 24
    poly = [point(P, rect, 135 + 180 * i / n, z1) for i in range(n + 1)]
    poly += [point(P, rect, -45 + 180 * i / n, z0) for i in range(n + 1)]
    return dict(
        top=outline(P, rect, z1),
        left=f"{M(lt)} {walk(P, rect, 135, 45, z1)} {L(fb)} {walk(P, rect, 45, 135, z0)} Z",
        right=f"{M(ft)} {walk(P, rect, 45, -45, z1)} {L(rb)} {walk(P, rect, -45, 45, z0)} Z",
        sil=f"{M(lt)} {walk(P, rect, 135, 315, z1)} {L(rb)} {walk(P, rect, -45, 135, z0)} Z",
        edge=edge,
        rx=rt[0],
        anchor=(rt[0], (rt[1] + rb[1]) / 2),
        poly=poly,
    )


# ---------------------------------------------------------------- parts


@dataclass
class Part:
    key: str
    name: str
    sub: str
    rect: Rect
    t: float
    kind: str = "slab"
    closed_z: float = 0
    level: int | None = None
    z: float = 0


def solid(P, rect, z0, z1, sk, tones, stroke, inner, role=True):
    pr = prism(P, rect, z0, z1)
    tag = ' data-role="silhouette"' if role else ""
    out = [f'<path{tag} d="{pr["sil"]}" fill="{sk["base"]}"/>']
    for path, tone in zip((pr["top"], pr["left"], pr["right"]), tones):
        if tone:
            out.append(f'<path d="{path}" fill="{tone}"/>')
    return pr, out


def finish(pr, stroke, inner, sw=1.2):
    return [f'<path d="{pr["edge"]}" fill="none" stroke="{inner}" stroke-width="0.8"/>',
            f'<path d="{pr["sil"]}" fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"/>']


def styles(sk, focal):
    return (sk["focal"] if focal else sk["shade"], sk["accent"] if focal else sk["sil"],
            sk["inner_acc"] if focal else sk["inner"])


WALL, FLOOR = 5, 3


def draw_part(P, p: Part, sk, focal: bool, uid: str):
    tones, stroke, inner = styles(sk, focal)
    z0, z1 = p.z, p.z + p.t
    if p.kind == "housing":
        # Back half only: silhouette, rim, cavity, and floor. housing_front() paints the
        # outer walls and the front rim after anything that sits inside.
        pr = prism(P, p.rect, z0, z1)
        ir = p.rect.inset(WALL)
        out = [f'<path data-role="silhouette" d="{pr["sil"]}" fill="{sk["base"]}"/>',
               f'<path d="{outline(P, p.rect, z1)}" fill="{sk["base"]}"/>']
        if tones[0]:
            out.append(f'<path d="{outline(P, p.rect, z1)}" fill="{tones[0]}"/>')
        out += [f'<path d="{outline(P, ir, z1)}" fill="{sk["base"]}"/>',
                f'<path d="{outline(P, ir, z1)}" fill="{sk["cavity"]}"/>',
                f'<clipPath id="{uid}-cavity"><path d="{outline(P, ir, z1)}"/></clipPath>',
                f'<g clip-path="url(#{uid}-cavity)"><path d="{outline(P, ir, z0 + FLOOR)}" fill="{sk["base"]}"/>'
                f'<path d="{outline(P, ir, z0 + FLOOR)}" fill="{sk["floor"]}"/>'
                f'<path d="{outline(P, ir, z0 + FLOOR)}" fill="none" stroke="{inner}" stroke-width="0.8"/></g>',
                f'<path d="{outline(P, ir, z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>',
                f'<path d="{M(point(P, p.rect, 135, z1))} {walk(P, p.rect, 135, 315, z1)}" fill="none" stroke="{stroke}" stroke-width="1.2" stroke-linejoin="round"/>']
        return pr, out
    pr, out = solid(P, p.rect, z0, z1, sk, tones, stroke, inner)
    r = p.rect
    if p.kind == "display":
        out.append(f'<path d="{outline(P, r.inset(4), z1)}" fill="{sk["screen"]}"/>')
        cx = (r.x0 + r.x1) / 2
        out.append(f'<path d="{outline(P, Rect(cx - 16, r.y0 + 12, cx + 16, r.y0 + 22, 5), z1)}" fill="{sk["island"]}"/>')
    elif p.kind == "battery":
        out.append(f'<path d="{outline(P, r.inset(8), z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
        out.append(f'<path d="{outline(P, Rect(r.x0 + 12, r.y0 + 4, r.x0 + 36, r.y0 + 10, 0), z1)}" fill="{sk["chip_top"]}"/>')
    elif p.kind == "board":
        out += finish(pr, stroke, inner)
        cam = Rect(r.x0 + 8, r.y0 + 8, r.x0 + 52, r.y0 + 52, 8)
        cpr, cbody = solid(P, cam, z1, z1 + 6, sk, sk["shade"], sk["sil"], sk["inner"], role=False)
        out += cbody + finish(cpr, sk["sil"], sk["inner"], 1)
        for lx, ly in ((r.x0 + 21, r.y0 + 21), (r.x0 + 39, r.y0 + 39)):
            lens = Rect(lx - 8, ly - 8, lx + 8, ly + 8, 8)
            out += [f'<path d="{prism(P, lens, z1 + 6, z1 + 9)["sil"]}" fill="{sk["lens"]}"/>',
                    f'<path d="{outline(P, lens.inset(3), z1 + 9)}" fill="none" stroke="{sk["lens_ring"]}" stroke-width="0.8"/>']
        for ax, ay, bx, by, h in ((64, 16, 100, 52, 3), (20, 64, 44, 92, 2), (64, 64, 108, 84, 2)):
            chip = prism(P, Rect(r.x0 + ax, r.y0 + ay, r.x0 + bx, r.y0 + by, 1), z1, z1 + h)
            out += [f'<path d="{chip["sil"]}" fill="{sk["chip_side"]}"/>', f'<path d="{chip["top"]}" fill="{sk["chip_top"]}"/>']
        return pr, out
    elif p.kind == "insert":
        for well in (Rect(SPK.x0 - 4, SPK.y0 - 4, SPK.x1 + 4, SPK.y1 + 4, SPK.r + 4),
                     Rect(CABLE.x0 - 3, CABLE.y0 - 3, CABLE.x1 + 3, CABLE.y1 + 3, 5)):
            out.append(f'<path d="{outline(P, well, z1)}" fill="{sk["well"]}" stroke="{inner}" stroke-width="0.8"/>')
    elif p.kind == "speaker":
        for zz in range(int(z0) + 10, int(z0 + p.t * 0.72), 8):
            out.append(f'<path d="{M(point(P, r, 135, zz))} {walk(P, r, 135, -45, zz)}" fill="none" stroke="{inner}" stroke-width="0.6"/>')
        out.append(f'<path d="{outline(P, r.inset(10), z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
        dot = Rect(r.x0 + 36, r.y0 + 36, r.x1 - 36, r.y1 - 36, 10)
        out.append(f'<path d="{outline(P, dot, z1)}" fill="{sk["accent"] if focal else sk["chip_top"]}"/>')
    elif p.kind == "cable":
        for k in (6, 11):
            out.append(f'<path d="{outline(P, r.inset(k, 4), z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
    elif p.kind == "lid":
        out.append(f'<path d="{outline(P, r.inset(14), z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        mark = Rect(cx - 14, cy - 14, cx + 14, cy + 14, 14)
        out.append(f'<path d="{outline(P, mark, z1)}" fill="none" stroke="{sk["sil"]}" stroke-width="1.2"/>')
        out.append(f'<path d="{outline(P, mark.inset(9), z1)}" fill="{sk["sil"]}"/>')
    out += finish(pr, stroke, inner)
    return pr, out


def housing_front(P, p: Part, sk, focal, buttons):
    """Outer walls and the front half of the rim, painted after the parts inside."""
    tones, stroke, inner = styles(sk, focal)
    z0, z1 = p.z, p.z + p.t
    ir = p.rect.inset(WALL)
    pr = prism(P, p.rect, z0, z1)
    rim = (f"{M(point(P, p.rect, 135, z1))} {walk(P, p.rect, 135, -45, z1)} "
           f"{L(point(P, ir, -45, z1))} {walk(P, ir, -45, 135, z1)} Z")
    walls = (f"{M(point(P, p.rect, 135, z1))} {walk(P, p.rect, 135, -45, z1)} "
             f"{L(point(P, p.rect, -45, z0))} {walk(P, p.rect, -45, 135, z0)} Z")
    out = [f'<path d="{walls}" fill="{sk["base"]}"/>', f'<path d="{rim}" fill="{sk["base"]}"/>']
    if tones[0]:
        out.append(f'<path d="{rim}" fill="{tones[0]}"/>')
    if tones[1]:
        out.append(f'<path d="{pr["left"]}" fill="{tones[1]}"/>')
    if tones[2]:
        out.append(f'<path d="{pr["right"]}" fill="{tones[2]}"/>')
    if buttons:
        r = p.rect
        for ya, yb in ((r.y0 + 60, r.y0 + 100), (r.y0 + 112, r.y0 + 132)):
            za, zb = z0 + p.t * 0.35, z0 + p.t * 0.75
            bar = [P.iso(r.x1 + 1.5, ya, zb), P.iso(r.x1 + 1.5, yb, zb), P.iso(r.x1 + 1.5, yb, za), P.iso(r.x1 + 1.5, ya, za)]
            out.append(f'<polygon points="{" ".join(f"{f(a)},{f(b)}" for a, b in bar)}" fill="{sk["base"]}" stroke="{inner}" stroke-width="0.8"/>')
    out.append(f'<path d="{M(point(P, ir, 135, z1))} {walk(P, ir, 135, -45, z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
    out.append(f'<path d="{pr["edge"]}" fill="none" stroke="{stroke}" stroke-width="1.2"/>')
    front = (f"{M(point(P, p.rect, 135, z1))} {L(point(P, p.rect, 135, z0))} "
             f"{walk(P, p.rect, 135, -45, z0)} {L(point(P, p.rect, -45, z1))}")
    out.append(f'<path d="{front}" fill="none" stroke="{stroke}" stroke-width="1.2" stroke-linejoin="round"/>')
    return out


# ---------------------------------------------------------------- layout


def levels_of(parts):
    idx, current, previous = [], -1, object()
    for p in parts:
        if p.level is None or p.level != previous:
            current += 1
        idx.append(current)
        previous = p.level if p.level is not None else object()
    return idx


def crosses(y, xa, xb, poly):
    xs = []
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 - y) * (y2 - y) < 0:
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return any(xs[i] < xb and xs[i + 1] > xa for i in range(0, len(xs) - 1, 2))


LABEL_PITCH = 36


def explode(parts, gap_k):
    """Assign z by level. Gap = max(gap_k x top-face height, 3 x part thickness), raised in
    4-unit steps until no leader crosses another part and no two labels sit closer than
    LABEL_PITCH. Raising the gap cannot fix two parts on one level, so that raises."""
    top_h = max((p.rect.x1 - p.rect.x0 + p.rect.y1 - p.rect.y0) / 2 for p in parts)
    tmax = max(p.t for p in parts if p.kind != "housing")
    gap = math.ceil(max(gap_k * top_h, 3 * tmax) / 4) * 4
    lv = levels_of(parts)
    while True:
        z = 0
        for k in range(max(lv) + 1):
            members = [p for p, level in zip(parts, lv) if level == k]
            for p in members:
                p.z = z
            z += max(p.t for p in members) + gap
        P = Proj(0, 0)
        prs = [prism(P, p.rect, p.z, p.z + p.t) for p in parts]
        right = max(pr["rx"] for pr in prs) + 48
        bad = False
        for i, pr in enumerate(prs):
            for j, q in enumerate(prs):
                if i != j and crosses(pr["anchor"][1], pr["anchor"][0] + 1, right, q["poly"]):
                    if lv[i] == lv[j]:
                        raise ValueError(f"leader of {parts[i].key} crosses {parts[j].key} on one level")
                    bad = True
        ys = sorted((pr["anchor"][1], lv[i], parts[i].key) for i, pr in enumerate(prs))
        for (y1, l1, k1), (y2, l2, k2) in zip(ys, ys[1:]):
            if y2 - y1 < LABEL_PITCH:
                if l1 == l2:
                    raise ValueError(f"labels of {k1} and {k2} collide on one level")
                bad = True
        if not bad:
            return gap
        gap += 4


# ---------------------------------------------------------------- figure


@dataclass
class Figure:
    slug: str
    title: str
    desc: str
    parts: list[Part]
    focus: str
    gap_k: float = 0.5
    buttons: bool = False
    caption: tuple[str, str] | None = None
    subtitle: str = ""
    cards: list[tuple[str, str, str, list[str] | str]] = field(default_factory=list)
    footer: str = ""


def label(sk, part, anchor, col_x, focal, motion):
    ax, ay = anchor
    cls = ' class="part-label"' if motion else ""
    lead = sk["lead_acc"] if focal else sk["lead"]
    dot = sk["accent"] if focal else sk["ink"]
    sub = sk["accent"] if focal else sk["muted"]
    return (f'<g data-role="label"{cls}>'
            f'<line data-role="leader" x1="{f(ax + 6)}" y1="{f(ay)}" x2="{f(col_x - 12)}" y2="{f(ay)}" stroke="{lead}" stroke-width="0.8"/>'
            f'<circle cx="{f(ax)}" cy="{f(ay)}" r="2" fill="{dot}"/>'
            f'<text data-role="name" x="{f(col_x)}" y="{f(ay - 1)}" fill="{sk["ink"]}" font-size="16" font-weight="600" font-family="\'Geist\', sans-serif">{part.name}</text>'
            f'<text x="{f(col_x)}" y="{f(ay + 15)}" fill="{sub}" font-size="10" font-family="\'Geist Mono\', monospace" letter-spacing="0.08em">{part.sub}</text></g>')


def build_svg(fig: Figure, skin: str, motion: bool, slug: str):
    sk = SKINS[skin]
    parts = fig.parts
    gap = explode(parts, fig.gap_k)
    P0 = Proj(0, 0)
    pts = [pt for p in parts for pt in prism(P0, p.rect, p.z, p.z + p.t)["poly"]]
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    lead_w, label_w = 64, 240
    left = math.floor((1000 - (maxx - minx + lead_w + label_w)) / 2 / 4) * 4
    ox, oy = round((left - minx) / 4) * 4, round((40 - miny) / 4) * 4
    P = Proj(ox, oy)
    vh = math.ceil((oy + maxy + (72 if fig.caption else 32)) / 4) * 4
    col_x = ox + maxx + lead_w

    lv = levels_of(parts)
    top_level = max(lv)
    steps = top_level + 1
    housing = parts[0] if parts[0].kind == "housing" else None

    def attrs(i, p):
        a = (f'data-part="{p.key}" data-name="{p.name}" data-rect="{p.rect.attr()}" '
             f'data-z="{f(p.z)}" data-t="{f(p.t)}" data-level="{lv[i]}"')
        if p.kind == "housing":
            a += ' data-kind="housing"'
        if p.key == fig.focus:
            a += " data-focal"
        if motion:
            a += f' data-closed-z="{f(p.closed_z)}"'
        return a

    out = [f'<rect width="100%" height="100%" fill="{sk["paper"]}"/>',
           f'<g data-exploded data-origin="{f(ox)} {f(oy)}" data-gap="{f(gap)}">']
    b, t = parts[0], parts[-1]
    trace = "".join(
        f'<line data-role="trace" x1="{f(point(P, b.rect, th, b.z + b.t)[0])}" y1="{f(point(P, b.rect, th, b.z + b.t)[1])}" '
        f'x2="{f(point(P, b.rect, th, t.z)[0])}" y2="{f(point(P, b.rect, th, t.z)[1])}" stroke="{sk["trace"]}" stroke-width="0.8" stroke-dasharray="4,3"/>'
        for th in (135, -45))

    pr0, body0 = draw_part(P, b, sk, b.key == fig.focus, f"{slug}-{b.key}")
    if motion:
        out.append(f'<g {attrs(0, b)}>' + "".join(body0) + "</g>")
        out.append(f'<g data-motion-item data-step="{steps}" data-reveal aria-label="{b.name} stays put; trace lines show where each part sat">'
                   + trace + label(sk, b, pr0["anchor"], col_x, b.key == fig.focus, False) + "</g>")
    else:
        out.append(trace)
        out.append(f'<g {attrs(0, b)}>' + "".join(body0) + label(sk, b, pr0["anchor"], col_x, b.key == fig.focus, False) + "</g>")

    def group(i):
        p = parts[i]
        focal = p.key == fig.focus
        pr, body = draw_part(P, p, sk, focal, f"{slug}-{p.key}")
        lab = label(sk, p, pr["anchor"], col_x, focal, motion)
        if not motion:
            return f'<g {attrs(i, p)}>' + "".join(body) + lab + "</g>"
        step = top_level - lv[i] + 1
        return (f'<g {attrs(i, p)} data-motion-item data-step="{step}" style="--lift:{f(p.z - p.closed_z)}px" '
                f'aria-label="{p.name} lifts clear">' + "".join(body) + lab + "</g>")

    if housing:
        for i in range(1, len(parts) - 1):
            out.append(group(i))
        out.append(f'<g data-part-front="{housing.key}">' + "".join(housing_front(P, housing, sk, housing.key == fig.focus, fig.buttons)) + "</g>")
        out.append(group(len(parts) - 1))
    else:
        for i in range(1, len(parts)):
            out.append(group(i))
    out.append("</g>")
    if fig.caption:
        cy = vh - 28
        out.append(f'<text x="{left}" y="{cy}" fill="{sk["muted"]}" font-size="8" font-family="\'Geist Mono\', monospace" letter-spacing="0.18em">{fig.caption[0]}</text>')
        out.append(f'<text x="{left + 104}" y="{cy}" fill="{sk["muted"]}" font-size="8.5" font-family="\'Geist\', sans-serif" font-style="italic">{fig.caption[1]}</text>')
    return "\n        ".join(out), vh, steps


# ---------------------------------------------------------------- pages

FONT_LINK = "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap"

MINIMAL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link href="{font}" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --color-paper:   {paper};
      --color-ink:     {ink};
      --color-muted:   {muted};
      --color-accent:  {accent};
      --font-sans:     'Geist', system-ui, sans-serif;
      --font-serif:    'Instrument Serif', serif;
      --font-mono:     'Geist Mono', ui-monospace, monospace;
    }}

    body {{
      font-family: var(--font-sans);
      background: var(--color-paper);
      color: var(--color-ink);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 3rem 2rem;
    }}

    .frame {{ max-width: 1200px; width: 100%; }}
    .diagram-container {{ width: 100%; overflow-x: auto; }}

    .eyebrow {{
      font-family: var(--font-mono);
      font-size: 0.66rem;
      font-weight: 500;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--color-muted);
      margin-bottom: 0.5rem;
    }}

    h1 {{
      font-family: var(--font-serif);
      font-size: clamp(1.5rem, 2.4vw + 0.75rem, 2rem);
      font-weight: 400;
      letter-spacing: -0.02em;
      line-height: 1.15;
      color: var(--color-ink);
      margin-bottom: 1.5rem;
    }}

    svg {{ width: 100%; min-width: 1000px; display: block; }}
    @media print {{
      .diagram-container {{ overflow-x: visible; }}
      svg {{ min-width: 0; }}
    }}
  </style>
</head>
<body>
  <div class="frame">
    <p class="eyebrow">Exploded axonometric · Diagram Design</p>
    <h1>{title}</h1>

    <div class="diagram-container">
      <svg viewBox="0 0 1000 {vh}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc">
        <title id="{slug}-title">{title}</title>
        <desc id="{slug}-desc">{desc}</desc>
        {body}
      </svg>
    </div>
  </div>
</body>
</html>
"""

FULL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link href="{font}" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{ --color-paper:#f5f5f5; --color-paper-2:#ececec; --color-ink:#2d3142; --color-muted:#4f5d75; --color-soft:#7a8399; --color-rule:rgba(45,49,66,0.12); --color-accent:#eb6c36; --color-link:#2e5aa8; --font-sans:'Geist',system-ui,sans-serif; --font-serif:'Instrument Serif',serif; --font-mono:'Geist Mono',ui-monospace,monospace; }}
    body {{ font-family: var(--font-sans); background: var(--color-paper); min-height: 100vh; padding: 3rem 2rem; color: var(--color-ink); }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    .header {{ margin-bottom: 2.5rem; }}
    .header-eyebrow {{ font-family: var(--font-mono); font-size: 0.66rem; font-weight: 500; letter-spacing: 0.18em; text-transform: uppercase; color: var(--color-muted); margin-bottom: 0.75rem; }}
    h1 {{ font-family: var(--font-serif); font-size: clamp(1.75rem, 3vw + 1rem, 2.5rem); font-weight: 400; letter-spacing: -0.02em; line-height: 1.1; margin-bottom: 0.5rem; }}
    .subtitle {{ font-size: 1rem; line-height: 1.55; color: var(--color-muted); max-width: 58ch; }}
    .diagram-container {{ overflow-x: auto; }}
    svg {{ width: 100%; min-width: 1000px; display: block; }}
    @media print {{ .diagram-container {{ overflow-x: visible; }} svg {{ min-width: 0; }} }}
    .cards {{ display: grid; grid-template-columns: 1.1fr 1fr 0.9fr; gap: 1rem; margin-top: 1.5rem; }}
    @media (max-width: 820px) {{ .cards {{ grid-template-columns: 1fr; }} }}
    .card {{ background: #fff; border-radius: 6px; border: 1px solid var(--color-rule); padding: 1.25rem; }}
    .card .eyebrow {{ font-family: var(--font-mono); font-size: 0.5rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--color-muted); margin-bottom: 0.5rem; }}
    .card-header {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.875rem; padding-bottom: 0.875rem; border-bottom: 1px solid rgba(45,49,66,0.08); }}
    .card-dot {{ width: 7px; height: 7px; border-radius: 50%; }}
    .card-dot.ink {{ background: var(--color-ink); }} .card-dot.muted {{ background: var(--color-muted); }} .card-dot.coral {{ background: var(--color-accent); }}
    .card h3 {{ font-size: 0.875rem; font-weight: 600; }}
    .card p, .card ul {{ color: var(--color-muted); font-size: 0.8125rem; line-height: 1.55; list-style: none; }}
    .card li {{ margin-bottom: 0.3rem; padding-left: 0.875rem; position: relative; }}
    .card li::before {{ content: '·'; position: absolute; left: 0.2rem; color: rgba(45,49,66,0.45); }}
    .footer {{ margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(45,49,66,0.10); font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.06em; color: var(--color-soft); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <p class="header-eyebrow">Exploded axonometric · Diagram Design</p>
      <h1>{title}</h1>
      <p class="subtitle">{subtitle}</p>
    </div>

    <div class="diagram-container">
      <svg viewBox="0 0 1000 {vh}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc">
        <title id="{slug}-title">{title}</title>
        <desc id="{slug}-desc">{desc}</desc>
        {body}
      </svg>
    </div>

    <div class="cards">
{cards}
    </div>

    <div class="footer">
      <span>{footer}</span>
      <span>example · diagram design</span>
    </div>
  </div>
</body>
</html>
"""

MOTION_CSS = """
    /* Static source is the exploded frame. Only an initialized enhancement assembles it.
       Parts travel straight up, so a vertical translate is the whole explode. */
    .motion-ready [data-motion-item][data-part] { opacity: 1; transform: translateY(var(--lift)); }
    .motion-ready:not([data-frame="start"]) [data-motion-item][data-part] { transition: transform var(--motion-step) var(--motion-ease); }
    .motion-ready [data-motion-item][data-part].is-visible,
    .motion-ready[data-frame="end"] [data-motion-item][data-part],
    .motion-ready[data-frame="static"] [data-motion-item][data-part] { transform: none; }
    .motion-ready [data-part] .part-label { opacity: 0; transition: none; }
    .motion-ready [data-part].is-visible .part-label { opacity: 1; transition: opacity var(--motion-fast) linear var(--motion-step); }
    .motion-ready[data-frame="end"] .part-label,
    .motion-ready[data-frame="static"] .part-label { opacity: 1; }
    .motion-ready [data-motion-item][data-reveal] { opacity: 0; transform: none; transition: none; }
    .motion-ready [data-motion-item][data-reveal].is-visible { opacity: 1; transition: opacity var(--motion-step) var(--motion-ease); }
    .motion-ready[data-frame="end"] [data-motion-item][data-reveal],
    .motion-ready[data-frame="static"] [data-motion-item][data-reveal] { opacity: 1; }
    html[data-motion="static"] .part-label { opacity: 1 !important; }
    html[data-motion="step"] .part-label { transition: none !important; }
    @media (prefers-reduced-motion: reduce) { .part-label { opacity: 1 !important; } }
    @media print { .part-label { opacity: 1 !important; } }
"""


def animated_page(fig: Figure, slug: str, body: str, vh: int, steps: int) -> str:
    """Start from template-motion.html so the controller, controls, and fallbacks stay canonical."""
    src = MOTION_TEMPLATE.read_text(encoding="utf-8")
    src = src.replace("<title>Motion diagram template</title>", f"<title>{fig.title}</title>", 1)
    src = src.replace("--motion-step: 480ms;", "--motion-step: 600ms;", 1)
    src = src.replace("--motion-hold: 720ms;", "--motion-hold: 900ms;", 1)
    src = src.replace("--motion-total: 3600ms;", f"--motion-total: {steps * 900}ms;", 1)
    src = src.replace("min-width: 960px;", "min-width: 1000px;", 1)
    src = src.replace("  </style>", MOTION_CSS + "  </style>", 1)
    start = src.index("  <!-- Replace template-motion")
    end = src.index("    <div data-motion-controls")
    main = (f'  <main data-motion-root data-motion-mode="reveal" data-step-count="{steps}" data-step-current="{steps}" data-frame="static" data-static-frame="complete">\n'
            f'    <p class="eyebrow">Exploded axonometric · Optional motion</p>\n'
            f'    <h1>{fig.title}</h1>\n\n'
            f'    <div class="diagram-container">\n'
            f'      <svg viewBox="0 0 1000 {vh}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc">\n'
            f'        <title id="{slug}-title">{fig.title}</title>\n'
            f'        <desc id="{slug}-desc">{fig.desc}</desc>\n'
            f'        {body}\n'
            f'      </svg>\n'
            f'    </div>\n\n')
    src = src[:start] + main + src[end:]
    src = re.sub(r'Step <span data-motion-step-label>\d+</span> of \d+',
                 f'Step <span data-motion-step-label>{steps}</span> of {steps}', src, count=1)
    src = src.replace("The complete final diagram is shown above.", "The complete exploded diagram is shown above.", 1)
    return src


def cards_html(cards):
    out = []
    for eyebrow, dot, title, body in cards:
        inner = f"<p>{body}</p>" if isinstance(body, str) else "<ul>" + "".join(f"<li>{item}</li>" for item in body) + "</ul>"
        eb = f'<p class="eyebrow">{eyebrow}</p>' if eyebrow else ""
        out.append(f'      <div class="card">\n        {eb}\n        <div class="card-header"><span class="card-dot {dot}"></span><h3>{title}</h3></div>\n        {inner}\n      </div>')
    return "\n".join(out)


# ---------------------------------------------------------------- content

def app_stack():
    a = 200
    return [Part("data", "Data", "postgres, object store", Rect(0, 0, a, a, 12), t=16, closed_z=0),
            Part("logic", "Logic", "api, workers, queue", Rect(0, 0, a, a, 12), t=16, closed_z=16),
            Part("interface", "Interface", "web app, mobile", Rect(0, 0, a, a, 12), t=16, closed_z=32)]


PW, PD, PR = 140, 280, 24


def phone():
    body = Rect(0, 0, PW, PD, PR)
    return [Part("housing", "Housing", "aluminium frame", body, t=20, kind="housing", closed_z=0),
            Part("board", "Logic board", "soc, cameras", Rect(8, 8, PW - 8, 112, 4), t=4, kind="board", closed_z=3, level=1),
            Part("battery", "Battery", "li-ion cell", Rect(10, 136, PW - 10, PD - 12, 6), t=8, kind="battery", closed_z=3, level=1),
            Part("display", "Display", "oled, cover glass", body, t=6, kind="display", closed_z=20)]


BW, BD = 180, 180
SPK = Rect(36, 52, 128, 144, 46)
CABLE = Rect(138, 40, 170, 72, 4)


def unboxing():
    return [Part("box", "Box", "rigid board", Rect(0, 0, BW, BD, 4), t=72, kind="housing", closed_z=0),
            Part("insert", "Insert", "moulded pulp", Rect(6, 6, BW - 6, BD - 6, 2), t=12, kind="insert", closed_z=3),
            Part("cable", "Cable", "usb-c, 1 m", CABLE, t=14, kind="cable", closed_z=9, level=2),
            Part("speaker", "Speaker", "the product", SPK, t=60, kind="speaker", closed_z=9, level=2),
            Part("lid", "Lid", "printed sleeve", Rect(-3, -3, BW + 3, BD + 3, 6), t=28, kind="lid", closed_z=48)]


FIGURES = {
    "exploded": lambda: Figure(
        slug="exploded",
        title="App stack · Three layers, one product",
        desc="Exploded view of a three-layer app stack: data at the base, logic in the middle, interface on top, with logic as the focal layer.",
        parts=app_stack(), focus="logic",
        caption=("FOCAL LAYER", "Logic is where the product decisions live; the other two layers are swappable."),
        subtitle="Three layers pulled apart along one axis. The middle one carries the product, and the other two can be swapped.",
        cards=[("The headline", "coral", "Logic is the layer that pays rent", "Swapping the database is a migration. Swapping the interface is a redesign. Rewriting the logic is a different product, so that layer gets the accent."),
               ("", "ink", "Reading the explode", ["Bottom layer stays put", "Equal gaps, one axis", "Dashed lines trace the outer corners", "Labels sit in one column"]),
               ("", "muted", "Why only three", "A stack this small reads at a glance. Past five parts the explode gets tall and the labels crowd; split it into two figures.")],
        footer="app stack · exploded axonometric"),
    "exploded-phone": lambda: Figure(
        slug="exploded-phone",
        title="Phone teardown · What sits under the glass",
        desc="Exploded view of a phone: the display lifts off the housing to show the logic board and battery inside, with the logic board as the focal part.",
        parts=phone(), focus="board", gap_k=0.75, buttons=True,
        subtitle="The display comes off first. Underneath, the logic board and battery share one level inside the housing, so they lift together.",
        cards=[("The headline", "coral", "The board is the phone", "Cameras, radios and the system chip all live on one small board. Everything else holds it, powers it, or shows its output."),
               ("", "ink", "How it was drawn", ["Rounded corners project as quarter ellipses", "The housing is a tray, so its front walls paint last", "Parts on one level explode together", "Gap widened so the display clears the board"]),
               ("", "muted", "Four parts", "A real teardown has dozens of parts. The diagram keeps the four a reader needs and drops the screws.")],
        footer="phone · exploded axonometric"),
    "exploded-unboxing": lambda: Figure(
        slug="exploded-unboxing",
        title="Unboxing · What you see, in the order you see it",
        desc="Exploded view of product packaging: printed lid, the speaker and its cable, the moulded insert that holds them, and the rigid box, with the speaker as the focal part.",
        parts=unboxing(), focus="speaker",
        subtitle="Read it top down and it is the unboxing: lid, product, insert, box. The product and its cable share a level because they sit side by side.",
        cards=[("The headline", "coral", "The product is the reveal", "Everything above the speaker is a lid and everything below it is a cradle. The accent marks the speaker because the packaging exists to present it."),
               ("", "ink", "Reading the explode", ["Lid telescopes over the box walls", "Insert wells match the parts they hold", "Cable and speaker lift as one level", "Box stays put"]),
               ("", "muted", "When to use it", "Packaging reviews, supplier briefs, and launch pages. For a list of what is in the box, a table is faster.")],
        footer="unboxing · exploded axonometric"),
}
ANIMATED = ("exploded-phone", "exploded-unboxing")


def render_all() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for name, make in FIGURES.items():
        for variant, skin in (("", "light"), ("-dark", "dark"), ("-full", "light")):
            fig = make()
            slug = f"{name}{variant}"
            body, vh, _ = build_svg(fig, skin, False, slug)
            sk = SKINS[skin]
            if variant == "-full":
                html = FULL.format(title=fig.title, font=FONT_LINK, slug=slug, desc=fig.desc, vh=vh, body=body,
                                   subtitle=fig.subtitle, cards=cards_html(fig.cards), footer=fig.footer)
            else:
                html = MINIMAL.format(title=fig.title, font=FONT_LINK, slug=slug, desc=fig.desc, vh=vh, body=body,
                                      **{k: sk[k] for k in ("paper", "ink", "muted", "accent")})
            files[ASSETS / f"example-{slug}.html"] = html
        if name in ANIMATED:
            fig = make()
            slug = f"{name}-animated"
            body, vh, steps = build_svg(fig, "light", True, slug)
            files[ASSETS / f"example-{slug}.html"] = animated_page(fig, slug, body, vh, steps)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if any generated example differs from disk")
    args = parser.parse_args()
    files = render_all()
    stale = []
    for path, html in files.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != html:
            if args.check:
                stale.append(path.relative_to(ROOT).as_posix())
            else:
                path.write_text(html, encoding="utf-8")
                print(f"wrote {path.relative_to(ROOT).as_posix()}")
    if stale:
        print("stale exploded examples (run scripts/build-exploded-examples.py):")
        for name in stale:
            print(f"  - {name}")
        return 1
    if args.check:
        print(f"OK exploded examples: {len(files)} files up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
