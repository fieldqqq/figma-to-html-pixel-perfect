#!/usr/bin/env python3
"""Extract every icon the page actually draws, straight out of the page SVG export.

No API call, no quota. The SVG export of the page frame contains every vector on that
page in page coordinates; the node JSON tells you where each icon sits. Intersect the two.

This exists so that "the icon library is behind a rate limit" is never a reason to draw an
icon by hand (§0.5, §6.5.5.1).

A path's bounding box is computed by flattening its curves — never by taking min/max of the
numbers in `d`, which is wrong for curves and relative commands and fails silently.

`visible:true, opacity:1` does not mean "renders". A component's placeholder artwork is often
left in the tree and painted over by a photo added later in the same frame. Those vectors are
skipped here: a later sibling with an opaque fill that covers the rect wins (painter's order).

Usage:
    python3 figma_icons.py --svg design/exports/page.svg --nodes figma/nodes \
        --out design/exports/icons [--min 10 --max 220]

Tip: strip the base64 image payloads from the SVG first; it makes it ~100x smaller.
"""
import argparse, glob, json, math, os, pathlib, re, xml.etree.ElementTree as ET

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
# What a Figma node may be made of.
VECTORISH = {"VECTOR", "BOOLEAN_OPERATION", "ELLIPSE", "RECTANGLE", "LINE",
             "REGULAR_POLYGON", "STAR"}
# ...but only these carry the drawn outline of an icon. A subtree of nothing but plain
# ELLIPSE/RECTANGLE is a shape the browser draws in CSS (carousel dots, a ring, a divider),
# not an icon you can export.
GLYPHISH = {"VECTOR", "BOOLEAN_OPERATION", "REGULAR_POLYGON", "STAR"}
# Figma's SVG export does not emit everything as <path>. An icon whose circle is a <circle>
# comes out empty if you only look at paths.
SHAPES = {"path", "rect", "circle", "ellipse", "line", "polygon", "polyline"}
TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def path_bbox(d):
    """Flatten the path and return (x0,y0,x1,y1). Curves are sampled, not guessed."""
    pts = path_points(d)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def path_points(d):
    """Flatten the path to a point list. Curves are sampled, not guessed."""
    xs, ys = [], []
    cmd, nums, cur, start = None, [], (0.0, 0.0), (0.0, 0.0)

    def add(p):
        xs.append(p[0]); ys.append(p[1])

    def bez(p0, p1, p2, p3, n=16):
        for i in range(n + 1):
            t = i / n
            u = 1 - t
            add((u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
                 u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]))

    def flush():
        nonlocal cur, start, nums
        if cmd is None:
            return
        c, rel = cmd.upper(), cmd.islower()
        i = 0
        while True:
            if c == "M":
                if i + 2 > len(nums): break
                p = (nums[i], nums[i+1]); i += 2
                cur = (cur[0]+p[0], cur[1]+p[1]) if rel else p
                start = cur; add(cur)
                c = "L"                       # subsequent pairs are implicit lineto
            elif c == "L":
                if i + 2 > len(nums): break
                p = (nums[i], nums[i+1]); i += 2
                cur = (cur[0]+p[0], cur[1]+p[1]) if rel else p
                add(cur)
            elif c == "H":
                if i + 1 > len(nums): break
                x = nums[i]; i += 1
                cur = (cur[0]+x, cur[1]) if rel else (x, cur[1]); add(cur)
            elif c == "V":
                if i + 1 > len(nums): break
                y = nums[i]; i += 1
                cur = (cur[0], cur[1]+y) if rel else (cur[0], y); add(cur)
            elif c == "C":
                if i + 6 > len(nums): break
                pts = [(nums[i+k], nums[i+k+1]) for k in (0, 2, 4)]; i += 6
                if rel: pts = [(cur[0]+p[0], cur[1]+p[1]) for p in pts]
                bez(cur, pts[0], pts[1], pts[2]); cur = pts[2]
            elif c == "Z":
                cur = start; add(cur); break
            else:                              # Q/S/T/A: endpoints only, good enough
                if i + 2 > len(nums): break
                p = (nums[-2], nums[-1])
                cur = (cur[0]+p[0], cur[1]+p[1]) if rel else p
                add(cur); break
        nums = []

    for m in TOKEN.finditer(d):
        if m.group(1):
            flush(); cmd = m.group(1)
        else:
            nums.append(float(m.group(2)))
    flush()
    return list(zip(xs, ys))


def _opaque(n):
    if n.get("visible") is False or n.get("opacity", 1) < 0.99:
        return False
    for f in n.get("fills") or []:
        if f.get("visible") is False or f.get("opacity", 1) < 0.99:
            continue
        if f.get("type") == "IMAGE":
            return True
        if f.get("type") == "SOLID" and f.get("color", {}).get("a", 1) >= 0.99:
            return True
    return False


def _covers(n, bb, pad=0.5):
    """Does n, or any descendant, paint an opaque box over bb?"""
    if n.get("visible") is False or n.get("opacity", 1) < 0.99:
        return False
    b = n.get("absoluteBoundingBox") or {}
    if b and _opaque(n):
        if (b["x"] - pad <= bb["x"] and b["y"] - pad <= bb["y"]
                and b["x"] + b["width"] + pad >= bb["x"] + bb["width"]
                and b["y"] + b["height"] + pad >= bb["y"] + bb["height"]):
            return True
    return any(_covers(c, bb, pad) for c in n.get("children") or [])


def occluded(bb, stack):
    """stack is [(parent, index_of_child_on_path), ...] from the root down.
    Anything later in paint order, at any level, can bury this rect."""
    for parent, i in stack:
        for later in (parent.get("children") or [])[i + 1:]:
            if _covers(later, bb):
                return True
    return False


def _nums(el, *names):
    return [float(el.get(n, 0) or 0) for n in names]


def elem_bbox(el):
    """bbox of any SVG shape element, in user units."""
    tag = el.tag.split("}")[-1]
    if tag == "path":
        return path_bbox(el.get("d") or "")
    if tag == "rect":
        x, y, w, h = _nums(el, "x", "y", "width", "height")
        return (x, y, x + w, y + h)
    if tag == "circle":
        cx, cy, r = _nums(el, "cx", "cy", "r")
        return (cx - r, cy - r, cx + r, cy + r)
    if tag == "ellipse":
        cx, cy, rx, ry = _nums(el, "cx", "cy", "rx", "ry")
        return (cx - rx, cy - ry, cx + rx, cy + ry)
    if tag == "line":
        x1, y1, x2, y2 = _nums(el, "x1", "y1", "x2", "y2")
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    if tag in ("polygon", "polyline"):
        pts = [float(v) for v in re.findall(r"-?\d*\.?\d+", el.get("points") or "")]
        if len(pts) < 2:
            return None
        xs, ys = pts[0::2], pts[1::2]
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def elem_points(el):
    """Every shape reduced to a point list, so two drawings can be compared."""
    tag = el.tag.split("}")[-1]
    if tag == "path":
        return path_points(el.get("d") or "")
    b = elem_bbox(el)
    if not b:
        return []
    if tag in ("rect", "line"):
        return [(b[0], b[1]), (b[2], b[3])]
    if tag in ("circle", "ellipse"):
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        return [(b[0], cy), (cx, b[1]), (b[2], cy), (cx, b[3])]
    pts = [float(v) for v in re.findall(r"-?\d*\.?\d+", el.get("points") or "")]
    return list(zip(pts[0::2], pts[1::2]))


def icon_signature(elems):
    """Fingerprint what an icon DRAWS: its outline and its paint.

    Two constraints make a hash the wrong tool here:

    * The same icon reused on another card lands on sub-pixel-different coordinates. A hash
      of the geometry turns a 0.0008px difference into a total mismatch.
    * A filled star and an outlined star have *identical* geometry and differ only in
      `fill`. A geometry-only fingerprint calls them the same icon.

    So: a scale- and translation-invariant shape profile that is compared with a tolerance,
    plus the paint, compared exactly.
    """
    shapes = [(el, elem_points(el)) for el in elems]
    pts = [p for _, ps in shapes for p in ps]
    if not pts:
        return "", ""

    paint = "|".join(
        ";".join((el.get(k) or "-") for k in
                 ("fill", "stroke", "stroke-width", "fill-rule", "opacity"))
        for el, _ in shapes)

    x0 = min(p[0] for p in pts); x1 = max(p[0] for p in pts)
    y0 = min(p[1] for p in pts); y1 = max(p[1] for p in pts)
    span = max(x1 - x0, y1 - y0) or 1.0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    # Quantiles, not angular bins. A bin boundary turns a 0.001px wobble into a 0.06 jump
    # in the profile; a quantile moves by the size of the wobble and nothing else.
    def quantiles(vals, k=16):
        vals = sorted(vals)
        n = len(vals) - 1
        return [vals[round(i * n / (k - 1))] for i in range(k)]

    xs = [(px - x0) / span for px, _ in pts]
    ys = [(py - y0) / span for _, py in pts]
    rs = [math.hypot((px - cx) / span, (py - cy) / span) for px, py in pts]
    prof = quantiles(xs) + quantiles(ys) + quantiles(rs)
    return ",".join(f"{v:.3f}" for v in prof), paint


def icon_rects(nodes_dir, lo, hi, absolute=False):
    """Outermost pure-vector subtrees that actually render, in page coordinates.

    With absolute=True the boxes are also reported in Figma's own absolute coordinates, so
    another tool can key on them without re-deriving the origin."""
    def only_vec(n):
        if n.get("type") == "TEXT":
            return False
        k = n.get("children") or []
        return all(only_vec(c) for c in k) if k else n.get("type") in VECTORISH

    def has_glyph(n):
        """An icon has a drawn outline somewhere in it. Dots, rings and dividers do not."""
        return n.get("type") in GLYPHISH or any(has_glyph(c) for c in n.get("children") or [])

    def splittable(n):
        """A frame holding several separate icons (a pager's two arrows, a five-star row)
        is a container, not an icon. Recurse into it. Guard: only when the children are
        themselves containers — the letters of a logo are bare VECTORs and must stay whole."""
        kids = [c for c in (n.get("children") or []) if c.get("visible") is not False]
        if len(kids) < 2 or any(k.get("type") in VECTORISH for k in kids):
            return False
        bbs = [k.get("absoluteBoundingBox") or {} for k in kids]
        if not all(b and lo <= b["width"] <= hi and lo <= b["height"] <= hi for b in bbs):
            return False
        for i, a_ in enumerate(bbs):           # pairwise disjoint?
            for b_ in bbs[i + 1:]:
                if (a_["x"] < b_["x"] + b_["width"] and b_["x"] < a_["x"] + a_["width"]
                        and a_["y"] < b_["y"] + b_["height"] and b_["y"] < a_["y"] + a_["height"]):
                    return False
        return True

    def has_image(n):
        """A RECTANGLE or ELLIPSE with an IMAGE fill is a photo, whatever its type says.
        Treating it as an icon exports the box and sweeps up every path behind it."""
        if any(f.get("type") == "IMAGE" and f.get("visible") is not False
               for f in n.get("fills") or []):
            return True
        return any(has_image(c) for c in n.get("children") or [])

    docs = {}
    for f in glob.glob(os.path.join(nodes_dir, "*.json")):
        d = json.load(open(f))
        docs[pathlib.Path(f).stem] = d["document"] if "document" in d else d
    ox = min((d.get("absoluteBoundingBox") or {}).get("x", 0) for d in docs.values())
    oy = min((d.get("absoluteBoundingBox") or {}).get("y", 0) for d in docs.values())

    out, buried = [], 0
    for name, doc in docs.items():
        def walk(n, op=1.0, stack=()):
            nonlocal buried
            if n.get("visible") is False:
                return
            op *= n.get("opacity", 1)
            if op == 0:
                return
            bb = n.get("absoluteBoundingBox") or {}
            w, h = bb.get("width", 0), bb.get("height", 0)
            if bb and lo <= w <= hi and lo <= h <= hi and only_vec(n) and has_glyph(n) \
                    and not has_image(n) and not splittable(n):
                if occluded(bb, stack):
                    buried += 1          # placeholder artwork under a photo; never renders
                    return
                out.append((name, bb["x"] - ox, bb["y"] - oy, w, h, bb["x"], bb["y"]))
                return
            for i, c in enumerate(n.get("children", []) or []):
                walk(c, op, stack + ((n, i),))
        walk(doc)
    if buried:
        print(f"skipped {buried} vector(s) buried under an opaque fill (they never render)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--nodes", default="figma/nodes")
    ap.add_argument("--out", default="design/exports/icons")
    ap.add_argument("--min", type=int, default=10)
    ap.add_argument("--max", type=int, default=220)
    ap.add_argument("--tol", type=float, default=1.5)
    a = ap.parse_args()

    root = ET.parse(a.svg).getroot()
    paths = [n for n in root.iter() if n.tag.split("}")[-1] in SHAPES]
    boxes = [elem_bbox(n) for n in paths]
    paths, boxes = zip(*[(n, b) for n, b in zip(paths, boxes) if b]) or ((), ())
    paths, boxes = list(paths), list(boxes)
    print(f"{len(paths)} shape elements in the SVG")

    rects = icon_rects(a.nodes, a.min, a.max)

    # A pure-vector subtree can still be a GROUP of icons (a tile holding a badge, a
    # toolbar holding three glyphs). If one rect strictly contains another, the outer one
    # is a group: exporting it yields two icons stacked on top of each other.
    def contains(a_, b_, pad=1.0):
        return (a_[1] - pad <= b_[1] and a_[2] - pad <= b_[2]
                and a_[1] + a_[3] + pad >= b_[1] + b_[3]
                and a_[2] + a_[4] + pad >= b_[2] + b_[4]
                and (a_[3] * a_[4]) > (b_[3] * b_[4]) * 1.2)

    groups = {i for i, r in enumerate(rects)
              if any(j != i and contains(r, o) for j, o in enumerate(rects))}
    if groups:
        print(f"dropped {len(groups)} rects that contain other icons (they are groups)")
    rects = [r for i, r in enumerate(rects) if i not in groups]
    print(f"{len(rects)} icon rects in the node JSON\n")

    outdir = pathlib.Path(a.out); outdir.mkdir(parents=True, exist_ok=True)
    made, empty, manifest = 0, [], {}
    seen = {}
    for name, x, y, w, h, ax, ay in rects:
        # Number by RECT, before any skip. The fidelity report re-derives these names from
        # the same node JSON with the same rules; a name that shifts when one icon happens
        # to be empty would silently compare the wrong file.
        i = seen.get(name, 0) + 1
        seen[name] = i
        sel = [(n, b) for n, b in zip(paths, boxes)
               if b and b[0] >= x - a.tol and b[1] >= y - a.tol
               and b[2] <= x + w + a.tol and b[3] <= y + h + a.tol]
        if not sel:
            empty.append((name, round(x), round(y)))
            continue
        # viewBox = the icon NODE's box, not the ink box. Cropping to the ink makes every
        # icon render larger than the design (a 12px glyph in a 40px button fills the button)
        # and silently loses the padding the designer drew.
        # NOTE: register_namespace already emits xmlns; passing it again breaks the file.
        # width/height too: an <img> with no intrinsic size falls back to 300x150 and the
        # icon renders at whatever the surrounding flexbox allows.
        shape_sig, paint_sig = icon_signature([n for n, _ in sel])
        svg = ET.Element(f"{{{NS}}}svg", {
            "width": f"{w:g}", "height": f"{h:g}",
            "viewBox": f"{x:.2f} {y:.2f} {w:.2f} {h:.2f}", "fill": "none",
            # lets a verifier ask "is this the icon the design puts here?" after the file
            # has been renamed, copied, resized or reused on another node
            "data-icon-shape": shape_sig, "data-icon-paint": paint_sig})
        for n, _ in sel:
            svg.append(n)
        fn = f"{name}-{i:02d}.svg"
        ET.ElementTree(svg).write(outdir / fn, encoding="unicode")
        # keyed on the node's absolute box: the one identifier that cannot drift
        manifest[f"{name}|{round(ax)}|{round(ay)}"] = fn
        made += 1

    (outdir / "icons.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    print(f"wrote {made} icons to {outdir}/ (+ icons.json, the node->file manifest)")
    if empty:
        print(f"{len(empty)} icon rects had no vector inside them (shapes drawn as frames?): {empty[:6]}")
    print("\nNow OPEN THEM AND LOOK. A bad crop is a plausible-looking blob.")


if __name__ == "__main__":
    main()
