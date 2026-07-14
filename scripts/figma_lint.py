#!/usr/bin/env python3
"""Build-stage guard: catch values you invented before the fidelity report does.

Everything in the design is a number that exists in the node JSON. If your CSS uses a
gap, padding or font-size that appears nowhere in the file, you guessed it — and guessed
values are exactly what a per-text-node audit later reports as 100+ offsets.

Checks
  1. every `gap:` / `padding:` px value in the CSS exists as an `itemSpacing` or padding
     in the design
  2. every `font-size:` px value exists as a `fontSize`
  3. the number of `<br>` in the HTML does not exceed the number of TEXT nodes whose
     `characters` actually contain a newline
  4. every colour literal in the CSS exists as a solid fill in the design
  5. no hand-drawn inline `<svg>` where the design ships a vector you can export
  6. every visible TEXT `characters` string appears in the HTML source (page text or
     placeholder/aria-label/value/alt) — missing or reworded copy is caught here, before
     the browser reports it as a hundred "not found in DOM" rows

Hidden nodes and nodes with effective ancestor opacity 0 are ignored — they render
nothing, so their numbers are not design values.

Usage:
    python3 figma_lint.py --css css/styles.css --html index.html --nodes figma/nodes
"""
import argparse, glob, html as html_lib, json, os, re, sys


def design_values(nodes_dir):
    gaps, pads, sizes, colours, newline_texts = set(), set(), set(), set(), 0
    texts = []
    families = set()

    def hexes(node):
        out = []
        for f in node.get("fills") or []:
            if f.get("visible") is False or f.get("type") != "SOLID":
                continue
            c = f["color"]
            out.append("#%02x%02x%02x" % tuple(round(c[k] * 255) for k in "rgb"))
        return out

    for path in glob.glob(os.path.join(nodes_dir, "*.json")):
        d = json.load(open(path))
        d = d["document"] if "document" in d else d

        def walk(n, op=1.0):
            nonlocal newline_texts
            if n.get("visible") is False:
                return
            op *= n.get("opacity", 1)
            if op == 0:
                return
            if n.get("itemSpacing"):
                gaps.add(round(n["itemSpacing"]))
            for k in ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"):
                if n.get(k):
                    pads.add(round(n[k]))
            if n.get("type") == "TEXT":
                st = n.get("style", {})
                if st.get("fontSize"):
                    sizes.add(round(st["fontSize"]))
                if st.get("fontFamily"):
                    families.add(st["fontFamily"])
                for o in (n.get("styleOverrideTable") or {}).values():
                    if o.get("fontSize"):
                        sizes.add(round(o["fontSize"]))
                if "\n" in (n.get("characters") or ""):
                    newline_texts += 1
                chars = n.get("characters") or ""
                if st.get("textCase") == "UPPER":
                    chars = chars.upper()
                texts.append(chars)
            colours.update(hexes(n))
            for c in n.get("children", []) or []:
                walk(c, op)

        walk(d)
    return gaps, pads, sizes, colours, newline_texts, texts, families


def custom_props(css):
    """--name: value, so `gap: var(--space-6)` can be resolved instead of skipped.
    Hiding an invented number inside a custom property is the obvious way to defeat
    this linter, so we follow them."""
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;{}]+);", css)}


def resolve(val, props, depth=0):
    if depth > 4:
        return val
    def sub(m):
        return props.get(m.group(1), "")
    out = re.sub(r"var\(\s*(--[\w-]+)[^)]*\)", sub, val)
    return resolve(out, props, depth + 1) if "var(" in out else out


def css_numbers(css, prop, props):
    """px values for a property, after resolving var(). Responsive functions are skipped:
    clamp()/min()/max() legitimately hold non-design values for other viewports."""
    out = []
    for m in re.finditer(rf"(?<![\w-]){prop}\s*:\s*([^;{{}}]+);", css):
        val = resolve(m.group(1), props)
        if any(fn in val for fn in ("clamp(", "min(", "max(", "calc(")):
            continue
        out += [int(x) for x in re.findall(r"(\d+)px", val)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--css", required=True)
    ap.add_argument("--html", required=True)
    ap.add_argument("--nodes", default="figma/nodes")
    ap.add_argument("--tolerance", type=int, default=0,
                    help="allow a CSS value within N px of a design value")
    ap.add_argument("--allow-inline-svg", type=int, default=0,
                    help="number of inline <svg> you have justified in the difference log "
                         "(a vector the design draws as a shape and you reproduce in CSS)")
    a = ap.parse_args()

    gaps, pads, sizes, colours, newline_texts, texts, families = design_values(a.nodes)
    css = open(a.css).read()
    html = open(a.html).read()
    props = custom_props(css)

    def near(v, allowed):
        return any(abs(v - x) <= a.tolerance for x in allowed)

    problems = []

    spacing = set(gaps) | set(pads)
    bad_gap = sorted({v for v in css_numbers(css, "gap", props) if not near(v, spacing)})
    if bad_gap:
        problems.append(("gap", bad_gap, "not an itemSpacing or padding anywhere in the design"))

    bad_pad = sorted({v for v in css_numbers(css, "padding", props) if not near(v, spacing)})
    if bad_pad:
        problems.append(("padding", bad_pad, "not an itemSpacing or padding anywhere in the design"))

    bad_size = sorted({v for v in css_numbers(css, "font-size", props) if not near(v, sizes)})
    if bad_size:
        problems.append(("font-size", bad_size, "no TEXT node uses this size"))

    css_hex = {h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}", css)}
    design_hex = {c.lower() for c in colours}
    bad_col = sorted(css_hex - design_hex)
    if bad_col:
        problems.append(("colour", bad_col, "no solid fill in the design uses this hex"))

    # Fonts must be ACTUALLY WIRED, not just named. Two silent-fallback traps:
    #   (a) an @font-face whose src file does not exist on disk → the browser drops it
    #       and falls back to a metrically-different face, changing every line break
    #       (FM82/85) while the position audit stays green.
    #   (b) a design font-family that appears in NO CSS font stack → nothing requests it.
    # A licensed webfont's Figma name ("The Seasons") and its web token ("the-seasons")
    # differ, so compare on a normalised key (lowercase, alphanumerics only).
    def norm(s):
        return re.sub(r"[^a-z0-9]", "", s.lower())

    css_dir = os.path.dirname(os.path.abspath(a.css))
    missing_face = []
    for block in re.findall(r"@font-face\s*{([^}]*)}", css):
        fam = re.search(r"font-family\s*:\s*[\"']?([^;\"']+)", block)
        fam = fam.group(1).strip() if fam else "?"
        for url in re.findall(r"url\(\s*[\"']?([^)\"']+)", block):
            if url.startswith(("http://", "https://", "data:")):
                continue
            p = os.path.normpath(os.path.join(css_dir, url.split("?")[0].split("#")[0]))
            if not os.path.exists(p):
                missing_face.append(f'{fam}: {url}')
    if missing_face:
        problems.append(("@font-face src missing", sorted(set(missing_face)),
                         "the file does not exist on disk, so the browser silently falls "
                         "back to a different face — line breaks and metrics will not match "
                         "the design. Supply the file or use the real webfont <link>"))

    # every design font-family must be referenced somewhere in the CSS (a `font-family`
    # stack OR a `--font-*` custom property that a stack resolves through). Compare on the
    # normalised key against the whole normalised stylesheet so 'The Seasons' matches a
    # 'the-seasons' token and a family held only in a custom property still counts.
    css_norm = norm(css)
    unwired = sorted({f for f in families if norm(f) not in css_norm})
    if unwired:
        problems.append(("design font not in any CSS font stack", unwired,
                         "this typeface is used in the design but no `font-family` in the "
                         "CSS names it (Figma reports the display name, e.g. 'The Seasons'; "
                         "the web token may be 'the-seasons' — either is fine, but SOMETHING "
                         "must reference it or the text falls back to a system font)"))

    inline_svg = len(re.findall(r"<svg\b", html))
    if inline_svg > a.allow_inline_svg:
        problems.append(("inline <svg>", [f"{inline_svg} hand-drawn (allowed: {a.allow_inline_svg})"],
                         "icons must be exported from the design, not redrawn from memory; "
                         "justify any genuine CSS-shape exception with --allow-inline-svg"))

    brs = len(re.findall(r"<br\s*/?>", html))
    if brs > newline_texts:
        problems.append(("<br>", [f"{brs} in HTML vs {newline_texts} newlines in `characters`"],
                         "you invented line breaks; the copy no longer matches the design"))

    # Every visible string the design shows must appear, verbatim, in the HTML. Missing or
    # reworded copy is the single largest source of "not found in DOM" in the fidelity
    # report; catching it here means fixing it before the browser ever runs. The check is on
    # the HTML SOURCE, so text carried by placeholder=/aria-label=/value= counts as present.
    def flat(s):
        return re.sub(r"\s+", " ", (s or "")).strip().lower()

    haystack = flat(html_lib.unescape(re.sub(r"<[^>]+>", " ", html)))
    attrs = " ".join(re.findall(r'(?:placeholder|aria-label|value|alt|title)="([^"]*)"', html))
    haystack += " " + flat(html_lib.unescape(attrs))
    missing = []
    for t in texts:
        for line in t.split("\n"):          # a node's own newlines may become separate tags
            f = flat(line)
            if len(f) >= 2 and f not in haystack:
                missing.append(line.strip()[:48])
    if missing:
        uniq = sorted(set(missing))
        problems.append(("missing copy", uniq[:20] + ([f"... {len(uniq)-20} more"] if len(uniq) > 20 else []),
                         "these strings are in the design but not in the HTML — invented, "
                         "reworded or dropped copy"))

    print("Design vocabulary")
    print(f"  spacing values : {sorted(spacing)}")
    print(f"  font sizes     : {sorted(sizes)}")
    print(f"  solid colours  : {len(design_hex)}")
    print(f"  texts with \\n  : {newline_texts}")
    print(f"  text strings   : {len(texts)}\n")

    if not problems:
        print("OK — every CSS value is a value the design actually uses.")
        return

    print("INVENTED VALUES — these appear in your CSS but nowhere in the design:\n")
    for prop, vals, why in problems:
        print(f"  {prop}: {vals}")
        print(f"      {why}\n")
    print("Fix these before running the fidelity report. Guessed spacing is what turns into")
    print("a hundred y-offsets in the text audit.")
    sys.exit(1)


if __name__ == "__main__":
    main()
