#!/usr/bin/env python3
"""Print an accurate layout spec for a Figma node, from cached node JSON.

Implements the §6.5.3 reading contract:
  - text content comes from `characters`, never `name`
  - `visible: false` subtrees are skipped
  - reports textCase / textAlign / colour / stroke / radius / layout / image refs

Usage:
    python3 figma_spec.py <path-to-node.json> [max_depth]

Where <path-to-node.json> is one entry of GET /v1/files/:key/nodes?ids=…
(i.e. a dict with a "document" key), as written by figma_pull.py.
"""
import json, sys

if len(sys.argv) < 2:
    sys.exit(__doc__)

path = sys.argv[1]
maxd = int(sys.argv[2]) if len(sys.argv) > 2 else 6

doc = json.load(open(path))
doc = doc["document"] if "document" in doc else doc
root = doc.get("absoluteBoundingBox") or {}
ox, oy = root.get("x", 0), root.get("y", 0)
print(f"### {path}  {int(root.get('width',0))}x{int(root.get('height',0))}\n")


def _col(c, opacity=1):
    a = opacity * c.get("a", 1)
    r, g, b = (round(c[k] * 255) for k in "rgb")
    return f"#{r:02x}{g:02x}{b:02x}" + (f"@{a:.2f}" if a < 0.99 else "")


def paint(node, key="fills"):
    for f in node.get(key) or []:
        if f.get("visible") is False:
            continue
        t = f.get("type")
        if t == "SOLID":
            return _col(f["color"], f.get("opacity", 1))
        if t == "IMAGE":
            # imageTransform may rotate/flip the photo — flag it, do not ignore it.
            flag = "*" if f.get("imageTransform") else ""
            return f"IMG({f.get('imageRef','')[:8]}{flag})"
        if t and "GRADIENT" in t:
            return "GRADIENT"
    return ""


def walk(n, depth=0):
    if n.get("visible") is False:      # hidden variants hold stale copy — skip
        return
    if depth > maxd:
        return
    bb = n.get("absoluteBoundingBox") or {}
    if not bb:
        return
    x, y = int(bb.get("x", 0) - ox), int(bb.get("y", 0) - oy)
    w, h = int(bb.get("width", 0)), int(bb.get("height", 0))
    t = n.get("type", "")
    pad = "  " * depth

    if t == "TEXT":
        s = n.get("style", {})
        chars = (n.get("characters") or "").replace("\n", "⏎").replace("\r", "")[:58]
        bits = [f'{s.get("fontFamily")} {s.get("fontWeight")} {round(s.get("fontSize",0))}px']
        if s.get("lineHeightPx"): bits.append(f'lh{round(s["lineHeightPx"])}')
        if s.get("letterSpacing"): bits.append(f'ls{s["letterSpacing"]:.1f}')
        if s.get("textCase"): bits.append(s["textCase"])          # UPPER is real
        if s.get("textAlignHorizontal"): bits.append(s["textAlignHorizontal"])
        c = paint(n)
        if c: bits.append(c)
        print(f'{pad}TEXT  {x:>5},{y:<5} {w:>4}x{h:<4} "{chars}"  [{" ".join(bits)}]')
    else:
        bits = []
        f = paint(n)
        if f: bits.append(f)
        st = paint(n, "strokes")
        if st: bits.append(f'stroke {st} {n.get("strokeWeight","")}')
        if n.get("cornerRadius"): bits.append(f'r{int(n["cornerRadius"])}')
        if n.get("layoutMode"): bits.append(f'{n["layoutMode"].lower()} gap{int(n.get("itemSpacing",0))}')
        pads = [n.get(k) for k in ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom")]
        if any(pads): bits.append("pad " + "/".join(str(int(p or 0)) for p in pads))
        name = (n.get("name") or "")[:30]
        print(f'{pad}{t[:5]:<5} {x:>5},{y:<5} {w:>4}x{h:<4} {name}{"  ["+" ".join(bits)+"]" if bits else ""}')

    for c in n.get("children", []) or []:
        walk(c, depth + 1)


walk(doc)
