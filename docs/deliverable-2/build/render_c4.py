#!/usr/bin/env python3
"""
Collision-free C4 diagram renderer for the Executive Review II deliverable.

Why this exists
---------------
Mermaid's C4 renderer draws every Rel() label at its edge midpoint with no
collision avoidance, so labels land on top of node boxes. That cannot be fixed
from Mermaid source. This renderer parses the same Mermaid C4 sources (content
fidelity guaranteed), lays the diagram out on an explicit grid in inches, and
places each edge label by search, accepting a position only when its bounding
box intersects no node box and no previously placed label.

Outputs per diagram: a 300 dpi PNG (for review) and a vector PDF (for LaTeX).

Every run prints a machine-readable collision report. It exits non-zero if any
diagram reports COLLISIONS != 0.
"""

from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from matplotlib.path import Path as MPath

ROOT = Path(__file__).resolve().parent.parent
FIGDIR = ROOT / "figures"
BUILDDIR = ROOT / "build"

# A4 with 1in margins (the LaTeX document geometry): the box the figure must fill.
TEXT_WIDTH_IN = 469.8 / 72.0
TEXT_HEIGHT_IN = 650.4 / 72.0

# ---------------------------------------------------------------- typography
FS_LABEL = 8.0
FS_TECH = 6.0
FS_DESC = 6.5
FS_EDGE = 6.0
FS_EDGE_TECH = 5.5
FS_TITLE = 11.0
FS_BOUNDARY = 7.5

LH_LABEL = 0.140
LH_TECH = 0.105
LH_DESC = 0.104
LH_EDGE = 0.098
LH_EDGE_TECH = 0.092

CHAR_W_LABEL = 0.066   # inches per char, 8pt bold, deliberately generous
CHAR_W_DESC = 0.048    # inches per char, 6.5pt
CHAR_W_EDGE = 0.044    # inches per char, 6pt
CHAR_W_EDGE_TECH = 0.040

BOX_PAD = 0.085
NODE_MARGIN = 0.26     # gap between node boxes in a row
ROW_GAP = 1.18         # vertical gap between rows (room for stacked edge labels)

# ---------------------------------------------------------------- C4 palette
STYLE = {
    "person":    dict(face="#08427B", edge="#052E56", text="white"),
    "system":    dict(face="#1168BD", edge="#0B4F8A", text="white"),
    "external":  dict(face="#8A8A8A", edge="#6B6B6B", text="white"),
    "container": dict(face="#438DD5", edge="#2E6BA8", text="white"),
    "component": dict(face="#85BBF0", edge="#5E93C4", text="#0B2A45"),
}

KIND_OF = {
    "Person": "person", "Person_Ext": "external",
    "System": "system", "System_Ext": "external", "SystemDb": "system",
    "Container": "container", "ContainerDb": "container", "ContainerQueue": "container",
    "Component": "component", "ComponentDb": "component",
}


def wrap_chars(width_in: float, char_w: float) -> int:
    return max(8, int(width_in / char_w))


def wrap(text: str, width_in: float, char_w: float) -> list[str]:
    if not text:
        return []
    return textwrap.wrap(text, width=wrap_chars(width_in, char_w)) or [text]


# ------------------------------------------------------------------ parsing
def split_args(s: str) -> list[str]:
    """Split on top-level commas, respecting double quotes."""
    out, cur, in_q = [], "", False
    for ch in s:
        if ch == '"':
            in_q = not in_q
            cur += ch
        elif ch == "," and not in_q:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def parse_call(line: str):
    """`Kind(arg, ...)` -> (Kind, args). Quote-aware bracket matching."""
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(", line)
    if not m:
        return None, None
    start = line.index("(")
    depth, in_q = 0, False
    for i in range(start, len(line)):
        ch = line[i]
        if ch == '"':
            in_q = not in_q
        elif not in_q:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return m.group(1), split_args(line[start + 1:i])
    return None, None


def parse_mmd(path: Path):
    title = ""
    nodes: dict[str, dict] = {}
    order: list[str] = []
    edges: list[dict] = []
    boundaries: list[dict] = []
    stack: list[dict] = []

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        if line.startswith("title "):
            title = line[6:].strip()
            continue
        if line == "}":
            if stack:
                stack.pop()
            continue
        if line.startswith("UpdateLayoutConfig") or line.startswith("UpdateElementStyle") \
                or line.startswith("UpdateRelStyle"):
            continue

        name, args = parse_call(line)
        if name is None:
            continue
        if name == "Rel":
            if len(args) >= 3:
                edges.append(dict(src=args[0], dst=args[1],
                                  label=unquote(args[2]),
                                  tech=unquote(args[3]) if len(args) > 3 else ""))
            continue
        if name.endswith("Boundary"):
            b = dict(alias=args[0], label=unquote(args[1]) if len(args) > 1 else "",
                     children=[])
            boundaries.append(b)
            stack.append(b)
            continue
        if name in KIND_OF and len(args) >= 2:
            alias = args[0]
            nodes[alias] = dict(
                alias=alias, kind=KIND_OF[name], mermaid=name,
                label=unquote(args[1]),
                tech=unquote(args[2]) if len(args) > 2 else "",
                desc=unquote(args[3]) if len(args) > 3 else "",
                boundary=stack[-1]["alias"] if stack else None,
            )
            order.append(alias)
            if stack:
                stack[-1]["children"].append(alias)
    return dict(title=title, nodes=nodes, order=order, edges=edges, boundaries=boundaries)


# ------------------------------------------------------------------ geometry
def node_height(n: dict, w: float) -> float:
    h = 2 * BOX_PAD
    h += len(wrap(n["label"], w - 2 * BOX_PAD, CHAR_W_LABEL)) * LH_LABEL
    if n["tech"]:
        h += len(wrap(n["tech"], w - 2 * BOX_PAD, CHAR_W_DESC)) * LH_TECH
    if n["desc"]:
        h += len(wrap(n["desc"], w - 2 * BOX_PAD, CHAR_W_DESC)) * LH_DESC
    return max(h, 0.55)


def rects_intersect(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def seg_hits_rect(p, q, r, samples=26) -> bool:
    for i in range(samples + 1):
        t = i / samples
        x = p[0] + (q[0] - p[0]) * t
        y = p[1] + (q[1] - p[1]) * t
        if r[0] < x < r[2] and r[1] < y < r[3]:
            return True
    return False


def path_clear(path, obstacles) -> bool:
    for i in range(len(path) - 1):
        for r in obstacles:
            if seg_hits_rect(path[i], path[i + 1], r):
                return False
    return True


def exit_point(rect, cx, cy, toward):
    """Where a ray from (cx,cy) towards `toward` leaves `rect`."""
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    cands = []
    if dx > 0:
        cands.append((rect[2] - cx) / dx)
    elif dx < 0:
        cands.append((rect[0] - cx) / dx)
    if dy > 0:
        cands.append((rect[3] - cy) / dy)
    elif dy < 0:
        cands.append((rect[1] - cy) / dy)
    ts = [t for t in cands if t > 0]
    if not ts:
        return cx, cy
    t = min(ts)
    return cx + dx * t, cy + dy * t


def inflate(r, pad):
    return (r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad)


def count_hits(path, obstacles) -> int:
    n = 0
    for i in range(len(path) - 1):
        for r in obstacles:
            if seg_hits_rect(path[i], path[i + 1], r):
                n += 1
                break
    return n


def path_len(path) -> float:
    return sum(abs(path[i + 1][0] - path[i][0]) + abs(path[i + 1][1] - path[i][1])
               for i in range(len(path) - 1))


def auto_route(p0, p1, obstacles, bounds, chan_x=(), chan_y=()):
    """Pick the candidate route with the fewest node-box hits, then the shortest.

    Lane candidates include the layout's own column and row gutters, which are the
    natural routing channels, plus fractions of the figure width as a fallback.
    """
    x0, y0, x1, y1 = bounds
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    cands = [
        [p0, p1],
        [p0, (p0[0], p1[1]), p1],
        [p0, (p1[0], p0[1]), p1],
        [p0, (mx, p0[1]), (mx, p1[1]), p1],
        [p0, (p0[0], my), (p1[0], my), p1],
    ]
    lanes_x = list(chan_x) + [x0 + 0.14, x1 - 0.14, x0 + 0.44, x1 - 0.44, mx - 0.9, mx + 0.9]
    lanes_x += [x0 + (x1 - x0) * f for f in (0.14, 0.24, 0.34, 0.44, 0.56, 0.66, 0.76, 0.86)]
    for lane in lanes_x:
        cands.append([p0, (lane, p0[1]), (lane, p1[1]), p1])
    lanes_y = list(chan_y) + [y0 + 0.14, y1 - 0.14, y0 + (y1 - y0) * 0.5]
    for lane in lanes_y:
        cands.append([p0, (p0[0], lane), (p1[0], lane), p1])
    # two-channel doglegs: slide into a column gutter, travel it, then cross on a row gutter
    for gx in chan_x:
        for gy in chan_y:
            cands.append([p0, (gx, p0[1]), (gx, gy), (p1[0], gy), p1])
            cands.append([p0, (p0[0], gy), (gx, gy), (gx, p1[1]), p1])

    straight = path_len([p0, p1])
    best, best_key = None, None
    for c in cands:
        if path_len(c) > 3.0 * straight + 2.0:
            continue
        key = (count_hits(c, obstacles), path_len(c))
        if best_key is None or key < best_key:
            best, best_key = c, key
    return best if best else [p0, p1]


# ------------------------------------------------------------------- layout
LAYOUT = {
    "c4-level1-context": dict(
        width=6.4,
        rows=[["analyst", "decisionMaker", "indigenous", "operator"],
              ["platform"],
              ["copernicus", "ideam", "unodc", "govSystems"]],
        centered={"platform": 3.4},
    ),
    "c4-level2-containers": dict(
        width=7.4,
        rows=[["copernicus", "analyst", "decisionMaker", "govSystems"],
              ["ac01", "ac02", "ac03", "ac04"],
              ["ac08", "ac07", "ac06", "ac05"],
              ["tn03", "tn06", "tn04", "tn05", "ac09"]],
        boundary_rows={"platform": [1, 2, 3]},
    ),
    "c4-level3-components": dict(
        width=6.8,
        rows=[["ac01", "ac02", "ac03"],
              ["ac06", "ac05", "ac04"],
              ["tn03", "tn06", "tn04", "ac08", "ac09"]],
        boundary_rows={"pipeline": [0, 1]},
    ),
}


def build_layout(spec_key: str, model: dict):
    """Rows are solved downward from y=0, then shifted into the positive axis box."""
    spec = LAYOUT[spec_key]
    W = spec["width"]
    side = 0.30
    usable = W - 2 * side
    nodes = model["nodes"]

    positions: dict[str, tuple] = {}
    row_bands: list[tuple[float, float]] = []

    y_top = 0.0
    for row in spec["rows"]:
        n = len(row)
        centered_w = spec.get("centered", {}).get(row[0]) if n == 1 else None
        bw = centered_w if centered_w else (usable - (n - 1) * NODE_MARGIN) / n
        bh = max(node_height(nodes[a], bw) for a in row)
        band_top, band_bot = y_top, y_top - bh
        for c_i, alias in enumerate(row):
            x0 = side + (usable - bw) / 2 if n == 1 else side + c_i * (bw + NODE_MARGIN)
            positions[alias] = (x0, band_bot, x0 + bw, band_bot + bh)
        row_bands.append((band_top, band_bot))
        y_top = band_bot - ROW_GAP

    # Shift everything so the content lives inside [0, H] instead of below zero.
    y_min = min(r[1] for r in positions.values())
    shift = 0.44 - y_min
    positions = {k: (r[0], r[1] + shift, r[2], r[3] + shift) for k, r in positions.items()}
    H = max(r[3] for r in positions.values()) + 0.92

    brects = {}
    for b in model["boundaries"]:
        idxs = spec.get("boundary_rows", {}).get(b["alias"])
        if idxs is None:
            continue
        kids = [positions[a] for a in b["children"] if a in positions]
        if not kids:
            continue
        xs0 = min(k[0] for k in kids) - 0.24
        xs1 = max(k[2] for k in kids) + 0.24
        ys1 = max(row_bands[i][0] for i in idxs) + shift + 0.32
        ys0 = min(row_bands[i][1] for i in idxs) + shift - 0.18
        brects[b["alias"]] = (xs0, ys0, xs1, ys1, b["label"])
    chan_x = set()
    for row in spec["rows"]:
        xs = sorted(positions[a] for a in row if a in positions)
        for i in range(len(xs) - 1):
            chan_x.add((xs[i][2] + xs[i + 1][0]) / 2)
    chan_y = set()
    for i in range(len(row_bands) - 1):
        chan_y.add((row_bands[i][1] + row_bands[i + 1][0]) / 2 + shift)
    return W, H, positions, brects, sorted(chan_x), sorted(chan_y)


def render(spec_key: str, model: dict, out_stem: Path):
    W, H, pos, brects, chan_x, chan_y = build_layout(spec_key, model)
    fig = plt.figure(figsize=(W, H), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")

    if model["title"]:
        ax.text(W / 2, H - 0.26, model["title"], ha="center", va="center",
                fontsize=FS_TITLE, fontweight="bold", color="#1B1B1B")

    node_rects = {a: r for a, r in pos.items()}
    obstacles = [inflate(r, 0.035) for r in node_rects.values()]

    # The boundary title strip must stay label-free too: labels were covering it.
    title_obs = []
    for _alias, (bx0, _by0, bx1, by1, lab) in brects.items():
        tw = len(lab) * 0.070 + 0.14
        cx = (bx0 + bx1) / 2
        cy = by1 - 0.14
        title_obs.append((cx - tw / 2, cy - 0.115, cx + tw / 2, cy + 0.115))

    # boundaries first (behind everything)
    for _alias, (x0, y0, x1, y1, lab) in brects.items():
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=True,
                               facecolor="#F4F7FA", edgecolor="#9DB2C4",
                               linestyle=(0, (5, 4)), linewidth=1.1, zorder=1))
        ax.text((x0 + x1) / 2, y1 - 0.14, lab, ha="center", va="center",
                fontsize=FS_BOUNDARY, fontweight="bold", color="#5A6B7B", zorder=2)

    # node boxes
    for alias, r in pos.items():
        n = model["nodes"][alias]
        st = STYLE[n["kind"]]
        ax.add_patch(FancyBboxPatch(
            (r[0], r[1]), r[2] - r[0], r[3] - r[1],
            boxstyle="round,pad=0,rounding_size=0.07",
            facecolor=st["face"], edgecolor=st["edge"], linewidth=1.0, zorder=3))
        cx = (r[0] + r[2]) / 2
        y = r[3] - BOX_PAD - LH_LABEL / 2
        for ln in wrap(n["label"], (r[2] - r[0]) - 2 * BOX_PAD, CHAR_W_LABEL):
            ax.text(cx, y, ln, ha="center", va="center", fontsize=FS_LABEL,
                    fontweight="bold", color=st["text"], zorder=4)
            y -= LH_LABEL
        if n["tech"]:
            for ln in wrap(n["tech"], (r[2] - r[0]) - 2 * BOX_PAD, CHAR_W_DESC):
                ax.text(cx, y, ln, ha="center", va="center", fontsize=FS_TECH,
                        style="italic", color=st["text"], alpha=0.92, zorder=4)
                y -= LH_TECH
        for ln in wrap(n["desc"], (r[2] - r[0]) - 2 * BOX_PAD, CHAR_W_DESC):
            ax.text(cx, y, ln, ha="center", va="center", fontsize=FS_DESC,
                    color=st["text"], alpha=0.92, zorder=4)
            y -= LH_DESC

    # ---- route edges
    bounds = (0.06, 0.06, W - 0.06, H - 0.06)
    routes = []
    for e in model["edges"]:
        if e["src"] not in pos or e["dst"] not in pos:
            continue
        r0, r1 = pos[e["src"]], pos[e["dst"]]
        c0 = ((r0[0] + r0[2]) / 2, (r0[1] + r0[3]) / 2)
        c1 = ((r1[0] + r1[2]) / 2, (r1[1] + r1[3]) / 2)
        others = [obstacles[i] for i, a in enumerate(pos) if a not in (e["src"], e["dst"])] + title_obs
        raw = auto_route(c0, c1, others, bounds, chan_x, chan_y)
        pts = list(raw)
        pts[0] = exit_point(r0, c0[0], c0[1], pts[1])
        pts[-1] = exit_point(r1, c1[0], c1[1], pts[-2])
        routes.append((e, pts))

    for e, pts in routes:
        ax.add_patch(FancyArrowPatch(
            path=MPath(pts), arrowstyle="-|>", mutation_scale=9,
            linewidth=0.85, color="#54606B", zorder=5,
            shrinkA=0, shrinkB=0, joinstyle="miter"))

    # ---- greedy label placement, longest first
    def abox(cx, cy, lines, tech):
        w = max((len(t) * CHAR_W_EDGE for t in lines), default=0.1)
        if tech:
            w = max(w, len(tech) * CHAR_W_EDGE_TECH)
        h = len(lines) * LH_EDGE + (LH_EDGE_TECH if tech else 0)
        return (cx - w / 2 - 0.035, cy - h / 2 - 0.03, cx + w / 2 + 0.035, cy + h / 2 + 0.03), w

    placed: list[tuple] = []
    collisions: list[str] = []
    ordered = sorted(range(len(routes)),
                     key=lambda i: (-len(routes[i][0]["label"]), i))

    for idx in ordered:
        e, pts = routes[idx]
        lines = wrap(e["label"], 99, CHAR_W_EDGE)
        tech = e["tech"]
        # anchor: midpoint of the longest segment
        segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        L = [((s[0][0] - s[1][0]) ** 2 + (s[0][1] - s[1][1]) ** 2) for s in segs]
        k = max(range(len(segs)), key=lambda i: L[i])
        a, b = segs[k]
        ux, uy = b[0] - a[0], b[1] - a[1]
        nrm = max((ux * ux + uy * uy) ** 0.5, 1e-9)
        nx, ny = -uy / nrm, ux / nrm

        best, bestbox = None, None
        offs = [(0.0, 0.0)]
        for k in range(1, 6):
            for v in (0.20 * k, -0.20 * k):
                offs.append((0.0, v))
                offs.append((0.20, v))
                offs.append((-0.20, v))
        for h in (0.20, -0.20, 0.42, -0.42, 0.66, -0.66):
            offs.append((h, 0.0))
        for t in (0.5, 0.44, 0.56, 0.38, 0.62, 0.30, 0.70):
            bx = a[0] + ux * t
            by = a[1] + uy * t
            for o_p, o_v in offs:
                cx = bx + nx * o_p
                cy = by + ny * o_p + o_v
                box, _w = abox(cx, cy, lines, tech)
                if box[0] < bounds[0] or box[2] > bounds[2] or box[1] < bounds[1] or box[3] > bounds[3]:
                    continue
                if any(rects_intersect(box, o) for o in obstacles + title_obs):
                    continue
                if any(rects_intersect(box, p) for p in placed):
                    continue
                best, bestbox = (cx, cy), box
                break
            if best:
                break
        if best is None:
            collisions.append(f"{e['src']}->{e['dst']} '{e['label']}'")
            cx, cy = a[0] + ux * 0.5, a[1] + uy * 0.5
            bestbox, _w = abox(cx, cy, lines, tech)
            best = (cx, cy)
        placed.append(bestbox)
        lines = wrap(e["label"], 99, CHAR_W_EDGE)
        y = best[1] + ((len(lines) - 1) * LH_EDGE + (LH_EDGE_TECH if tech else 0)) / 2
        ax.text(best[0], best[1], "\n".join(lines + ([tech] if tech else [])),
                ha="center", va="center", fontsize=FS_EDGE, color="#2B3A47", zorder=6,
                linespacing=1.28,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.88,
                          boxstyle="round,pad=0.10"))

    # arrows crossing unrelated nodes (reported, not fatal)
    crossings = 0
    crossing_edges = []
    for e, pts in routes:
        others = [pos[a] for a in pos if a not in (e["src"], e["dst"])]
        hit = False
        for i in range(len(pts) - 1):
            for r in others:
                if seg_hits_rect(pts[i], pts[i + 1], r):
                    hit = True
                    break
            if hit:
                break
        if hit:
            crossings += 1
            crossing_edges.append(f"{e['src']}->{e['dst']}")

    scale = min(TEXT_WIDTH_IN / W, TEXT_HEIGHT_IN / H)
    fig.savefig(out_stem.with_suffix(".png"), dpi=300,
                facecolor="white", bbox_inches=None, pad_inches=0)
    fig.savefig(out_stem.with_suffix(".pdf"), facecolor="white")
    plt.close(fig)

    print(f"DIAGRAM={spec_key}")
    print(f"  nodes={len(pos)} edges={len(routes)} labels={len(routes)}")
    print(f"  COLLISIONS={len(collisions)}")
    for c in collisions:
        print(f"    UNPLACED {c}")
    print(f"  arrows_through_nodes={crossings}")
    for ce in crossing_edges:
        print(f"    CROSSES {ce}")
    print(f"  figure_in={W:.2f}x{H:.2f} aspect_w_h={W / H:.3f}")
    print(f"  png_px={int(W * 300)}x{int(H * 300)}")
    print(f"  on_page_scale={scale:.3f} body_text_pt={FS_DESC * scale:.2f}")
    return len(collisions), crossings


def main() -> int:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for stem in ("c4-level1-context", "c4-level2-containers", "c4-level3-components"):
        src = BUILDDIR / f"{stem}.mmd"
        if not src.exists():
            print(f"MISSING SOURCE {src}", file=sys.stderr)
            return 2
        model = parse_mmd(src)
        c, _ = render(stem, model, FIGDIR / stem)
        total += c
    print(f"TOTAL_COLLISIONS={total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
