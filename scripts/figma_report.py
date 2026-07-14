#!/usr/bin/env python3
"""Generate a self-verifying fidelity report the user can open and judge themselves.

For every section it puts the Figma reference next to the live page, adds an opacity
slider and a difference-blend overlay, and runs the numeric checks in the browser
(section heights, container offset, horizontal overflow, resolved fonts, console errors).

Nothing here asserts "it matches" — it shows the evidence and prints the numbers.

Inputs (all produced earlier in the workflow):
  figma/nodes/<section>.json      node trees          (for y offsets + expected heights)
  figma/renders/ref_<section>.png reference slices    (what the design looks like)
  <page>                          the built page      (served over http)

Usage:
    python3 figma_report.py --page index.html \
        [--nodes figma/nodes] [--renders figma/renders] \
        [--selectors selectors.json] [--out fidelity-report.html]

`selectors.json` is optional: {"hero": ".hero", "footer": ".footer", ...}. Without it the
report measures `header, main > section, footer` in DOM order.
"""
import argparse, glob, json, os, pathlib, re, sys


def load_sections(nodes_dir, renders_dir):
    refs = {}
    for p in glob.glob(os.path.join(renders_dir, "ref_*.png")):
        refs[re.sub(r"^ref_", "", pathlib.Path(p).stem)] = p
    if not refs:
        raise SystemExit(f"No ref_*.png in {renders_dir}. Slice the page export first.")

    # A section with node JSON but no reference slice is a section nobody is checking.
    # This is exactly how a whole section goes missing without anyone noticing.
    known = {pathlib.Path(f).stem for f in glob.glob(os.path.join(nodes_dir, "*.json"))}
    unverified = sorted(known - set(refs))
    if unverified:
        print("WARNING: no reference slice for: " + ", ".join(unverified))
        print("         these sections are NOT verified by this report.")

    boxes = {}
    for name in refs:
        f = os.path.join(nodes_dir, f"{name}.json")
        if not os.path.exists(f):
            continue
        d = json.load(open(f))
        d = d["document"] if "document" in d else d
        bb = d.get("absoluteBoundingBox") or {}
        boxes[name] = (bb.get("x", 0), bb.get("y", 0), bb.get("width", 0), bb.get("height", 0))
    if not boxes:
        raise SystemExit(f"No matching node JSON in {nodes_dir}")

    origin_y = min(b[1] for b in boxes.values())
    origin_x = min(b[0] for b in boxes.values())

    def content_extents(node, sx, sw):
        """Left/right edge of the real content: ignore full-bleed backgrounds and
        anything hidden (visible:false, or effective ancestor opacity 0)."""
        lo, hi = [], []

        def walk(n, op=1.0):
            if n.get("visible") is False:
                return
            op *= n.get("opacity", 1)
            if op == 0:
                return
            bb = n.get("absoluteBoundingBox") or {}
            w = bb.get("width", 0)
            if bb and 0 < w < sw * 0.95:
                # clamp into the frame: carousels legitimately overflow and are clipped
                lo.append(max(0, bb["x"] - sx))
                hi.append(min(sw, bb["x"] + w - sx))
            for c in n.get("children", []) or []:
                walk(c, op)

        walk(node)
        return (round(min(lo)), round(max(hi))) if lo else (None, None)

    def hexc(node):
        for f in node.get("fills") or []:
            if f.get("visible") is False:
                continue
            if f.get("type") == "SOLID":
                c = f["color"]
                return "#%02x%02x%02x" % tuple(round(c[k] * 255) for k in "rgb")
        return None

    VECTORISH = {"VECTOR", "BOOLEAN_OPERATION", "ELLIPSE", "RECTANGLE", "LINE",
                 "REGULAR_POLYGON", "STAR"}
    # only these carry an icon's drawn outline; a subtree of plain ellipses is a shape
    # (carousel dots, a ring) that CSS draws, and demanding an <img> there is a false alarm
    GLYPHISH = {"VECTOR", "BOOLEAN_OPERATION", "REGULAR_POLYGON", "STAR"}

    def opaque(n):
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

    def covers(n, bb, pad=0.5):
        if n.get("visible") is False or n.get("opacity", 1) < 0.99:
            return False
        b = n.get("absoluteBoundingBox") or {}
        if b and opaque(n) and (b["x"] - pad <= bb["x"] and b["y"] - pad <= bb["y"]
                                and b["x"] + b["width"] + pad >= bb["x"] + bb["width"]
                                and b["y"] + b["height"] + pad >= bb["y"] + bb["height"]):
            return True
        return any(covers(c, bb, pad) for c in n.get("children") or [])

    def occluded(bb, stack):
        """A vector that a later sibling paints over never renders. Demanding an <img>
        there would send you chasing an icon nobody can see."""
        for parent, i in stack:
            for later in (parent.get("children") or [])[i + 1:]:
                if covers(later, bb):
                    return True
        return False

    def graphic_nodes(node, sx, sy, section=""):
        """Icon boxes (small, pure-vector subtrees) and image boxes (IMAGE fills).

        Each icon carries the filename figma_icons.py gives it, so the report can check
        *which* icon landed on the node — not merely that some icon did."""
        icons, images = [], []

        def only_vectors(n):
            if n.get("type") == "TEXT":
                return False
            kids = n.get("children") or []
            if not kids:
                return n.get("type") in VECTORISH
            return all(only_vectors(k) for k in kids)

        def has_vector(n):
            if n.get("type") in GLYPHISH:
                return True
            return any(has_vector(k) for k in n.get("children") or [])

        def splittable(n):
            """Several separate icons in one frame (pager arrows, a star row) are audited
            one by one, exactly as figma_icons.py exports them."""
            kids = [c for c in (n.get("children") or []) if c.get("visible") is not False]
            if len(kids) < 2 or any(k.get("type") in VECTORISH for k in kids):
                return False
            bbs = [k.get("absoluteBoundingBox") or {} for k in kids]
            if not all(b and 10 <= b["width"] <= 220 and 10 <= b["height"] <= 220 for b in bbs):
                return False
            for i, p_ in enumerate(bbs):
                for q in bbs[i + 1:]:
                    if (p_["x"] < q["x"] + q["width"] and q["x"] < p_["x"] + p_["width"]
                            and p_["y"] < q["y"] + q["height"] and q["y"] < p_["y"] + p_["height"]):
                        return False
            return True

        def has_image(n):
            """A shape with an IMAGE fill is a photo; it is audited as an image, not an icon."""
            if any(f.get("type") == "IMAGE" and f.get("visible") is not False
                   for f in n.get("fills") or []):
                return True
            return any(has_image(k) for k in n.get("children") or [])

        def walk(n, op=1.0, stack=()):
            if n.get("visible") is False:
                return
            op *= n.get("opacity", 1)
            if op == 0:
                return
            bb = n.get("absoluteBoundingBox") or {}
            for f in n.get("fills") or []:
                if f.get("visible") is not False and f.get("type") == "IMAGE" and bb.get("width", 0) >= 40:
                    images.append({"x": round(bb["x"] - sx), "y": round(bb["y"] - sy),
                                   "w": round(bb["width"]), "h": round(bb["height"]),
                                   "ref": f.get("imageRef")})
                    break
            # The OUTERMOST pure-vector subtree is one icon. Recursing further would count
            # every glyph outline of a logo as its own "missing icon".
            if bb and 10 <= bb.get("width", 0) <= 220 and 10 <= bb.get("height", 0) <= 220 \
                    and only_vectors(n) and has_vector(n) and not has_image(n) \
                    and not splittable(n):
                if not occluded(bb, stack):
                    ib = {"x": round(bb["x"] - sx), "y": round(bb["y"] - sy),
                          "w": round(bb["width"]), "h": round(bb["height"])}
                    # which file figma_icons.py exported for this exact node
                    key = (section, ib["x"] + round(sx), ib["y"] + round(sy))
                    ib["file"] = MANIFEST.get(f"{section}|{round(bb['x'])}|{round(bb['y'])}")
                    icons.append(ib)
                return
            for i, c in enumerate(n.get("children", []) or []):
                walk(c, op, stack + ((n, i),))

        walk(node)
        return icons, images

    def hover_nodes(node, sx, sy):
        """Nodes the design says react to hover, with the duration/easing it specifies.
        The durations are already in the node JSON — verifying them needs no extra fetch."""
        out = []

        def walk(n, op=1.0):
            if n.get("visible") is False:
                return
            op *= n.get("opacity", 1)
            if op == 0:
                return
            bb = n.get("absoluteBoundingBox") or {}
            for it in n.get("interactions") or []:
                if (it.get("trigger") or {}).get("type") != "ON_HOVER":
                    continue
                for act in it.get("actions") or []:
                    tr = act.get("transition") or {}
                    if bb and tr.get("duration"):
                        out.append({"x": round(bb["x"] - sx), "y": round(bb["y"] - sy),
                                    "w": round(bb["width"]), "h": round(bb["height"]),
                                    "ms": round(tr["duration"] * 1000),
                                    "easing": (tr.get("easing") or {}).get("type"),
                                    "dest": act.get("destinationId")})
            for c in n.get("children", []) or []:
                walk(c, op)

        walk(node)
        return out

    def box_nodes(node, sx, sy):
        """Non-text boxes worth checking: a visible solid fill and/or a corner radius.
        Nothing here is about text, so it catches the class of defect the text audit
        is blind to (a panel with the wrong colour, a card with the wrong radius)."""
        out = []

        def walk(n, op=1.0):
            if n.get("visible") is False:
                return
            op *= n.get("opacity", 1)
            if op == 0:
                return
            bb = n.get("absoluteBoundingBox") or {}
            # TEXT nodes are the text audit's job; a text fill is a font colour, not a box.
            if n.get("type") != "TEXT" and bb and bb.get("width", 0) >= 60 and bb.get("height", 0) >= 40:
                fill = None
                has_image = False
                for f in n.get("fills") or []:
                    if f.get("visible") is False:
                        continue
                    if f.get("type") == "IMAGE":
                        has_image = True
                    elif f.get("type") == "SOLID" and fill is None \
                            and f.get("opacity", 1) >= 0.99 and f["color"].get("a", 1) >= 0.99:
                        c = f["color"]
                        fill = "#%02x%02x%02x" % tuple(round(c[k] * 255) for k in "rgb")
                # An IMAGE fill covers the box: the solid underlay is invisible — never
                # compare it against the CSS background colour.
                if has_image:
                    fill = None
                r = n.get("cornerRadius")
                # Figma stores huge pill radii (e.g. 999/1353); the rendered radius can
                # never exceed half the short side — clamp so comparisons are physical.
                if r:
                    r = min(float(r), min(bb["width"], bb["height"]) / 2)
                stroke = None
                for st in n.get("strokes") or []:
                    if st.get("visible") is not False and st.get("type") == "SOLID" \
                            and st.get("opacity", 1) >= 0.5 and st["color"].get("a", 1) >= 0.5:
                        c = st["color"]
                        stroke = "#%02x%02x%02x" % tuple(round(c[k] * 255) for k in "rgb")
                        break
                shadow = any(e.get("type") == "DROP_SHADOW" and e.get("visible") is not False
                             for e in n.get("effects") or [])
                if fill or r or stroke or shadow:
                    out.append({"x": round(bb["x"] - sx), "y": round(bb["y"] - sy),
                                "w": round(bb["width"]), "h": round(bb["height"]),
                                "fill": fill, "radius": round(r) if r else None,
                                "stroke": stroke, "shadow": shadow})
            for c in n.get("children", []) or []:
                walk(c, op)

        walk(node)
        return out[:40]

    def text_nodes(node, sx, sy):
        """Every TEXT node that actually renders, with the spec we can verify in the DOM."""
        out = []

        def walk(n, op=1.0):
            if n.get("visible") is False:
                return
            op *= n.get("opacity", 1)
            if op == 0:
                return
            if n.get("type") == "TEXT":
                bb = n.get("absoluteBoundingBox") or {}
                st = n.get("style", {})
                chars = (n.get("characters") or "").strip()
                if bb and chars:
                    if st.get("textCase") == "UPPER":
                        chars = chars.upper()
                    out.append({
                        "text": " ".join(chars.split()),
                        "x": round(bb["x"] - sx), "y": round(bb["y"] - sy),
                        "w": round(bb["width"]), "h": round(bb["height"]),
                        "size": round(st.get("fontSize", 0)),
                        "weight": st.get("fontWeight"),
                        "family": st.get("fontFamily"),
                        "color": hexc(n),
                        # how the text sits in its box: a CENTER/RIGHT-aligned node in a wide
                        # fixed box has its ink offset from the box's left edge, so X must be
                        # compared at the matching anchor, not always at the left
                        "align": st.get("textAlignHorizontal"),
                    })
            for c in n.get("children", []) or []:
                walk(c, op)

        walk(node)
        return out

    out = []
    for name, (x, y, w, h) in boxes.items():
        d = json.load(open(os.path.join(nodes_dir, f"{name}.json")))
        d = d["document"] if "document" in d else d
        cl, cr = content_extents(d, x, w)
        icons, images = graphic_nodes(d, x, y, name)
        out.append({"name": name, "top": round(y - origin_y), "left": round(x - origin_x),
                    "w": round(w), "h": round(h), "ref": refs[name],
                    "contentLeft": cl, "contentRight": cr,
                    "texts": text_nodes(d, x, y),
                    "boxes": box_nodes(d, x, y),
                    "hovers": hover_nodes(d, x, y),
                    "icons": icons, "images": images})
    out.sort(key=lambda s: s["top"])
    return out


HTML = r"""<!doctype html><meta charset="utf-8"><title>Fidelity report</title>
<style>
 :root{--col:560px}
 body{font:14px/1.5 system-ui,sans-serif;margin:0;background:#111;color:#eee}
 header{padding:20px 24px;border-bottom:1px solid #333;position:sticky;top:0;background:#111;z-index:5}
 h1{margin:0 0 4px;font-size:18px} .sub{color:#999}
 #summary{margin-top:12px;display:flex;gap:22px;flex-wrap:wrap}
 .stat{background:#1b1b1b;border:1px solid #333;border-radius:8px;padding:8px 14px}
 .stat b{display:block;font-size:18px} .ok{color:#5cd08a} .bad{color:#ff7676}
 section{padding:26px 24px;border-bottom:1px solid #262626}
 .head{display:flex;align-items:baseline;gap:14px;margin-bottom:12px}
 .head h2{margin:0;font-size:16px} .verdict{font-weight:600}
 .cols{display:grid;grid-template-columns:repeat(2, var(--col)) ;gap:18px}
 .pane{width:var(--col);background:#000;border:1px solid #333;border-radius:6px;overflow:hidden;position:relative}
 .pane .cap{position:absolute;top:0;left:0;z-index:2;background:#000a;padding:3px 8px;font-size:11px;letter-spacing:.05em}
 .shot{position:relative;overflow:hidden}
 .shot img{display:block;width:100%}
 .shot iframe{border:0;position:absolute;top:0;left:0;transform-origin:0 0}
 .overlay{margin-top:18px}
 .overlay .stack{width:var(--col);position:relative;overflow:hidden;border:1px solid #333;border-radius:6px}
 .overlay img{display:block;width:100%}
 .overlay .live{position:absolute;inset:0;overflow:hidden}
 .overlay iframe{border:0;position:absolute;top:0;left:0;transform-origin:0 0}
 .ctl{display:flex;align-items:center;gap:12px;margin:10px 0}
 .ctl input[type=range]{width:260px}
 table{border-collapse:collapse;margin-top:14px;font-size:13px;width:100%}
 td,th{border:1px solid #333;padding:5px 9px;text-align:left}
 th{background:#1b1b1b;font-weight:600}
 code{color:#9fd}
</style>
<header>
  <h1>Fidelity report</h1>
  <div class="sub">Left = Figma reference · Right = the built page, live. Drag the slider to
  cross-fade, or switch to <em>difference</em> — a perfect match goes black.</div>
  <div id="summary"></div>
</header>
<main id="out"></main>
<script>
const SECTIONS = __SECTIONS__;
const UNVERIFIED = __UNVERIFIED__;
const BREAKPOINTS = __BREAKPOINTS__;
const ASSETS_MAP = __ASSETS_MAP__;
// Cache-bust every load of the page. The browser caches linked CSS/JS across iframes, so a
// report opened after an edit can silently measure the PREVIOUS stylesheet — a fixed offset
// stays "unfixed" in the report though the file on disk is correct. A unique query per report
// forces a fresh fetch of the page; sub-resources still cache unless the page links them with
// its own bust, so the report also appends the token to same-origin <link>/<script>/<img> in
// the probe before measuring.
const BUST = 'cb=' + (location.search.match(/[?&]v=([^&]+)/) || [,''])[1] + Date.now();
const PAGE = "__PAGE__" + ("__PAGE__".includes('?') ? '&' : '?') + BUST;
const DESIGN_W = __DESIGN_W__;
const COL_W = 560;
document.documentElement.style.setProperty('--col', COL_W + 'px');

const out = document.getElementById('out');
SECTIONS.forEach(s => {
  const scale = COL_W / DESIGN_W;
  const el = document.createElement('section');
  el.innerHTML = `
   <div class="head">
     <h2>${s.name}</h2>
     <span class="sub">Figma ${s.w}×${s.h} @ y=${s.top}</span>
     <span class="verdict" id="v-${s.name}">measuring…</span>
   </div>
   <div class="cols">
     <div class="pane"><span class="cap">Figma reference</span>
       <div class="shot" style="height:${s.h*scale}px"><img src="${s.ref}"></div></div>
     <div class="pane"><span class="cap">Built page (live)</span>
       <div class="shot" style="height:${s.h*scale}px">
         <iframe src="${PAGE}" scrolling="no" width="${DESIGN_W}" height="${s.top+s.h}"
                 style="transform:scale(${scale}) translateY(${-s.top}px)"></iframe>
       </div></div>
   </div>
   <div class="overlay">
     <div class="ctl">
       <label>overlay <input type="range" min="0" max="100" value="50" id="r-${s.name}"></label>
       <label><input type="checkbox" id="d-${s.name}"> difference blend</label>
     </div>
     <div class="stack" style="height:${s.h*scale}px">
       <img src="${s.ref}">
       <div class="live" id="l-${s.name}" style="opacity:.5">
         <iframe src="${PAGE}" scrolling="no" width="${DESIGN_W}" height="${s.top+s.h}"
                 style="transform:scale(${scale}) translateY(${-s.top}px)"></iframe>
       </div>
     </div>
   </div>`;
  out.appendChild(el);
  const live = el.querySelector(`#l-${CSS.escape(s.name)}`);
  el.querySelector(`#r-${CSS.escape(s.name)}`).addEventListener('input', e => live.style.opacity = e.target.value/100);
  el.querySelector(`#d-${CSS.escape(s.name)}`).addEventListener('change', e => {
    live.style.mixBlendMode = e.target.checked ? 'difference' : 'normal';
    live.style.opacity = e.target.checked ? 1 : (el.querySelector(`#r-${CSS.escape(s.name)}`).value/100);
  });
});

// ---- numeric checks, run against the live page in an offscreen iframe ----
const probe = document.createElement('iframe');
probe.style.cssText = 'position:absolute;left:-9999px;width:' + DESIGN_W + 'px;height:900px';
probe.src = PAGE;
document.body.appendChild(probe);

// A verifier that dies quietly is worse than no verifier: the page keeps saying
// "measuring…" and the reader reads that as "still working", not "it crashed".
function reportCrash(err) {
  const bar = document.createElement('div');
  bar.style.cssText = 'position:sticky;top:0;z-index:99;background:#c0392b;color:#fff;'
    + 'padding:14px 18px;font:13px/1.5 ui-monospace,monospace;white-space:pre-wrap';
  bar.textContent = 'THIS REPORT CRASHED — every number below is missing, not passing.\n'
    + (err && err.stack ? err.stack : String(err));
  document.body.prepend(bar);
  document.querySelectorAll('.verdict').forEach(v => { v.textContent = 'audit crashed'; });
}
window.addEventListener('error', e => reportCrash(e.error || e.message));
window.addEventListener('unhandledrejection', e => reportCrash(e.reason));

probe.addEventListener('load', async () => {
 try {
  const d = probe.contentDocument, w = probe.contentWindow;

  // The probe page scrolls, so its vertical scrollbar steals ~15px from the layout viewport:
  // every centred/right-anchored element then sits left of its Figma x and the whole text
  // audit fails by a constant. Widen the iframe by the scrollbar width so the layout
  // viewport is EXACTLY the design width.
  const sbw = DESIGN_W - d.documentElement.clientWidth;
  if (sbw > 0) probe.style.width = (DESIGN_W + sbw) + 'px';

  // Force fresh CSS/JS. The HTML was loaded with a cache-bust, but its linked stylesheets are
  // cached separately, so a just-fixed offset can still be measured against the OLD CSS. Re-
  // point every same-origin <link rel=stylesheet>/<script>/<img> at a busted URL and wait for
  // the stylesheets to re-apply before measuring — otherwise the report lies about the fix.
  const busted = [];
  d.querySelectorAll('link[rel="stylesheet"][href], script[src], img[src]').forEach(el => {
    const attr = el.tagName === 'LINK' ? 'href' : 'src';
    const u = el.getAttribute(attr);
    if (!u || /^(https?:|data:|\/\/)/i.test(u) && !u.startsWith(location.origin)) return;
    if (el.tagName === 'LINK') {
      busted.push(new Promise(res => {
        const link = el.cloneNode();
        link.setAttribute('href', u + (u.includes('?') ? '&' : '?') + BUST);
        link.addEventListener('load', res); link.addEventListener('error', res);
        el.parentNode.insertBefore(link, el.nextSibling);
        setTimeout(res, 1500);   // never hang the whole report on one asset
      }));
    } else {
      el.setAttribute(attr, u + (u.includes('?') ? '&' : '?') + BUST);
    }
  });
  await Promise.all(busted);
  await new Promise(r => setTimeout(r, 60));   // let the fresh CSS lay out

  // Measure the RESOLVED layout, never a mid-animation frame. An entrance reveal commonly
  // starts elements at opacity:0 translateY(Npx) and transitions them in. In this offscreen
  // measuring iframe document.hidden is true, so CSS transitions and IntersectionObserver are
  // FROZEN — every revealed element stays stranded at its start offset, and getComputedStyle
  // returns that displaced, invisible value. Reading it makes a perfectly-built page look
  // uniformly N-px low. Force every element to its final, settled state before measuring:
  // kill transitions/animations AND neutralise the usual reveal start-state and its markers.
  // This never hides a real design offset — it removes only the animation's own displacement.
  const reset = d.createElement('style');
  reset.textContent = `*,*::before,*::after{transition:none!important;animation:none!important}
    [data-reveal],[data-aos],[class*="reveal"],[class*="fade"],[class*="animate"],
    .is-in,.in-view,.is-visible,.visible,.show,.active{
      opacity:1!important;transform:none!important;filter:none!important;
      visibility:visible!important;clip-path:none!important}`;
  d.documentElement.appendChild(reset);
  // Some builds hide via a class on <html>/<body> removed by JS (e.g. .preload, .no-js);
  // strip common ones so their descendants settle too.
  ['preload','loading','no-js','js-loading'].forEach(c => {
    d.documentElement.classList.remove(c); d.body && d.body.classList.remove(c);
  });
  void d.documentElement.offsetHeight;   // force a synchronous reflow with the reset applied

  const sel = __SELECTORS__;
  const selProblems = [];
  const nodes = sel
    ? SECTIONS.map(s => {
        const q = sel[s.name];
        if (!q) { selProblems.push(`${s.name}: no selector`); return null; }
        const hits = d.querySelectorAll(q);
        if (hits.length !== 1) selProblems.push(`${s.name}: "${q}" matches ${hits.length} elements`);
        return hits[0] || null;
      })
    : [...d.querySelectorAll('header, main > section, footer')];
  if (!sel) selProblems.push('no --selectors given; sections were matched by DOM order, which can silently mis-map');

  // Left/right edge of the real content, ignoring full-bleed backgrounds.
  // Heights alone will not catch a container that is offset sideways.
  function extents(root) {
    const rb = root.getBoundingClientRect();
    let lo = Infinity, hi = -Infinity;
    root.querySelectorAll('*').forEach(e => {
      const r = e.getBoundingClientRect();
      if (r.width <= 0 || r.width >= rb.width * 0.95) return;
      if (getComputedStyle(e).visibility === 'hidden') return;
      // clamp into the frame: carousels legitimately overflow and are clipped
      lo = Math.min(lo, Math.max(0, r.left - rb.left));
      hi = Math.max(hi, Math.min(rb.width, r.right - rb.left));
    });
    return lo === Infinity ? [null, null] : [Math.round(lo), Math.round(hi)];
  }

  // ---- text-level audit: match Figma TEXT nodes to DOM elements by their words ----
  const norm = t => (t||'').replace(/\s+/g,' ').trim();
  const rgb2hex = c => {
    const m = c.match(/\d+/g); if (!m) return c;
    return '#' + m.slice(0,3).map(n => (+n).toString(16).padStart(2,'0')).join('');
  };
  // A Figma TEXT node may render as a bare text run inside a mixed element
  // (e.g. "/ Night" beside a <span>), and the same string may appear many times
  // (one per card). Collect every candidate run, then pick the one nearest to the
  // position the design expects. Matching by element identity does neither.
  // Figma's TEXT box top is the LINE box top — it includes the line-height leading above the
  // caps. The browser's ink box (Range bounds) starts at the glyph tops, so ink-top carries a
  // systematic bias vs Figma that swings with line-height (below for small text, ABOVE for big
  // display type whose ascenders overshoot). The faithful analog is the element's own
  // content-box top — but only when that element tightly wraps just this text; a multi-child
  // container's top is the first child's, not this run's. So: content-box top when the element
  // wraps exactly `want`, else fall back to the ink line. X always uses the ink's left edge.
  function boxTop(el) {
    const r = el.getBoundingClientRect(), cs = el.ownerDocument.defaultView.getComputedStyle(el);
    return r.top + parseFloat(cs.paddingTop || 0) + parseFloat(cs.borderTopWidth || 0);
  }
  function yTop(el, rg, want) {
    return norm(el.textContent).toLowerCase() === want ? boxTop(el)
         : (rg.getClientRects()[0] || rg.getBoundingClientRect()).top;
  }
  function candidates(root, text) {
    const want = norm(text).toLowerCase();
    const out = [];
    const w = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      if (norm(n.nodeValue).toLowerCase() === want && n.parentElement) {
        // Text inside a closed <option> has no layout box (rect 0,0); if kept it wins the
        // leaf-most filter over the real <select> and the field reads "not found". The
        // select itself is matched by the form-control pass below.
        if (n.parentElement.closest('option')) continue;
        const rg = root.ownerDocument.createRange();
        rg.selectNodeContents(n);
        out.push({el: n.parentElement, rect: rg.getBoundingClientRect(), top: yTop(n.parentElement, rg, want)});
      }
    }
    // also whole elements whose text EQUALS the wanted string, for text broken across <br>
    // or nested spans. Use innerText, not textContent: a <br> joins two runs with no space in
    // textContent ("Best availabledirect rates"), so a design string with the space would
    // never match. innerText renders the <br> as a line break, which norm() folds to a space.
    // Only EQUALS here — a CONTAINS match (e.g. "5" inside "5 Bedrooms") must NOT use the whole
    // element's rect (it starts at the element's left, e.g. an icon), which reports a large
    // false x-offset. Those are handled by the substring fallback below, which ranges over the
    // matched substring so the position is the substring's own, not the container's.
    root.querySelectorAll('*').forEach(e => {
      // Skip <option>: it has no layout box (rect 0,0) but its innerText matches the select's
      // placeholder, so it would survive the leaf-most filter over the real <select> and then
      // be discarded as zero-size, leaving the field "not found". The select is matched by its
      // value in the form-control pass below.
      if (e.tagName === 'OPTION') return;
      if (norm(e.innerText).toLowerCase() !== want) return;
      const rg = root.ownerDocument.createRange();
      rg.selectNodeContents(e);
      out.push({el: e, rect: rg.getBoundingClientRect(), top: yTop(e, rg, want)});
    });
    // A Figma TEXT node inside a field ("First Name", "Email") usually renders as a form
    // control's placeholder/value/label, not as page text. Reading only text nodes would
    // cry "missing" over copy that is plainly on screen.
    // NB: never match a bare <option> — inside a closed <select> it has no layout box (rect
    // at 0,0), and the leaf-most filter would then drop the real <select> in its favour and
    // report a nonsense −thousands-px offset. The select's own `value` already carries the
    // placeholder/first-option text, so the control matches without the option.
    root.querySelectorAll('input, textarea, select, [aria-label], [placeholder]')
      .forEach(e => {
        const cand = [e.getAttribute('placeholder'), e.getAttribute('aria-label'), e.value,
                      e.tagName === 'SELECT' && e.options[e.selectedIndex]
                        ? e.options[e.selectedIndex].textContent : null];
        if (!cand.some(v => norm(v).toLowerCase() === want)) return;
        const br = e.getBoundingClientRect();
        // The design's node is the placeholder/label TEXT, which sits inside the field's
        // content padding — not at the field box's edge. Anchor X/Y at the content box so the
        // comparison matches where the text actually renders, not the control's border.
        // X only: a single-line field's placeholder is centred vertically, so the box top is
        // already the right Y anchor; only the horizontal inset (padding/border) matters.
        const fcs = e.ownerDocument.defaultView.getComputedStyle(e);
        const pad = n => parseFloat(fcs[n] || 0);
        const cr = {left: br.left + pad('paddingLeft') + pad('borderLeftWidth'),
                    right: br.right - pad('paddingRight') - pad('borderRightWidth'),
                    top: br.top,
                    width: br.width - pad('paddingLeft') - pad('paddingRight')};
        out.push({el: e, rect: cr, top: br.top, viaAttr: true});
      });
    // Fallback — the design may split one phrase into several TEXT nodes ("5", "Bedrooms")
    // that the build renders as one run ("5 Bedrooms"), or the reverse. A run that CONTAINS
    // the wanted text at word boundaries is a visual match, not a miss. Range over just the
    // substring so its own rect is used and position is still checked. Only when no exact
    // candidate was found, so the common case stays precise.
    if (!out.length && want) {
      const rx = new RegExp('(^|\\s)' + want.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
                              .replace(/\s+/g, '\\s+') + '(\\s|$)', 'i');
      const wk = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let n = wk.nextNode(); n; n = wk.nextNode()) {
        if (!n.parentElement) continue;
        const m = rx.exec(n.nodeValue || '');
        if (!m) continue;
        const start = m.index + m[1].length;
        const rg = root.ownerDocument.createRange();
        rg.setStart(n, start);
        rg.setEnd(n, start + (m[0].length - m[1].length - m[2].length));
        out.push({el: n.parentElement, rect: rg.getBoundingClientRect(), top: (rg.getClientRects()[0]||rg.getBoundingClientRect()).top, grouped: true});
      }
    }
    // A label wrapped in a group wrapped in a field all share the same innerText, so all three
    // become candidates — but only the innermost is the actual text box; the outer ones are
    // taller and sit higher, which would report a false vertical offset. Keep only the
    // leaf-most: drop any candidate whose element contains another candidate's element.
    const els = out.map(c => c.el);
    return out.filter(c => !els.some(o => o !== c.el && c.el.contains(o)));
  }
  function pickNearest(cands, box, rb) {
    let best = null, bd = Infinity;
    cands.forEach(c => {
      if (!c.rect.width && !c.rect.height) return;
      // X from the ink's left edge; Y from the line-box top (the true analog of Figma's box).
      const dx = (c.rect.left - rb.left) - box.x;
      const dy = ((c.top != null ? c.top : c.rect.top) - rb.top) - box.y;
      const d = Math.hypot(dx, dy);
      if (d < bd) { bd = d; best = c; }
    });
    return best;
  }
  // Measure the *ink box* of the text, not the element box: a centred heading lives in a
  // full-width <p>, while Figma stores the tight text box. Comparing element rects would
  // report a huge false offset.
  function inkRect(el) {
    const rg = el.ownerDocument.createRange();
    rg.selectNodeContents(el);
    const r = rg.getBoundingClientRect();
    rg.detach && rg.detach();
    return (r.width || r.height) ? r : el.getBoundingClientRect();
  }
  const SUBSTITUTED = new Set();   // font families we could not load -> weight is not comparable

  const textIssues = [];
  // One "10/224 match" number hides the story: a string that is present and correct except
  // for a 6px shift is nothing like a string that is missing. Tally each dimension so the
  // reader sees "223 found, 61 positioned, ..." and knows a shifted layout from dropped copy.
  const tally = {found:0, position:0, size:0, weight:0, colour:0};
  function auditText(sec, node) {
    const rb = node.getBoundingClientRect();
    (sec.texts || []).forEach(t => {
      const hit = pickNearest(candidates(node, t.text), t, rb);
      if (!hit) { textIssues.push({s:sec.name, t:t.text.slice(0,34), issue:'text not found in DOM'}); return; }
      tally.found++;
      const el = hit.el;
      const r = hit.rect, cs = getComputedStyle(el);
      // Compare X at the anchor the text is aligned to. Figma's box is the LAYOUT box; a
      // CENTER/RIGHT-aligned node's ink sits away from the box's left edge, so comparing my
      // ink-left to the Figma box-left invents an offset the size of the box's slack (seen as
      // +195 on a centred name in a full-column box). Anchor both sides the same way.
      let dx;
      if (t.align === 'CENTER')      dx = Math.round((r.left + r.width / 2 - rb.left) - (t.x + t.w / 2));
      else if (t.align === 'RIGHT')  dx = Math.round((r.right - rb.left) - (t.x + t.w));
      else                           dx = Math.round(r.left - rb.left) - t.x;
      const dy = Math.round((hit.top != null ? hit.top : r.top) - rb.top) - t.y;
      const fs = Math.round(parseFloat(cs.fontSize));
      const fw = parseInt(cs.fontWeight, 10);
      // A design TEXT that renders as an input's PLACEHOLDER shows the ::placeholder colour,
      // not the element's `color` (which paints typed text). Comparing `color` would flag a
      // grey placeholder as wrong just because typed text is dark. Read the pseudo when the
      // match came from an attribute on a form field.
      let col = rgb2hex(cs.color);
      if (hit.viaAttr && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) {
        try {
          const ph = rgb2hex(getComputedStyle(el, '::placeholder').color);
          if (ph && ph !== '#') col = ph;
        } catch (e) {}
      }
      const famUsed = (cs.fontFamily.split(',')[0] || '').replace(/["']/g, '').trim();
      // A declared @font-face whose file 404s still shows up in computed fontFamily.
      // Ask the document whether the face is really loaded before trusting it.
      let loaded = true;
      try { loaded = el.ownerDocument.fonts.check(`${t.weight || 400} ${t.size || 16}px "${famUsed}"`); } catch (e) {}
      const substituted = !!t.family &&
        (famUsed.toLowerCase() !== t.family.toLowerCase() || !loaded);
      if (substituted) SUBSTITUTED.add(`${t.family}${loaded ? ' -> ' + famUsed : ' (not loaded)'}`);

      const bad = [];
      const posOK = Math.abs(dx) <= 4 && Math.abs(dy) <= 4;
      if (Math.abs(dx) > 4) bad.push(`x ${dx>0?'+':''}${dx}`);
      if (Math.abs(dy) > 4) bad.push(`y ${dy>0?'+':''}${dy}`);
      if (posOK) tally.position++;
      const sizeOK = !t.size || Math.abs(fs - t.size) <= 1;
      if (!sizeOK) bad.push(`size ${fs} vs ${t.size}`);
      if (sizeOK) tally.size++;
      // weight is only comparable within the same typeface
      const weightOK = substituted || !t.weight || Math.abs(fw - t.weight) < 100;
      if (!weightOK) bad.push(`weight ${fw} vs ${t.weight}`);
      if (weightOK) tally.weight++;
      const colOK = !t.color || col.toLowerCase() === t.color.toLowerCase();
      if (!colOK) bad.push(`colour ${col} vs ${t.color}`);
      if (colOK) tally.colour++;
      if (bad.length) textIssues.push({s:sec.name, t:t.text.slice(0,34), issue:bad.join(', ')});
    });
  }

  // ---- graphic audit: is each design icon a real exported asset, a hand-drawn
  // approximation, or missing? Same for photos vs gradient placeholders. ----
  const gfx = {icon:{asset:0, drawn:0, missing:0, offset:0, wrong:0, extra:0, unsigned:0}, image:{real:0, placeholder:0, missing:0}};
  const identityChecks = [];
  const gfxIssues = [];
  // Returns {el, d} for the closest candidate, whatever the distance. The caller decides
  // what counts as a match: "nothing is there" and "something is there, 90px off" are two
  // different defects and must never be reported with the same word.
  function nearest(cands, box, rb) {
    const cx = box.x + box.w/2, cy = box.y + box.h/2;
    let best = null, bd = 1e9;
    cands.forEach(e => {
      const r = e.getBoundingClientRect();
      if (!r.width) return;
      const ex = r.left - rb.left + r.width/2, ey = r.top - rb.top + r.height/2;
      const d = Math.hypot(ex - cx, ey - cy);
      if (d < bd) { bd = d; best = e; }
    });
    return best ? {el: best, d: Math.round(bd)} : null;
  }
  const ICONS_DIR = __ICONS_DIR__;
  const MANIFEST_FILES = __MANIFEST__;
  const sigCache = new Map();
  // figma_icons.py stamps every icon it exports with data-icon-shape (a scale- and
  // translation-invariant outline profile) and data-icon-paint. Comparing files by name or
  // by bytes would call each legitimate reuse of an icon a mismatch; comparing geometry
  // alone would call a filled star and an outlined star the same icon.
  function signature(url) {
    if (sigCache.has(url)) return sigCache.get(url);
    const pr = fetch(url).then(r => r.ok ? r.text() : null).then(t => {
      if (!t) return null;
      const el = new DOMParser().parseFromString(t, 'image/svg+xml').documentElement;
      const shape = el.getAttribute('data-icon-shape');
      if (!shape) return null;
      return {shape: shape.split(',').map(Number), paint: el.getAttribute('data-icon-paint')};
    }).catch(() => null);
    sigCache.set(url, pr);
    return pr;
  }
  function sameIcon(a, b, eps = 0.02) {
    if (!a || !b || a.paint !== b.paint || a.shape.length !== b.shape.length) return false;
    return a.shape.every((v, i) => Math.abs(v - b.shape[i]) < eps);
  }

  const identityIssues = [];
  const extraGraphics = [];

  // Verify the verifier. A comparator that answers "different" to everything makes a
  // perfect build look broken, and one that answers "same" makes a broken build look
  // perfect. Prove it can tell the same file from itself before trusting a single verdict.
  const comparatorOK = !ICONS_DIR ? Promise.resolve(true) : (async () => {
    const probe = Object.values(MANIFEST_FILES)[0];
    if (!probe) return true;
    const a = await signature(ICONS_DIR + '/' + probe + '?a');
    const b = await signature(ICONS_DIR + '/' + probe + '?b');
    if (!a || !b) return true;                    // unsigned icons: nothing to test
    if (!sameIcon(a, b)) {
      reportCrash(new Error('icon comparator says a file differs from itself — '
        + 'every "wrong icon" row below is a lie'));
      return false;
    }
    return true;
  })();

  function auditGraphics(sec, node) {
    const rb = node.getBoundingClientRect();
    // src*= not src$= — the report's own cache-bust pass appends ?BUST to every img src.
    // Small raster images count too: wordmark logos are legitimately PNG (vector extraction
    // can collapse them), and excluding them reads as "icon absent".
    const svgs = [...node.querySelectorAll('svg, img')].filter(e => {
      const src = e.tagName === 'IMG' ? (e.getAttribute('src') || '') : '';
      if (e.tagName !== 'IMG' || src.includes('.svg')) return true;
      const r = e.getBoundingClientRect();
      // wordmark shape only: wide and short. Square/portrait rasters are photos/tiles.
      return r.width <= 400 && r.height <= 120 && r.width >= 2 * r.height;
    });
    const claimed = new Set();
    (sec.icons || []).forEach(b => {
      const tol = Math.max(24, b.w);
      const hit = nearest(svgs, b, rb);
      if (!hit) {
        gfx.icon.missing++;
        gfxIssues.push({s:sec.name, k:'icon', m:`nothing drawn at ${b.x},${b.y} (${b.w}x${b.h})`});
        return;
      }
      if (hit.d > tol) {
        claimed.add(hit.el);          // already reported as misplaced; not also "extra"
        gfx.icon.offset++;
        gfxIssues.push({s:sec.name, k:'icon',
          m:`${b.w}x${b.h} icon belongs at ${b.x},${b.y}; nearest ${hit.el.tagName.toLowerCase()}`
            + ` is ${hit.d}px away (tolerance ${tol}px)`});
        return;
      }
      claimed.add(hit.el);
      if (hit.el.tagName === 'IMG') {
        gfx.icon.asset++;
        // ...but is it the RIGHT icon? Compare what it draws against what the design node
        // exported. "An icon is present" and "the icon belongs here" are different claims.
        if (ICONS_DIR && b.file) {
          identityChecks.push(Promise.all([
            signature(hit.el.getAttribute('src')),
            signature(ICONS_DIR + '/' + b.file),
          ]).then(([got, want]) => {
            if (!want || !got) return;
            if (!sameIcon(got, want)) {
              gfx.icon.wrong++;
              identityIssues.push({s: sec.name, k: 'icon',
                m: `${hit.el.getAttribute('src').split('/').pop()} at ${b.x},${b.y} is not the icon `
                 + `the design puts there (${b.file})`});
            }
          }));
        }
      }
      else { gfx.icon.drawn++; gfxIssues.push({s:sec.name, k:'icon', m:`hand-drawn inline <svg> at ${b.x},${b.y}`}); }
    });

    // ---- reverse audit: graphics the design does not have ----
    // Every check above walks design -> DOM, so anything you ADD to the page is invisible
    // to it. Walk DOM -> design as well, or a stray icon ships looking verified.
    svgs.forEach(e => {
      if (claimed.has(e)) return;
      const r = e.getBoundingClientRect();
      if (!r.width || !r.height) return;             // display:none, e.g. the closed state of a toggle
      gfx.icon.extra++;
      const src = e.tagName === 'IMG' ? e.getAttribute('src').split('/').pop() : 'inline <svg>';
      extraGraphics.push({s: sec.name, k: 'icon',
        m: `${src} at ${Math.round(r.left - rb.left)},${Math.round(r.top - rb.top)} `
         + `has no icon node in the design`});
    });
    const pics = [...node.querySelectorAll('img:not([src$=".svg"]), [style*="background"], *')]
      .filter(e => { const bi = getComputedStyle(e).backgroundImage;
                     return e.tagName === 'IMG' || (bi && bi !== 'none'); });
    (sec.images || []).forEach(b => {
      const pick = nearest(pics, b, rb);
      const el = (pick && pick.d <= Math.max(24, b.w)) ? pick.el : null;
      if (!el) { gfx.image.missing++; gfxIssues.push({s:sec.name, k:'image', m:`missing at ${b.x},${b.y}`}); return; }
      const bi = getComputedStyle(el).backgroundImage;
      const real = el.tagName === 'IMG' ? !!el.currentSrc : /url\(/.test(bi);
      if (real) gfx.image.real++;
      else { gfx.image.placeholder++; gfxIssues.push({s:sec.name, k:'image', m:`gradient placeholder at ${b.x},${b.y}`}); }
    });
  }

  // ---- box audit: fill colour and corner radius of non-text elements ----
  const boxIssues = [];       // real mismatches: wrong fill or wrong radius
  const boxUnmatched = [];    // Figma frame with no 1:1 DOM element — usually structural, not a bug
  function auditBoxes(sec, node) {
    const rb = node.getBoundingClientRect();
    const all = [node, ...node.querySelectorAll('*')];   // the section itself is a box too
    (sec.boxes || []).forEach(b => {
      let best = null, bd = Infinity;
      all.forEach(e => {
        const r = e.getBoundingClientRect();
        if (Math.abs(r.width - b.w) > 4 || Math.abs(r.height - b.h) > 4) return;
        const d = Math.hypot((r.left - rb.left) - b.x, (r.top - rb.top) - b.y);
        if (d < bd) { bd = d; best = e; }
      });
      if (!best || bd > 8) { boxUnmatched.push({s:sec.name, m:`${b.w}x${b.h} at ${b.x},${b.y}`}); return; }
      const cs = getComputedStyle(best);
      const bestR = best.getBoundingClientRect();
      if (b.fill) {
        // A CSS background-image (photo/gradient) covers the colour exactly like a Figma
        // IMAGE fill does — comparing the underlay colour would be a guaranteed false fail.
        const covered = (cs.backgroundImage && cs.backgroundImage !== 'none') || best.tagName === 'IMG';
        let bg = rgb2hex(cs.backgroundColor);
        // Transparent element: the visible paint may live on an inset-0 ::before (e.g. a
        // flipped background layer) — read that before crying mismatch.
        if (!covered && (bg === null || cs.backgroundColor === 'rgba(0, 0, 0, 0)')) {
          const pb = getComputedStyle(best, '::before');
          if (pb.backgroundImage && pb.backgroundImage !== 'none') bg = 'covered';
          else if (pb.backgroundColor && pb.backgroundColor !== 'rgba(0, 0, 0, 0)') bg = rgb2hex(pb.backgroundColor);
          else {
            // A child <img>/<video> filling ≥80% of the box paints it (badge/ring photos)
            const kid = [...best.children].find(k => (k.tagName === 'IMG' || k.tagName === 'VIDEO')
              && k.getBoundingClientRect().width * k.getBoundingClientRect().height
                 >= 0.8 * bestR.width * bestR.height);
            if (kid) bg = 'covered';
          }
        }
        if (!covered && bg !== 'covered' && (bg || '').toLowerCase() !== b.fill.toLowerCase())
          boxIssues.push({s:sec.name, m:`${b.w}x${b.h} fill ${bg} vs ${b.fill}`});
      }
      if (b.radius != null) {
        // Resolve % radii against the element's own box, and clamp both sides to half the
        // short side — 50% on a 108px tile and Figma's 999-style pill are the SAME circle.
        const raw = cs.borderTopLeftRadius || '0';
        let rr = raw.trim().endsWith('%')
          ? parseFloat(raw) / 100 * Math.min(bestR.width, bestR.height)
          : parseFloat(raw) || 0;
        const half = Math.min(b.w, b.h) / 2;
        rr = Math.round(Math.min(rr, half));
        const want = Math.round(Math.min(b.radius, half));
        if (Math.abs(rr - want) > 1)
          boxIssues.push({s:sec.name, m:`${b.w}x${b.h} radius ${rr} vs ${want}`});
      }
      if (b.stroke) {
        // A design stroke may render as any one border side (e.g. a bottom accent bar)
        const side = ['Top','Right','Bottom','Left'].find(x => parseFloat(cs['border'+x+'Width']) > 0);
        const bw = side ? parseFloat(cs['border'+side+'Width']) : 0;
        const bc = bw ? rgb2hex(cs['border'+side+'Color']) : null;
        if (!bw) boxIssues.push({s:sec.name, m:`${b.w}x${b.h} has no border; design strokes it ${b.stroke}`});
        else if (bc.toLowerCase() !== b.stroke.toLowerCase())
          boxIssues.push({s:sec.name, m:`${b.w}x${b.h} border ${bc} vs ${b.stroke}`});
      }
      if (b.shadow && cs.boxShadow === 'none')
        boxIssues.push({s:sec.name, m:`${b.w}x${b.h} has no box-shadow; design has a drop shadow`});
    });
  }

  // ---- motion audit: the design states hover durations; verify what you shipped ----
  const motionIssues = [];
  let motionChecked = 0;
  // Element lookup runs now (geometry is frozen and reliable), but the DURATION read is
  // DEFERRED: the measuring reset above sets `transition:none!important` on everything, so
  // reading transitionDuration here would report "no transition" for a perfectly-animated
  // build — the verifier must not measure what it has itself disabled.
  const motionQueue = [];
  function auditMotion(sec, node) {
    const rb = node.getBoundingClientRect();
    const all = [node, ...node.querySelectorAll('*')];
    (sec.hovers || []).forEach(hv => {
      let best = null, bd = Infinity;
      all.forEach(e => {
        const r = e.getBoundingClientRect();
        if (Math.abs(r.width - hv.w) > 6 || Math.abs(r.height - hv.h) > 6) return;
        const d = Math.hypot((r.left - rb.left) - hv.x, (r.top - rb.top) - hv.y);
        if (d < bd) { bd = d; best = e; }
      });
      if (!best || bd > 8) return;                       // element not found: geometry audits cover it
      // Wrappers, the interactive element and its icon often share the exact box; keep the
      // whole tie set and let the duration read pick whichever actually carries a transition.
      const ties = all.filter(e => {
        const r = e.getBoundingClientRect();
        if (Math.abs(r.width - hv.w) > 6 || Math.abs(r.height - hv.h) > 6) return false;
        return Math.hypot((r.left - rb.left) - hv.x, (r.top - rb.top) - hv.y) <= bd + 1;
      });
      motionQueue.push({sec: sec.name, hv, els: ties.length ? ties : [best]});
    });
  }
  function flushMotion() {
    // Steady-state first: in this hidden iframe the entrance reveal never fires, so its
    // marker attribute (and its own 820ms transition rule) is still on every element and
    // would shadow the hover transition being audited. The live page sheds the marker
    // after the entrance completes — measure that state.
    d.querySelectorAll('[data-reveal], [data-aos]').forEach(e => {
      e.removeAttribute('data-reveal'); e.removeAttribute('data-aos');
      e.classList.remove('is-in', 'in-view', 'is-visible');
    });
    reset.remove();                                       // un-freeze transitions
    void d.documentElement.offsetHeight;
    motionQueue.forEach(({sec, hv, els}) => {
      motionChecked++;
      const ms = Math.max(...els.map(el => {
        const cs = getComputedStyle(el);
        return Math.max(...cs.transitionDuration.split(',').map(v => parseFloat(v) * 1000 || 0));
      }));
      if (ms === 0)
        motionIssues.push({s:sec, m:`${hv.w}x${hv.h} has no transition; design says ${hv.ms}ms ${hv.easing}`});
      else if (Math.abs(ms - hv.ms) > 30)
        motionIssues.push({s:sec, m:`${hv.w}x${hv.h} transition ${Math.round(ms)}ms vs ${hv.ms}ms (${hv.easing})`});
    });
    d.documentElement.appendChild(reset);                 // re-freeze for anything after
    void d.documentElement.offsetHeight;
  }

  // ---- image identity: is the RIGHT photo wired to this node, not merely a photo? ----
  // (icon identity shares the identityIssues list declared with the graphics audit)
  let identityChecked = 0;
  function auditIdentity(sec, node) {
    if (!ASSETS_MAP) return;
    const rb = node.getBoundingClientRect();
    // only elements that actually CARRY an image can be identity candidates — matching
    // "nearest of everything" lands on wrappers/overlays and reads "uses none"
    const pics = [...node.querySelectorAll('*')].filter(e =>
      e.tagName === 'IMG' || getComputedStyle(e).backgroundImage !== 'none');
    // Overlapping design variants often stamp a TEMPLATE's image over the real card's
    // position: several design entries share one spot with different refs. Group them —
    // the build passes if it uses ANY of that spot's refs.
    const spots = new Map();
    (sec.images || []).forEach(im => {
      if (!im.ref || !ASSETS_MAP[im.ref]) return;
      const k = Math.round(im.x/8) + ':' + Math.round(im.y/8);
      if (!spots.has(k)) spots.set(k, {x: im.x, y: im.y, wants: new Set()});
      spots.get(k).wants.add(ASSETS_MAP[im.ref]);
    });
    spots.forEach(im => {
      const wants = [...im.wants];
      const want = wants.join(' | ');
      let best = null, bd = Infinity;
      pics.forEach(e => {
        const r = e.getBoundingClientRect();
        if (!r.width) return;
        const d = Math.hypot((r.left - rb.left) - im.x, (r.top - rb.top) - im.y);
        if (d < bd) { bd = d; best = e; }
      });
      if (!best || bd > 12) return;
      identityChecked++;
      const src = best.tagName === 'IMG' ? (best.getAttribute('src') || '')
                                         : getComputedStyle(best).backgroundImage;
      if (!wants.some(w => src.includes(w)))
        identityIssues.push({s:sec.name, m:`node expects ${want}, element uses ${src.slice(0,60)}`});
    });
  }

  let pass = 0, fail = 0, rows = '';
  SECTIONS.forEach((s, i) => {
    const n = nodes[i];
    const built = n ? Math.round(n.getBoundingClientRect().height) : null;
    const [bl, br] = n ? extents(n) : [null, null];
    const hOK = built === s.h;
    const TOL = 2;
    const xOK = s.contentLeft === null || bl === null
      || (Math.abs(bl - s.contentLeft) <= TOL && Math.abs(br - s.contentRight) <= TOL);
    if (n) { auditText(s, n); auditGraphics(s, n); auditBoxes(s, n); auditMotion(s, n); auditIdentity(s, n); }
    const ok = hOK && xOK;
    ok ? pass++ : fail++;

    const notes = [];
    if (!hOK) notes.push(`height ${built}px vs ${s.h}px (${built - s.h > 0 ? '+' : ''}${built - s.h})`);
    if (!xOK) notes.push(`content x ${bl}–${br} vs ${s.contentLeft}–${s.contentRight}`);
    const v = document.getElementById('v-' + s.name);
    v.textContent = built === null ? 'no element matched' : (ok ? 'matches' : notes.join(' · '));
    v.className = 'verdict ' + (ok ? 'ok' : 'bad');

    rows += `<tr><td>${s.name}</td>
             <td class="${hOK?'ok':'bad'}">${s.h} / ${built ?? '—'}</td>
             <td class="${xOK?'ok':'bad'}">${s.contentLeft ?? '—'}–${s.contentRight ?? '—'} / ${bl ?? '—'}–${br ?? '—'}</td>
             <td class="${ok?'ok':'bad'}">${ok ? 'match' : 'differs'}</td></tr>`;
  });
  flushMotion();   // duration reads must run OUTSIDE the transition-freezing reset

  // Blank-graphic scan: the per-node audits confirm an image is PRESENT, never that it
  // renders as anything. A logo whose vector extraction collapsed into a solid rectangle
  // (e.g. a wordmark exported as overlapping filled paths) passes every other check while
  // showing an empty block. Draw each sizeable same-origin image and flag it if it is a
  // near-uniform opaque block (a shaped icon has transparent surroundings, so it is exempt).
  const blankImgs = [];
  d.querySelectorAll('img').forEach(img => {
    const r = img.getBoundingClientRect();
    if (r.width < 60 || r.height < 12 || !img.complete || !img.naturalWidth) return;
    try {
      const cv = document.createElement('canvas');
      const W = cv.width = Math.min(64, img.naturalWidth), H = cv.height = Math.min(64, img.naturalHeight);
      const cx = cv.getContext('2d');
      cx.drawImage(img, 0, 0, W, H);
      const px = cx.getImageData(0, 0, W, H).data;
      const counts = new Map(); let opaque = 0;
      for (let i = 0; i < px.length; i += 4) {
        if (px[i + 3] < 128) continue;
        opaque++;
        const k = (px[i] >> 4) + ',' + (px[i + 1] >> 4) + ',' + (px[i + 2] >> 4);
        counts.set(k, (counts.get(k) || 0) + 1);
      }
      const total = W * H;
      const top = Math.max(0, ...counts.values());
      if (opaque / total > 0.85 && top / opaque > 0.9) {
        blankImgs.push({src: (img.getAttribute('src') || '').split('/').pop(),
                        wh: `${Math.round(r.width)}x${Math.round(r.height)}`});
      }
    } catch (e) { /* cross-origin: cannot inspect */ }
  });

  const overflow = d.documentElement.scrollWidth > DESIGN_W + 1;
  const totalFigma = SECTIONS.reduce((a, s) => a + s.h, 0);
  const totalBuilt = nodes.reduce((a, n) => a + (n ? Math.round(n.getBoundingClientRect().height) : 0), 0);

  document.getElementById('summary').innerHTML = `
    <div class="stat"><b class="${fail?'bad':'ok'}">${pass}/${SECTIONS.length}</b>sections match (height + content x)</div>
    <div class="stat"><b class="${totalBuilt===totalFigma?'ok':'bad'}">${totalBuilt} / ${totalFigma}</b>total px built / Figma</div>
    <div class="stat"><b class="${overflow?'bad':'ok'}">${overflow?'yes':'no'}</b>horizontal overflow</div>
    <div class="stat"><b>${DESIGN_W}px</b>design width</div>
    <div class="stat"><b class="${UNVERIFIED.length?'bad':'ok'}">${UNVERIFIED.length}</b>sections with no reference</div>
    <div class="stat"><b class="${blankImgs.length?'bad':'ok'}">${blankImgs.length}</b>images that render as a blank block</div>`;
  if (blankImgs.length) {
    document.querySelector('header').insertAdjacentHTML('beforeend',
      `<div class="sub bad" style="margin-top:8px">Render as a solid/blank block (broken logo or
       failed vector extraction — LOOK at them, use the raster export if a wordmark):
       ${blankImgs.map(b => `<code>${b.src} (${b.wh})</code>`).join(', ')}</div>`);
  }
  if (UNVERIFIED.length) {
    document.querySelector('header').insertAdjacentHTML('beforeend',
      `<div class="sub" style="margin-top:8px" class="bad">Not verified by this report (no reference slice):
       <code>${UNVERIFIED.join('</code>, <code>')}</code></div>`);
  }

  const t = document.createElement('table');
  t.innerHTML = `<tr><th>section</th><th>height figma / built</th>
                     <th>content x figma / built</th><th>verdict</th></tr>${rows}`;
  document.querySelector('header').appendChild(t);

  const totalTexts = SECTIONS.reduce((a,s)=>a+(s.texts?s.texts.length:0),0);
  const t2 = document.createElement('table');
  t2.id = 'textAudit';
  const notFoundN = totalTexts - tally.found;
  t2.innerHTML = `<tr><th colspan="3">text audit — of ${totalTexts} design text nodes:
    <b>${tally.found}</b> present in the DOM · <b>${tally.position}</b> at the right position (±4px) ·
    <b>${tally.size}</b> right size · <b>${tally.weight}</b> right weight · <b>${tally.colour}</b> right colour.
    A perfect node is present, positioned, sized, weighted and coloured — ${totalTexts - textIssues.length}
    clear all five.</th></tr>` +
    (textIssues.length
      ? `<tr><th>section</th><th>text</th><th>difference</th></tr>` +
        textIssues.map(i=>`<tr><td>${i.s}</td><td><code>${i.t.replace(/</g,'&lt;')}</code></td>
                            <td class="bad">${i.issue}</td></tr>`).join('')
      : `<tr><td class="ok" colspan="3">no differences</td></tr>`);
  document.querySelector('header').appendChild(t2);

  document.getElementById('summary').insertAdjacentHTML('beforeend',
    `<div class="stat"><b class="${notFoundN?'bad':'ok'}">${tally.found}/${totalTexts}</b>copy present in the DOM</div>
     <div class="stat"><b class="${totalTexts - textIssues.length < totalTexts?'bad':'ok'}">${totalTexts - textIssues.length}/${totalTexts}</b>text nodes fully match</div>`);

  if (selProblems.length) {
    document.querySelector('header').insertAdjacentHTML('beforeend',
      `<div class="sub bad" style="margin-top:8px">Section mapping problems: ${selProblems.join(' · ')}</div>`);
  }
  const totalBoxes = SECTIONS.reduce((a,s)=>a+(s.boxes?s.boxes.length:0),0);
  const checked = totalBoxes - boxUnmatched.length;
  document.getElementById('summary').insertAdjacentHTML('beforeend',
    `<div class="stat"><b class="${boxIssues.length?'bad':'ok'}">${checked - boxIssues.length}/${checked}</b>boxes match fill + radius</div>`);
  const t4 = document.createElement('table');
  t4.id = 'boxAudit';
  t4.innerHTML = `<tr><th colspan="2">box audit — fill colour and corner radius of non-text elements
      (${checked} of ${totalBoxes} design boxes had a 1:1 DOM element; the rest are structural
      differences, not necessarily defects — decide, do not ignore)</th></tr>` +
    (boxIssues.length
      ? `<tr><th>section</th><th>difference</th></tr>` +
        boxIssues.slice(0,40).map(i=>`<tr><td>${i.s}</td><td class="bad">${i.m}</td></tr>`).join('') +
        (boxIssues.length>40?`<tr><td colspan="2">… ${boxIssues.length-40} more</td></tr>`:'')
      : `<tr><td class="ok" colspan="2">no fill or radius differences among matched boxes</td></tr>`);
  document.querySelector('header').appendChild(t4);

  document.getElementById('summary').insertAdjacentHTML('beforeend',
    `<div class="stat"><b class="${motionIssues.length?'bad':'ok'}">${motionChecked - motionIssues.length}/${motionChecked}</b>hover timings match</div>
     <div class="stat"><b class="${ASSETS_MAP ? (identityIssues.length?'bad':'ok') : 'bad'}">${ASSETS_MAP ? (identityChecked - identityIssues.length) + '/' + identityChecked : 'n/a'}</b>images are the RIGHT asset</div>`);
  if (!ASSETS_MAP) {
    document.querySelector('header').insertAdjacentHTML('beforeend',
      `<div class="sub bad" style="margin-top:8px">No --assets-map given: this report checks that
       <em>a</em> photo is present, never that it is the <em>right</em> photo.</div>`);
  }
  const otherBps = BREAKPOINTS.filter(w => w !== DESIGN_W);
  if (otherBps.length) {
    document.querySelector('header').insertAdjacentHTML('beforeend',
      `<div class="sub bad" style="margin-top:8px">Confirmed breakpoints NOT covered by this report:
       <code>${otherBps.join('px</code>, <code>')}px</code>. Each is a separate design: build it and
       run this report against it. A responsive layout you inferred is not a substitute.</div>`);
  }

  [[motionIssues, 'motionAudit', 'motion audit — hover transition durations vs the design'],
   [identityIssues, 'identityAudit', 'image identity — is the right photo wired to this node?']]
   .forEach(([issues, id, title]) => {
     const t = document.createElement('table');
     t.id = id;
     t.innerHTML = `<tr><th colspan="2">${title}</th></tr>` +
       (issues.length
         ? `<tr><th>section</th><th>difference</th></tr>` +
           issues.slice(0,30).map(i=>`<tr><td>${i.s}</td><td class="bad">${i.m}</td></tr>`).join('') +
           (issues.length>30?`<tr><td colspan="2">… ${issues.length-30} more</td></tr>`:'')
         : `<tr><td class="ok" colspan="2">no differences</td></tr>`);
     document.querySelector('header').appendChild(t);
   });

  const totalImgs = gfx.image.real + gfx.image.placeholder + gfx.image.missing;
  // The identity checks fetch files; nothing may be reported until they all land.
  Promise.all([comparatorOK, ...identityChecks]).catch(() => {}).then(() => {
  const allGfx = gfxIssues.concat(identityIssues, extraGraphics);
  const totalIcons = gfx.icon.asset + gfx.icon.drawn + gfx.icon.missing + gfx.icon.offset;
  const right = gfx.icon.asset - gfx.icon.wrong;
  const iconBad = gfx.icon.drawn || gfx.icon.missing || gfx.icon.offset || gfx.icon.wrong || gfx.icon.extra;
  document.getElementById('summary').insertAdjacentHTML('beforeend',
    `<div class="stat"><b class="${iconBad?'bad':'ok'}">${right}/${totalIcons}</b>icons: right asset, right place</div>
     <div class="stat"><b class="${gfx.icon.extra?'bad':'ok'}">${gfx.icon.extra}</b>graphics the design has no node for</div>
     <div class="stat"><b class="${gfx.image.placeholder||gfx.image.missing?'bad':'ok'}">${gfx.image.real}/${totalImgs}</b>images are real photos</div>`);

  const t3 = document.createElement('table');
  t3.id = 'gfxAudit';
  t3.innerHTML = `<tr><th colspan="3">graphics audit — icons: ${right} correct,
      ${gfx.icon.wrong} wrong icon on the node, ${gfx.icon.offset} placed wrong,
      ${gfx.icon.drawn} hand-drawn, ${gfx.icon.missing} absent, ${gfx.icon.extra} not in the design ·
      images: ${gfx.image.real} real, ${gfx.image.placeholder} placeholder, ${gfx.image.missing} missing</th></tr>` +
    (gfx.icon.unsigned ? `<tr><td class="bad" colspan="3">${gfx.icon.unsigned} icon(s) on the page carry
      no <code>data-icon-shape</code>: they were not produced by figma_icons.py, so nothing can say
      whether they are the right drawing. Re-export them.</td></tr>` : '') +
    (ICONS_DIR ? '' : `<tr><td class="bad" colspan="3">No icons.json manifest found: this report
      checks that <em>an</em> icon is present, never that it is the <em>right</em> icon.
      Run figma_icons.py first, or pass --icons-dir.</td></tr>`) +
    (allGfx.length
      ? `<tr><th>section</th><th>kind</th><th>problem</th></tr>` +
        allGfx.slice(0, 60).map(i=>`<tr><td>${i.s}</td><td>${i.k}</td><td class="bad">${i.m}</td></tr>`).join('') +
        (allGfx.length > 60 ? `<tr><td colspan="3">… ${allGfx.length - 60} more</td></tr>` : '')
      : `<tr><td class="ok" colspan="3">every icon is the design's own asset, in the design's own place,
          and nothing is drawn that the design does not have</td></tr>`);
  document.querySelector('header').appendChild(t3);
  if (SUBSTITUTED.size) {
    document.querySelector('header').insertAdjacentHTML('beforeend',
      `<div class="sub" style="margin-top:8px">Font substitutions in effect (weight not compared):
       <code>${[...SUBSTITUTED].join('</code>, <code>')}</code></div>`);
  }
  });
 } catch (err) { reportCrash(err); }
});
</script>
"""


MANIFEST = {}


def load_manifest(d):
    f = pathlib.Path(d) / "icons.json"
    if f.exists():
        MANIFEST.update(json.loads(f.read_text()))
    return bool(MANIFEST)


def selfcheck(path):
    """The report is a program. If it does not parse, it silently shows 'measuring…' forever
    and a reader takes that for 'still working'. Refuse to hand over a broken one."""
    import re, shutil, subprocess, tempfile
    node = shutil.which("node")
    if not node:
        return
    m = re.findall(r"<script>(.*?)</script>", pathlib.Path(path).read_text(), re.S)
    if not m:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(m[-1])
        tmp = f.name
    r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"BUG in figma_report.py: the report it just wrote does not parse.\n{r.stderr}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default="index.html")
    ap.add_argument("--nodes", default="figma/nodes")
    ap.add_argument("--renders", default="figma/renders")
    ap.add_argument("--selectors", default=None)
    ap.add_argument("--only", default=None,
                    help="verify a single section while you are building it (§6.5.5)")
    ap.add_argument("--breakpoints", default=None,
                    help="comma-separated widths the user confirmed are real breakpoints; "
                         "any width other than this report's is flagged as unbuilt")
    ap.add_argument("--assets-map", default=None,
                    help="JSON {imageRef: filename} so image IDENTITY can be checked, "
                         "not just 'a photo is present'")
    ap.add_argument("--out", default="fidelity-report.html")
    ap.add_argument("--icons-dir", default="design/exports/icons",
                    help="output of figma_icons.py; enables the icon-identity check")
    a = ap.parse_args()
    have_manifest = load_manifest(a.icons_dir)

    sections = load_sections(a.nodes, a.renders)
    known = {pathlib.Path(f).stem for f in glob.glob(os.path.join(a.nodes, "*.json"))}
    unverified = sorted(known - {s["name"] for s in sections})
    if a.only:
        sections = [s for s in sections if s["name"] == a.only]
        if not sections:
            raise SystemExit(f"no section named {a.only!r}")
    design_w = max(s["w"] for s in sections)
    selectors = json.load(open(a.selectors)) if a.selectors else None

    bps = [int(x) for x in a.breakpoints.split(",")] if a.breakpoints else []
    amap = json.load(open(a.assets_map)) if a.assets_map else None
    html = (HTML
            .replace("__BREAKPOINTS__", json.dumps(bps))
            .replace("__ASSETS_MAP__", json.dumps(amap))
            .replace("__UNVERIFIED__", json.dumps(unverified))
            .replace("__SECTIONS__", json.dumps(sections))
            .replace("__PAGE__", a.page)
            .replace("__DESIGN_W__", str(design_w))
            .replace("__SELECTORS__", json.dumps(selectors))
            .replace("__ICONS_DIR__", json.dumps(a.icons_dir if have_manifest else None))
            .replace("__MANIFEST__", json.dumps(MANIFEST)))
    pathlib.Path(a.out).write_text(html)
    selfcheck(a.out)

    print(f"wrote {a.out}  ({len(sections)} section(s), design width {design_w}px)")
    print("Serve the project and open it — the numbers are computed live, in the browser.")
    print("Hand the user this file. Do not claim a match it does not show.")


if __name__ == "__main__":
    main()
