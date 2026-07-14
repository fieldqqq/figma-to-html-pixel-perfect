#!/usr/bin/env python3
"""Report every font the design actually renders, and which ones the user must supply.

Run this once, before writing any CSS, and paste the output to the user (§0.3, §17.A).

It is careful about three things that trip people up:
  * `characters` styling can be overridden per character -> also read `styleOverrideTable`
  * `visible: false` subtrees never render -> skipped
  * a node can be `visible: true` and still render nothing -> effective (cumulative)
    ancestor `opacity` of 0 is skipped too

Usage:
    python3 figma_fonts.py figma/nodes/*.json
"""
import json, sys
from collections import Counter

# Common families served free by Google Fonts. Not exhaustive — anything not listed is
# reported as "verify"; check fonts.google.com before asking the user for it.
GOOGLE = {
    "abril fatface", "bodoni moda", "cormorant garamond", "dm sans", "dm serif display",
    "eb garamond", "figtree", "fraunces", "geist", "ibm plex sans", "inter", "instrument sans",
    "jost", "karla", "lato", "libre baskerville", "lora", "manrope", "merriweather",
    "montserrat", "mulish", "nunito", "open sans", "outfit", "playfair display", "poppins",
    "prata", "public sans", "quicksand", "raleway", "roboto", "rubik", "source sans 3",
    "space grotesk", "spectral", "syne", "urbanist", "work sans",
}


def collect(paths):
    faces = Counter()          # postScriptName -> render count
    families = {}              # postScriptName -> family
    for p in paths:
        doc = json.load(open(p))
        doc = doc["document"] if "document" in doc else doc

        def walk(n, opacity=1.0):
            if n.get("visible") is False:
                return
            opacity *= n.get("opacity", 1)
            if opacity == 0:                      # renders nothing, needs no font
                return
            if n.get("type") == "TEXT":
                styles = [n.get("style", {})]
                styles += list((n.get("styleOverrideTable") or {}).values())
                for st in styles:
                    ps = st.get("fontPostScriptName")
                    if not ps:
                        continue
                    faces[ps] += 1
                    families[ps] = st.get("fontFamily") or ps.split("-")[0]
            for c in n.get("children", []) or []:
                walk(c, opacity)

        walk(doc)
    return faces, families


def main():
    paths = sys.argv[1:]
    if not paths:
        sys.exit(__doc__)
    faces, families = collect(paths)
    if not faces:
        sys.exit("No TEXT nodes found — wrong files?")

    free, licensed = [], []
    for ps, n in faces.most_common():
        (free if (families[ps] or "").lower() in GOOGLE else licensed).append((ps, families[ps], n))

    print("Fonts this design actually renders\n")
    if licensed:
        print("LICENSED — the user must supply these (drop into design/fonts/):")
        for ps, fam, n in licensed:
            print(f"  {ps}.woff2   (or .otf)   family={fam!r}  used x{n}")
    if free:
        print("\nFREE — load these yourself from a CDN, do not ask the user:")
        for ps, fam, n in free:
            print(f"  {ps}   family={fam!r}  used x{n}")

    print("\nNotes:")
    print("  * families not in the built-in Google list are reported as LICENSED —")
    print("    check fonts.google.com before asking the user for one.")
    print("  * hidden nodes and nodes with effective opacity 0 were excluded, so this")
    print("    list is what the page really needs.")
    print("  * font files cannot be extracted from the REST API or from an SVG export.")


if __name__ == "__main__":
    main()
