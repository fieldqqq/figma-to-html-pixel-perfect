#!/usr/bin/env python3
"""Discovery: find everything in the file you are about to ignore.

Run this FIRST, before the node dump, before the renders, before a single line of CSS —
and show the output to the user. It answers four questions that decide the whole job:

  1. how many design widths are in this file?      -> breakpoints you must build, not guess
  2. is there an icon library?                     -> icons you must export, not draw
  3. do any interactions point at hover variants?  -> states you must reproduce, not invent
  4. how many page-sized frames are there?         -> screens you may have been asked for

Missing any of these is not a small error. Guessing a mobile layout that the designer
already drew, or hand-drawing icons that ship as components in the same file, produces
work that is wrong on purpose.

Usage:
    python3 figma_discover.py <fileKey> [--nodes figma/nodes] [--json out.json]

Token: env FIGMA_TOKEN, else ~/.figma_token
"""
import argparse, glob, json, os, pathlib, re, sys, urllib.request
from collections import Counter, defaultdict

API = "https://api.figma.com/v1"
ICON_MAX = 64          # a frame this small is an icon, not a screen
SCREEN_MIN_H = 1200    # a screen is tall
SCREEN_MIN_W, SCREEN_MAX_W = 320, 1920
# Names that mean "pasted asset", not "screen we must build". Scratch pages are full of
# them and they otherwise drown the breakpoint list.
ASSET_RE = re.compile(
    r"^(image|screencapture|group|rectangle|vector|ellipse|union|mask|isolation_mode|"
    r"frame \d+|frame \d{6,})", re.I)


def token():
    if os.environ.get("FIGMA_TOKEN"):
        return os.environ["FIGMA_TOKEN"].strip()
    p = pathlib.Path.home() / ".figma_token"
    if p.exists():
        return p.read_text().strip()
    sys.exit("No token. See SKILL.md §0.1")


CACHE = pathlib.Path("figma/_api_cache")


def get(path, tok, required=True):
    """Cache every response. EVERY REST endpoint shares a rate-limit budget — the render
    endpoint exhausts first, but /files and /nodes will 429 too. A cached answer is always
    better than a dead run."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / (re.sub(r"[^\w.-]", "_", path)[:120] + ".json")
    if key.exists():
        return json.loads(key.read_text())
    req = urllib.request.Request(API + path, headers={"X-Figma-Token": tok})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.load(r)
        key.write_text(json.dumps(data))
        return data
    except urllib.error.HTTPError as e:
        body = e.read(200).decode(errors="replace")
        if e.code == 429:
            ra = e.headers.get("Retry-After")
            msg = f"429 rate limited on {path}. Retry-After: {ra}"
            if required:
                sys.exit(msg + "\n  Every REST endpoint shares a budget, not just /images.")
            print(f"  ! {msg} — skipping this part of discovery")
            return None
        if e.code == 403 and "not exportable" in body:
            sys.exit("403 File not exportable — the owner disabled export/copy/share (§0.2).")
        sys.exit(f"HTTP {e.code}: {body}")


def size(n):
    bb = n.get("absoluteBoundingBox") or {}
    return round(bb.get("width", 0)), round(bb.get("height", 0))


def hover_destinations(nodes_dir):
    """destinationId of every ON_HOVER action, and whether we already have that node."""
    dests, have = Counter(), set()
    for f in glob.glob(os.path.join(nodes_dir, "*.json")):
        d = json.load(open(f))
        d = d["document"] if "document" in d else d

        def walk(n):
            if n.get("visible") is False:
                return
            have.add(n.get("id"))
            for it in n.get("interactions") or []:
                if (it.get("trigger") or {}).get("type") == "ON_HOVER":
                    for a in it.get("actions") or []:
                        if a.get("destinationId"):
                            dests[a["destinationId"]] += 1
            for c in n.get("children", []) or []:
                walk(c)

        walk(d)
    return dests, have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fileKey")
    ap.add_argument("--nodes", default="figma/nodes",
                    help="cached node JSON, to find hover destinations (optional)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    doc = get(f"/files/{a.fileKey}?depth=2", token())["document"]

    widths = Counter()
    screens, icons, icon_pages, components, skipped = [], [], [], [], 0
    for page in doc.get("children", []):
        pname = page.get("name", "")
        kids = page.get("children") or []
        is_icon_page = "icon" in pname.lower() and bool(kids)
        if is_icon_page:
            icon_pages.append(pname)
        for k in kids:
            w, h = size(k)
            name = k.get("name", "")
            entry = {"page": pname, "name": name, "w": w, "h": h, "type": k.get("type")}
            if k.get("type") in ("COMPONENT", "COMPONENT_SET"):
                components.append(entry)
            if 0 < w <= ICON_MAX and 0 < h <= ICON_MAX:
                icons.append(entry)
                continue
            if is_icon_page or ASSET_RE.match(name):
                skipped += 1
                continue
            if (SCREEN_MIN_W <= w <= SCREEN_MAX_W and h >= SCREEN_MIN_H
                    and h >= w * 1.5):
                widths[w] += 1
                screens.append(entry)

    out = {"widths": dict(widths), "screens": screens, "icons": icons,
           "icon_pages": icon_pages, "components": components}

    print("CANDIDATE DESIGN WIDTHS (a heuristic — confirm with the user which are breakpoints)")
    print(f"  (ignored {skipped} pasted assets and icon-page frames)")
    for w, n in widths.most_common():
        tallest = max((s for s in screens if s["w"] == w), key=lambda s: s["h"])
        print(f"  {w:>5}px  x{n:<3} tallest: {tallest['name'][:44]!r} ({tallest['h']}px, page {tallest['page']!r})")
    if len(widths) > 1:
        print("\n  -> More than one width. Some of these are cards or scratch frames, not")
        print("     breakpoints. Ask the user which are real, then run the whole loop per")
        print("     confirmed width. If a mobile frame exists, INFERRING a mobile layout")
        print("     instead of building that frame is a fabrication.\n")
    else:
        print("\n  -> one width only; responsive behaviour is genuinely inferred (label it).\n")

    # An icon page's real components live below depth 2; fetch those pages properly.
    lib = []
    for page in doc.get("children", []):
        if page.get("name") in icon_pages:
            node = get(f"/files/{a.fileKey}/nodes?ids={page['id']}", token(), required=False)
            if not node:
                continue
            root = node["nodes"][page["id"]]["document"]

            def walk(n):
                w, h = size(n)
                # the icons themselves, whatever type the designer used
                if 0 < w <= ICON_MAX and 0 < h <= ICON_MAX and n.get("name"):
                    lib.append({"name": n["name"], "id": n["id"], "w": w, "h": h})
                    return
                for c in n.get("children", []) or []:
                    walk(c)

            walk(root)
    out["icon_library"] = lib

    print(f"ICON LIBRARY: {len(icons)} icon-sized top-level frames"
          + (f"; icon pages: {icon_pages}" if icon_pages else ""))
    if lib:
        names = sorted({i["name"] for i in lib})
        print(f"  {len(lib)} icons inside those pages ({len(names)} distinct names)")
        print("  sample: " + ", ".join(names[:8]))
    if icons or lib:
        print("  -> export these. Hand-drawing an icon that ships in the file is never acceptable.\n")
    else:
        print("  -> none found; icons must still be extracted from the page SVG, not drawn.\n")

    print(f"COMPONENTS / VARIANTS at top level: {len(components)}")
    if components:
        print("  -> reuse implies shared CSS components; variants imply states.\n")
    else:
        print()

    if os.path.isdir(a.nodes):
        dests, have = hover_destinations(a.nodes)
        missing = [d for d in dests if d not in have]
        print(f"HOVER VARIANTS: {sum(dests.values())} ON_HOVER actions -> {len(dests)} destination nodes")
        print(f"  not in your cache: {len(missing)}  {missing[:5]}")
        if missing:
            print("  -> fetch them and compare your :hover against the real variant (§9.0).\n")
        out["hover_destinations"] = {"all": list(dests), "missing": missing}
    else:
        print("HOVER VARIANTS: no node cache yet; re-run after figma_pull.py\n")

    page_screens = defaultdict(list)
    for s in screens:
        page_screens[s["page"]].append(s["name"])
    print("PAGE-SIZED FRAMES PER FIGMA PAGE (are you being asked for one screen, or a site?)")
    for p, names in page_screens.items():
        print(f"  {p!r}: {len(names)}")

    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")

    print("\nShow this output to the user before you write any code.")


if __name__ == "__main__":
    main()
