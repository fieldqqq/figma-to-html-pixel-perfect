# figma-to-html-pixel-perfect

A Claude Code / Claude Agent skill that turns a Figma design into production HTML & CSS
with verified visual fidelity — and refuses to guess when it can't see the design.

It exists because the naive approach ("read the Figma JSON, write the CSS") reliably
produces a page whose section heights match to the pixel and whose design is completely
wrong. Every rule in `SKILL.md` is a guard against a failure that actually happened.

## What it does

- **Looks at the whole file first**: other design widths are other designs (build them, do
  not guess them); an icon that ships in the file is never redrawn; hover variants named by
  `interactions[]` are fetched, not invented.
- Pulls **exact values** from the Figma REST API (geometry, auto-layout, colour tokens,
  real text, image refs) — not eyeballed from a screenshot.
- Pulls **one reference render per section**, and refuses to implement a section it
  hasn't looked at.
- Builds **section by section**, verifying each one visually *and* numerically before
  moving on.
- **Measures** font substitutions instead of guessing them.
- **Reproduces the motion the file already specifies** (`interactions[]`) as fidelity work,
  and only asks approval for motion it would invent.
- Tells you up front which fonts the design needs and where to put them.
- Separates exact implementation from inferred behaviour from optional enhancement, and
  asks before changing the design.
- Reports blocked sections as blocked, instead of shipping a geometry-only guess.
- Names, in the report, every breakpoint it did **not** build and every check it did **not** run.
- Audits in **both** directions: the design's nodes against the page, and the page's graphics
  against the design. Anything you added that the design has no node for is listed.
- Checks *which* icon landed on a node, not merely that one did.
- **Builds from the numbers**, not from the picture: spacing comes from `itemSpacing`,
  type from each TEXT node's `style`, copy verbatim from `characters`, icons from exported
  vectors. A linter rejects any value — or any hand-drawn icon — the design never had.
- Ends with a **fidelity report** the user can open: every section, reference beside the
  live page, cross-fade and difference-blend, height and content-extent checks, and a
  per-text-node audit of position, size, weight and colour.

## Install

**Personal skill**

```bash
git clone https://github.com/fieldqqq/figma-to-html-perfect-pixel \
  ~/.claude/skills/figma-to-html-pixel-perfect
```

**Project skill**

```bash
git clone https://github.com/fieldqqq/figma-to-html-perfect-pixel \
  .claude/skills/figma-to-html-pixel-perfect
```

Restart the session; the skill is picked up automatically, or invoke it explicitly with
`/figma-to-html-pixel-perfect`.

## Requirements

- **Claude Code** (or any Claude agent runtime that reads `SKILL.md` skills)
- **Python 3.9+** — the scripts use only the standard library (no `pip install`)
- A modern browser for the fidelity report (it computes its numbers live, in-page)
- A **Figma personal access token** (below); a paid Figma seat is NOT required —
  everything runs over the REST API. Note the REST API has **plan-based monthly quotas
  on every endpoint** (even node JSON can 429 for hours) — the skill works cache-first,
  so each node is fetched once and everything afterwards runs offline from `figma/nodes/`

## Setup (one-time)

1. **Figma token** — figma.com → Settings → Security → Personal access tokens,
   scope `File content: Read`:

   ```bash
   echo 'YOUR_TOKEN' > ~/.figma_token && chmod 600 ~/.figma_token
   ```

   Never paste the token into the chat.

2. **Export permission** — the scripts preflight this. If you get
   `403 File not exportable`, the file owner has disabled export/copy/share; only they
   (or an editor) can re-enable it in the Share dialog.

3. **Font files** — on first run the skill reports, from *your* file, exactly which faces
   the design renders and which of them are licensed. Drop those into `design/fonts/` and
   they are used automatically. Free faces are loaded from a CDN and are never asked for.
   Without the licensed files the skill measures a substitute and says so; the type will
   not be exact.

See `SKILL.md` §0 for the full checklist.

## Usage

Give it a **node-specific** Figma URL:

```
implement this Figma as pixel-perfect HTML/CSS — Mode A (exact, no redesign)
URL: https://figma.com/design/<fileKey>/<fileName>?node-id=<nodeId>

- pull real values via the REST API; do not eyeball from screenshots
- download the real assets; no placeholders
- framework: plain HTML/CSS
- responsive: desktop + tablet + mobile
- verify each section against its render, then give me a difference log
- reproduce any motion the file specifies; propose anything it doesn't
- do not add shadows/sections that aren't in the design
```

Modes: **A** = exact reproduction · **B** = exact + suggestions (approval required) ·
**C** = implement approved enhancements only.

## Scripts

```bash
# FIRST: what is in this file that you are about to ignore?
#   breakpoints · icon library · hover variants · how many screens
python3 scripts/figma_discover.py <fileKey> --nodes figma/nodes --json figma/discovery.json

# node JSON + one render per section (preflights access, fails loudly)
python3 scripts/figma_pull.py <fileKey> <nodeId>[,<nodeId>...] figma/

# accurate spec for one node: characters / textCase / fills / strokes / radii / layout
python3 scripts/figma_spec.py figma/nodes/<nodeId>.json 6

# which fonts the design really renders, split free vs licensed  -> report this first
python3 scripts/figma_fonts.py figma/nodes/*.json

# every icon the page draws, extracted offline from the page SVG (no API, no quota)
python3 scripts/figma_icons.py --svg design/exports/page.svg --nodes figma/nodes

# build-stage guard: spacing / sizes / colours / <br> that exist nowhere in the design
python3 scripts/figma_lint.py --css css/styles.css --html index.html --nodes figma/nodes

# fidelity report: reference vs live page, difference blend, and audits of every
# text node, icon, image, box (fill/radius/stroke/shadow) and hover duration
python3 scripts/figma_report.py --page index.html --selectors selectors.json \
    --breakpoints 1600,402 --assets-map assets-map.json --icons-dir design/exports/icons

# verify ONE section while you are still building it
python3 scripts/figma_report.py --only <section> --out /tmp/one.html
```

The two guards catch different things. `figma_lint.py` runs **before** you look: it fails on
any `gap`, `font-size` or colour that appears nowhere in the node JSON — invented spacing is
what later shows up as a hundred vertical offsets. `figma_report.py` runs **after**: it
compares every Figma TEXT node against the DOM for position, size, weight and colour.

> Matching section heights proves almost nothing. In one build every section matched on
> height and content extents while only **10 of 224 text nodes** — and **17 of 114 icons** —
> actually did. Geometry is a smoke test, not a verdict.

The report also audits, per section: every icon (the design's own asset, hand-drawn, or
missing — and *which* icon, via shape signatures), every image (real photo vs placeholder,
and *which* photo, via `--assets-map`), every non-text box (fill, radius, stroke, shadow),
and every hover transition duration vs the design's `interactions[]`. It states plainly
what it still does **not** check (hover *appearance*, z-order, viewports you didn't run it
at) so a green report is never mistaken for proof.

`figma_fonts.py` excludes hidden subtrees *and* nodes whose cumulative ancestor `opacity`
is 0, and reads per-character overrides — so it will not send you chasing a licensed font
the design never actually shows.

`figma_spec.py` marks image fills carrying an `imageTransform` (rotation/flip) as
`IMG(<ref>*)` — ignore that asterisk and your background will render upside-down.

## If the API rate-limits you

Renders (`GET /v1/images`) are the scarcest, but **every** endpoint — including
`/v1/files` node JSON — sits under a plan-based quota and can 429 with an hours-long
Retry-After. The skill is built for this: node JSON is pulled once and cached in
`figma/nodes/` (the puller skips anything already on disk), and all scripts read the
cache, never the API. If you hit 429 mid-acquisition, the error prints the Retry-After;
everything already cached keeps working. When it 429s, ask for a **PNG @2x export of the page frame** and slice it
locally using the section offsets from the JSON. If you use **SVG** as a visual
reference, you must enable **"Outline text"** on export — otherwise the SVG references a
font you don't have and the reference lies to you. Details in `SKILL.md` §6.5.2.

## Layout

```
figma-to-html-pixel-perfect/
├── SKILL.md                          # the skill itself
├── README.md
├── references/
│   ├── visual-review-checklist.md
│   ├── accessibility-checklist.md    # WCAG 2.2 AA
│   └── animation-guidelines.md       # motion in the file = required; motion you invent = approval
└── scripts/
    ├── figma_discover.py
    ├── figma_icons.py
    ├── figma_pull.py
    ├── figma_spec.py
    ├── figma_fonts.py
    ├── figma_lint.py
    └── figma_report.py
```

## Core principle

The Figma design is the visual source of truth. Implement first, verify second,
recommend third, and change the design only after the user approves.

Never claim "100% identical" without comparison evidence. Matching section heights is
not that evidence.
