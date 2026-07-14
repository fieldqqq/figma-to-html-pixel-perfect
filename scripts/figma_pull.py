#!/usr/bin/env python3
"""Fetch node JSON + one render per section from the Figma REST API.

Implements §6.5.1 (preflight) and §6.5.2 (spend the render budget first).

Deliberately does NOT bulk-download image fills: that burns the shared quota the
renders need. Fetch assets afterwards, only for the refs you actually use
(see `download_refs`).

Token: env FIGMA_TOKEN, else ~/.figma_token  (scope: File content: Read)

Usage:
    python3 figma_pull.py <fileKey> <nodeId>[,<nodeId>...] [outdir]
    python3 figma_pull.py <fileKey> --hover <destId>[,<destId>...] [outdir]

`--hover` fetches the variant nodes that `interactions[].destinationId` points at (find them
with figma_discover.py) and renders each one. Those renders are the reference for the hover
state; nothing else in this toolkit can tell you what a hover is supposed to look like.

Writes:
    <outdir>/nodes/<nodeId>.json     full node tree
    <outdir>/renders/<nodeId>.png    one render per node  <-- LOOK AT THESE
"""
import json, os, sys, time, pathlib, urllib.parse, urllib.request

API = "https://api.figma.com/v1"


def token():
    if os.environ.get("FIGMA_TOKEN"):
        return os.environ["FIGMA_TOKEN"].strip()
    p = pathlib.Path.home() / ".figma_token"
    if p.exists():
        return p.read_text().strip()
    sys.exit("No token. figma.com > Settings > Security > Personal access tokens\n"
             "then: echo 'TOKEN' > ~/.figma_token && chmod 600 ~/.figma_token")


def get(path, tok):
    req = urllib.request.Request(API + path, headers={"X-Figma-Token": tok})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read(300).decode(errors="replace")
        if e.code == 429:
            ra = e.headers.get("Retry-After")
            hrs = f" ({int(ra)/3600:.1f} h)" if ra and ra.isdigit() else ""
            sys.exit(f"429 rate limited. Retry-After: {ra}{hrs}\n"
                     f"Do not plan around a quick reset. {body}")
        if e.code == 403 and "not exportable" in body:
            sys.exit("403 File not exportable — the owner disabled export/copy/share.\n"
                     "Only the owner (or an editor) can lift this. Nothing else will work.")
        sys.exit(f"HTTP {e.code}: {body}")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    argv = sys.argv[1:]
    hover = False
    if "--hover" in argv:
        hover = True
        argv.remove("--hover")
    force = "--force" in argv
    if force:
        argv.remove("--force")
    key, ids = argv[0], [i.strip().replace("-", ":") for i in argv[1].split(",")]
    out = pathlib.Path(argv[2] if len(argv) > 2 else "figma")
    tok = token()
    # CACHE-FIRST. Every REST endpoint (including /v1/files) sits under a plan-based
    # monthly quota and 429s with Retry-After up to hours/days. A node that is already
    # on disk is NEVER re-fetched — the cache is the workspace, the API is only for
    # what is missing. Use --force to deliberately refresh.
    if not force:
        cached = [i for i in ids if (out / "nodes" / f"{i.replace(':','-')}.json").exists()]
        if cached:
            print(f"cache-first: {len(cached)}/{len(ids)} node(s) already in {out}/nodes — skipped "
                  f"(--force to re-fetch)")
        ids = [i for i in ids if i not in cached]
        if not ids:
            return
    if hover:
        (out / "hover").mkdir(parents=True, exist_ok=True)
        nodes = get(f"/files/{key}/nodes?ids={urllib.parse.quote(','.join(ids))}", tok)
        for nid in ids:
            n = nodes["nodes"].get(nid)
            if n:
                (out / "hover" / f"{nid.replace(':','-')}.json").write_text(
                    json.dumps(n, indent=2, ensure_ascii=False))
        for nid in ids:
            r = get(f"/images/{key}?ids={urllib.parse.quote(nid)}&format=png&scale=2", tok)
            url = (r.get("images") or {}).get(nid)
            if not url:
                print(f"  !! no render for hover variant {nid}")
                continue
            with urllib.request.urlopen(url, timeout=240) as im:
                (out / "hover" / f"{nid.replace(':','-')}.png").write_bytes(im.read())
            print(f"  hover variant {nid}")
            time.sleep(1)
        print("\nLook at these. Then make your :hover match them (§9.0).")
        return

    # §6.5.1 preflight — fail fast with the real reason
    get(f"/files/{key}?depth=1", tok)
    print("preflight ok: file is readable and exportable")

    (out / "nodes").mkdir(parents=True, exist_ok=True)
    (out / "renders").mkdir(parents=True, exist_ok=True)

    # 1) node trees (single call)
    nodes = get(f"/files/{key}/nodes?ids={urllib.parse.quote(','.join(ids))}", tok)
    for nid in ids:
        n = nodes["nodes"].get(nid)
        if n:
            (out / "nodes" / f"{nid.replace(':','-')}.json").write_text(
                json.dumps(n, indent=2, ensure_ascii=False))
    print(f"saved {len(ids)} node trees -> {out}/nodes/")

    # 2) ONE RENDER PER SECTION — the scarce budget. Fail loudly, never silently.
    failed = []
    for nid in ids:
        r = get(f"/images/{key}?ids={urllib.parse.quote(nid)}&format=png&scale=1", tok)
        url = (r.get("images") or {}).get(nid)
        if not url:
            failed.append(nid)
            print(f"  !! NO RENDER for {nid} (err={r.get('err')})", flush=True)
            continue
        with urllib.request.urlopen(url, timeout=240) as im:
            (out / "renders" / f"{nid.replace(':','-')}.png").write_bytes(im.read())
        print(f"  rendered {nid}", flush=True)
        time.sleep(1)

    if failed:
        sys.exit(f"\nBLOCKED: {len(failed)} section(s) have no reference render: {failed}\n"
                 "Per §6.5.0 these must NOT be implemented from geometry alone.\n"
                 "Report them to the user and ask for screenshots.")
    print("\nAll sections rendered. Now OPEN EVERY RENDER before writing any code.")


def download_refs(key, refs, dest="assets"):
    """Fetch only the imageRefs you actually use. Call after the renders exist."""
    tok = token()
    m = get(f"/files/{key}/images", tok)["meta"]["images"]
    pathlib.Path(dest).mkdir(parents=True, exist_ok=True)
    for name, ref in refs.items():
        with urllib.request.urlopen(m[ref], timeout=240) as r:
            pathlib.Path(f"{dest}/{name}.png").write_bytes(r.read())
        print("saved", name)


if __name__ == "__main__":
    main()
