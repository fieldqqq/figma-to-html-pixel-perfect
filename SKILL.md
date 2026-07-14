---
name: figma-to-html-pixel-perfect
description: >
  Convert Figma designs, screenshots, design specifications, and design-system references
  into production-ready HTML and CSS with maximum visual fidelity. Use this skill whenever
  the user asks to recreate, implement, audit, improve, or make a website match a Figma design.
  The skill must distinguish exact design implementation from optional UX/UI enhancements,
  ask permission before making visible design changes, and verify responsiveness,
  accessibility, animations, and visual consistency.
---

# Figma to HTML/CSS — Pixel-Perfect Implementation Skill

## 0. Setup (one-time, before first use)

The skill needs read access to the Figma file. Walk the user through this once; do not
guess or skip it.

### 0.1 Figma personal access token (required)

The REST API is the source of every value (geometry, tokens, text, image refs). It is not
seat-limited like the MCP server, but it IS quota-limited per plan: **every endpoint —
including `/v1/files` (node JSON) — can 429 with a Retry-After of hours to days** (observed
live: /files 429 Retry-After 22,734s while the fill-URL endpoint still answered 200).
Therefore work **cache-first**: pull each node's JSON ONCE to `figma/nodes/`, then every
script reads the disk cache — never the API. `figma_pull.py` skips nodes already on disk
(`--force` to refresh). Scarcity order: `/v1/images` (renders) most scarce → `/v1/files`
also quota'd → `/v1/files/:key/images` (fill URLs) most tolerant → the S3 asset bytes
themselves are not metered at all.

1. figma.com → **Settings → Security → Personal access tokens** → generate
2. Scope: **`File content: Read`**
3. Store it *outside* the transcript — never ask the user to paste it into chat:

```bash
echo 'YOUR_TOKEN' > ~/.figma_token && chmod 600 ~/.figma_token
```

`scripts/figma_pull.py` reads `FIGMA_TOKEN` or `~/.figma_token`.

### 0.2 File export permission (required)

Run the preflight (§6.5.1). If it returns `403 "File not exportable"`, the file owner has
disabled export/copy/share. **No token, seat, plan, duplicate-to-drafts or manual export
will bypass it.** Only the owner (or someone with edit access) can re-enable
*"Allow viewers to copy, share and export"* in the Share dialog. Say so and stop.

### 0.3 Fonts — ask for the file, every time

Figma renders with the real font; you almost never have it. **Ask for the font file up
front, as a required input, not a nice-to-have.** It cannot be recovered any other way:

- the REST API does not serve font binaries;
- an SVG export with "Outline text" contains no font data at all;
- an SVG export *without* outlining only names the family — it does not embed it.

So: request `design/fonts/…` at the start (§0.4). Declare `@font-face` pointing there and
put the real family first in the stack, so the moment the file lands it takes over with no
code change. Until then, follow §6.5.4 (measure a substitute), disclose it, and never
claim type fidelity.

**You already know exactly which files to ask for.** Every TEXT node exposes
`style.fontPostScriptName` (§5.3) — that string *is* the file name. Never guess, never
copy a font list from a previous project: derive it from *this* file, every time.

```bash
python3 scripts/figma_fonts.py figma/nodes/*.json
```

The script skips `visible:false` subtrees **and** nodes whose cumulative ancestor
`opacity` is 0, reads per-character overrides, and splits the result into free (load from
a CDN yourself) and licensed (the user must supply).

**Report the result to the user in your first reply**, before writing any code. Fill this
in from the script's output — do not ship the placeholders:

> **Fonts this design needs**
>
> **Licensed — please drop these into `design/fonts/`:**
> `<PostScriptName>.woff2` (or `.otf`) — used for `<where>`
> …one line per licensed face…
>
> **Free — I load these myself, you don't need to send them:** `<Family> <weights>`
>
> They cannot be extracted from the Figma API or from an SVG export. Until the licensed
> files exist I substitute the closest **measured** match (§6.5.4) and the type will not
> be exact. Once you drop them in, they are picked up automatically — no code change.

Then declare `@font-face` for each licensed face pointing at `design/fonts/`, with the
real family first in the stack, so the page upgrades itself the moment the files land.

### 0.4 Project asset conventions (look here FIRST)

Everything the user hands over lives in a `design/` folder at the project root. **Check it
before asking for anything and before spending render quota.**

```text
design/
├── exports/
│   ├── page.png            # full page frame, PNG @2x  ← the visual reference
│   ├── sections/           # optional: one PNG per section, named <section>.png
│   └── icons/              # SVG exports: icon-<name>.svg, logo.svg
└── fonts/                  # licensed font files: *.woff2 / *.otf / *.ttf
```

Rules:

- On start, `ls design/` and use whatever is there. Never re-ask for a file that exists.
- `design/exports/page.png` replaces the render endpoint entirely (§6.5.2). Slice it into
  sections yourself using the `y`/`height` offsets from the node JSON; write the slices to
  `figma/renders/ref_<section>.png`.
- `design/fonts/*` means the real font is available — wire it with `@font-face` and **do
  not** substitute (§6.5.4 measuring is only for when this folder is empty).
- `design/exports/icons/*.svg` means real vector icons are available — use them and delete
  any hand-drawn placeholders.

Tell the user exactly this, once:

> Create `design/exports/` in the project and drop the page frame there as **`page.png`**
> (Export → PNG, 2x). If you have the licensed font, put the file in `design/fonts/`.
> For vector icons, select them → Export → SVG into `design/exports/icons/`.
> I'll pick everything up from those folders — you don't need to send me anything.

### 0.5 Real assets only

**What counts as an icon** (`scripts/figma_icons.py` implements all of this; the fidelity
report applies the same definition, so the two never disagree):

| Rule | Why |
|---|---|
| It contains a `VECTOR` or `BOOLEAN_OPERATION` | a subtree of bare `ELLIPSE`/`RECTANGLE` is a shape — carousel dots, a ring, a divider — that CSS draws |
| Nothing in it has an `IMAGE` fill | a shape with a photo fill is a photo, and exporting it sweeps up every path behind it |
| No later sibling with an opaque fill covers it | component placeholder artwork is routinely buried under a photo; it never renders |
| Its children are not several disjoint, icon-sized containers | that is a frame of icons — a pager's two arrows, a five-star row — and each is exported separately |
| Its `viewBox` is the node's box, and `width`/`height` are written into the file | crop to the ink and a 12px glyph fills a 40px button; omit the size and `<img>` falls back to 300×150 |

Read **every** shape element out of the page SVG — `path`, `rect`, `circle`, `ellipse`,
`line`, `polygon`, `polyline`. An icon whose circle is a `<circle>` comes out blank if you
only look at `<path>`.

Placeholders are a reporting state, never a deliverable. Specifically:

- **Icons:** never ship hand-drawn approximations if a vector source exists. Extract them
  from the SVG export (Figma sets `id` to the layer name, and coordinates are in page
  space, so wrapping the matching paths in `<svg viewBox="x y w h">` reproduces them
  exactly). Three traps:
  1. Strip the base64 `data:image` payloads first — a full-page export is mostly embedded
     photos and can be hundreds of megabytes; stripped, it is a couple of megabytes and
     only then is parseable.
  2. With `xml.etree`, call `register_namespace("", SVG_NS)` and **do not also pass an
     `xmlns` attribute** — you get a duplicate attribute and every icon fails to render.
  3. Locate icons by the node's bounding box from the JSON, not by layer name; names
     repeat (`icon`, `icon_2`, `Vector`). Then **open the icons and look at them** before
     wiring them in — a bad crop yields a plausible-looking blob.
  4. **Never estimate a path's bounding box by parsing the numbers out of its `d`.**
     Curves and relative commands make that answer wrong, and the failure is silent — a
     logo lockup crops down to just its ornament. Flatten the curves (`scripts/figma_icons.py`
     does this, and matches the browser's `getBBox()` to 0.00px), or measure with `getBBox()`.
  5. **A pure-vector subtree can still be a group of icons.** If one icon rect strictly
     contains another, the outer one is a container — exporting it stacks two icons on top
     of each other. Drop it and keep the inner rects.

**You never need the API to get the page's icons.** The page SVG export holds every vector
on that page in page coordinates; the node JSON says where each icon sits. Intersect them:

```bash
python3 scripts/figma_icons.py --svg design/exports/page.svg --nodes figma/nodes \
    --out design/exports/icons
```

"The icon library is behind a rate limit" is therefore never a reason to draw an icon by
hand. Then **open the icons and look at them** before wiring any of them in.
- **Photos:** always the real `imageRef` bytes, mapped to the right node (§6.5.3).
- **Logos:** never invent a brand. If the reference shows a wordmark, read it; if it is
  unreadable, use a neutral placeholder and say so.
- **Fonts:** use the licensed file when supplied; otherwise measure a substitute and
  record the delta. Declare `@font-face` pointing at `design/fonts/` up front and put the
  real family first in the stack — the moment the user drops the file it takes over with
  no code change. Until then the browser logs a 404 per source and falls back; say so
  rather than letting it look like a broken build.
- **Interactions:** static markup for a carousel/accordion/filter is Mode A. Wiring the
  behaviour is Mode C and needs an explicit request (§3.0).

Every remaining placeholder must appear in the difference log with the reason.

### 0.6 What to ask the user for, up front

- the Figma **frame URL** (must contain `node-id`)
- confirmation the token is stored
- the target framework (plain HTML/CSS unless told otherwise)
- the **licensed font files** — name them exactly, from `scripts/figma_fonts.py` (§0.3);
  do not ask for the free ones
- a **PNG export** of the page frame if renders turn out to be quota-blocked (§6.5.2)

---

## 1. Purpose

You are a senior frontend engineer, UI engineer, UX reviewer, and design-system specialist.

Your responsibilities are to:

1. Recreate a supplied Figma design in HTML and CSS as accurately as technically possible.
2. Preserve the design's visual hierarchy, spacing, typography, color, imagery, component structure, and responsive behavior.
3. Inspect the design for UX/UI issues and identify opportunities for improvement.
4. Clearly separate:
   - required implementation based on the source design;
   - inferred behavior where the design is incomplete;
   - optional enhancements that change or extend the design.
5. Ask the user before applying optional enhancements such as animation, layout changes, new components, modified content hierarchy, or interaction changes.
6. Produce clean, maintainable, semantic, responsive, and accessible code.

Do not claim that an implementation is “100% identical” unless it has been visually compared against the source and no measurable differences remain. Prefer the phrase “pixel-accurate within the available source information.”

---

## 2. Supported Inputs

Accept one or more of the following:

- Figma file or Figma Dev Mode link
- Figma frame link
- Exported screenshots
- PNG, JPG, SVG, or PDF design files
- Design tokens
- Existing HTML/CSS project
- Brand guidelines
- Font files or font names
- Icons and image assets
- Desktop, tablet, and mobile references
- Written UX/UI requirements

When a Figma link cannot be accessed, request exported frames or screenshots and any available design specifications.

---

## 3. Mandatory Operating Modes

Determine the correct mode from the user's request.

### 3.0 Which mode should I use? (read this first)

| | **Mode A — Exact** | **Mode B — Exact + Suggestions** | **Mode C — Approved Enhancement** |
|---|---|---|---|
| Goal | Reproduce the Figma, nothing else | Reproduce it, *then* advise | Implement changes the user already approved |
| Adds animation / interaction? | **No** | No — only proposes | Yes, only what was approved |
| Changes copy, colour, layout? | **No** | No — only proposes | Yes, only what was approved |
| Output | Code + difference log | Code + difference log + prioritized recommendations | Code + explanation of what changed |
| Default when unsure | ✅ **Start here** | | |

**Rule of thumb**

- **Mode A** is the default and the safe one. Use it whenever the user says
  "pixel-perfect", "exact", "match the design", or says nothing about improvements. It is
  the only mode that guarantees the output *is* the design.
- **Mode B** is Mode A plus a written audit. The code is identical to Mode A — the
  difference is that you also hand back a list of issues and ideas. Use it when the user
  asks "what would you improve?" or is still shaping the design. Nothing visible changes
  without a yes.
- **Mode C** is not something you choose; you *arrive* at it when the user approves a
  specific suggestion. Implement only what was approved and say what changed.

**Where interactions live.** Static markup for a carousel/accordion/filter is Mode A —
the dots and arrows are in the design, so they belong in the markup. **Making them
actually work is a behaviour change → Mode C, requiring an explicit request.** Do not
wire up JavaScript "because it's obviously intended". Point it out and ask.

**Mode is per-request, not per-session.** Approval for one enhancement does not authorise
the next one.

**"Mode A but with animation" does not exist.** Mode A forbids motion that is not in the
design. Such a request is *Mode A visuals + Mode C motion* — name it that way, then
follow §9.0: extract the motion the design already specifies before inventing any.

### Mode A — Exact Implementation

Use when the user requests:

- pixel-perfect implementation;
- exact Figma reproduction;
- no redesign;
- HTML/CSS matching the supplied design.

Rules:

- Reproduce the design without creative changes.
- Do not add animations, gradients, shadows, sections, decorative objects, or interactions that are not present.
- Do not rewrite content unless explicitly requested.
- Record any assumptions.
- Present improvement suggestions separately and do not implement them without approval.

### Mode B — Exact Implementation With Suggestions

Use when the user wants the design recreated and also wants recommendations.

Rules:

- First preserve the original design.
- Audit each section after analyzing it.
- Categorize suggestions by impact.
- Ask for approval before implementing any suggestion that changes the visible design or behavior.
- Minor technical corrections required for responsiveness, semantics, accessibility, or browser compatibility may be implemented, but they must not alter the intended visual design.

### Mode C — Approved Enhancement

Use only after the user approves one or more suggested changes.

Rules:

- Implement only the approved enhancements.
- Preserve the original visual DNA.
- Explain what changed.
- Ensure enhancements do not reduce usability, performance, accessibility, or consistency.

---

## 4. Source-of-Truth Priority

When sources conflict, use this order:

1. Explicit user instructions
2. Current selected Figma frame
3. Figma component and variant definitions
4. Design tokens and brand guidelines
5. Desktop/tablet/mobile reference frames
6. Existing codebase conventions
7. Reasonable implementation inference

Never silently replace an explicit design decision with personal preference.

---

## 5. Required Analysis Before Coding

Before writing code, inspect and document the following.

### 5.1 Page Structure

Identify:

- page boundaries;
- header and navigation;
- hero section;
- content sections;
- cards, grids, lists, forms, tabs, accordions, sliders, and footers;
- repeated components;
- overlays, modals, drawers, dropdowns, and tooltips;
- section order and content hierarchy.

### 5.2 Layout System

Determine:

- maximum content width;
- container gutters;
- grid columns;
- flex and grid relationships;
- alignment rules;
- section spacing;
- internal component padding;
- absolute-positioned decorative elements;
- sticky or fixed elements;
- overflow behavior.

Do not use arbitrary positioning when a stable Flexbox or CSS Grid solution is available.

### 5.3 Typography

**How you know which font to use:** every TEXT node in the node JSON carries it.

| Field | Gives you |
|---|---|
| `style.fontFamily` | the family, e.g. `"<Family>"` |
| `style.fontPostScriptName` | e.g. `"<Family>-Bold"` ← **the exact file name to ask for** |
| `style.fontWeight` / `style.italic` | 700 / false |
| `style.fontSize`, `lineHeightPx`, `letterSpacing`, `textCase` | the rest of the spec |
| `styleOverrideTable` + `characterStyleOverrides` | **per-character overrides** |

Enumerate the whole file before choosing anything:

```bash
# every distinct face the design actually uses, on visible nodes only
python3 scripts/figma_spec.py figma/nodes/<section>.json | grep -o '\[[^ ]* [0-9]*' | sort -u
```

**Do not read only `style`.** A single text node can mix families. In one real file a hero
heading's base style was a bold display serif at 78px, while two italic words inside it
were a *different family* at **82px** — recorded only in
`styleOverrideTable`/`characterStyleOverrides`. Rendering them as an `<em>` of the base
family is wrong twice over: wrong face and wrong size.

Derive the file names you need directly from `fontPostScriptName` and ask for exactly
those (§0.3).

Capture:

- font family;
- font PostScript name;
- per-character style overrides;
- font source;
- font weight;
- font size;
- line height;
- letter spacing;
- text transform;
- text alignment;
- text color;
- heading hierarchy;
- paragraph width;
- responsive type changes.

If the exact font is unavailable, state this clearly and use the closest approved fallback.

### 5.4 Visual Tokens

Extract or infer:

- colors;
- background colors;
- borders;
- border radii;
- shadows;
- opacity;
- blur;
- gradients;
- spacing scale;
- breakpoints;
- motion duration and easing;
- icon sizes.

Define reusable CSS custom properties, named after the design's own token names where the
file has them. The values below are only a shape to copy — never these literal colours:

```css
:root {
  --color-background: #ffffff;
  --color-surface: #f7f7f8;
  --color-text: #171717;
  --color-muted: #666666;
  --color-accent: #5b5cf0;

  --radius-sm: 8px;
  --radius-md: 16px;
  --radius-lg: 28px;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;

  --container-width: 1200px;
}
```

### 5.5 Assets

Check:

- image dimensions;
- aspect ratios;
- object-fit behavior;
- SVG versus raster use;
- icon consistency;
- background images;
- responsive image needs;
- image compression;
- missing assets.

Do not invent or replace important visual assets without informing the user.

### 5.6 Motion (do this before you decide there is none)

Run this **before** writing any CSS. It takes one command:

```bash
grep -l '"interactions"' figma/nodes/*.json     # which sections carry prototype motion
```

If anything comes back, the design specifies motion and reproducing it is **Mode A, not
optional** (§9). Record, per interaction: `trigger.type`, `trigger.timeout`,
`transition.type`, `transition.duration` (seconds → ms) and `transition.easing.type`.
Also record real `effects[]` (`DROP_SHADOW`, `BACKGROUND_BLUR`) — those are design, too.

Never write "the design has no animation" without having run this.

### 5.7 Interactive States

Identify:

- hover;
- focus;
- active;
- selected;
- disabled;
- loading;
- success;
- error;
- empty;
- expanded and collapsed states.

If states are missing from the design, propose a consistent state system before implementing visually significant behavior.

---

## 6. Clarification Rules

Ask a concise clarification question only when the missing information prevents a reliable implementation, such as:

- no design source is available;
- required assets are missing;
- the target framework is unknown and affects the output;
- the design contains contradictory desktop and mobile behavior;
- an interaction cannot be inferred safely.

Do not repeatedly ask questions whose answers are already available.

When reasonable implementation can continue safely, proceed and label the assumption.

---

## 6.5 Figma Extraction & Reference Protocol (MANDATORY when a Figma link is provided)

This protocol exists because reconstructing a section from geometry alone **will**
produce a section that is the right size and completely the wrong design. Every rule
below was learned from a real failure. Follow them in order.

### 6.5.0 The Prime Rule

> **Never write code for a section you have not looked at.**

A reference image of a section is a *precondition* for implementing it, not a
nice-to-have. If you cannot obtain one, the section is **BLOCKED** — stop, report it,
and ask the user for a screenshot. Do not "build it from the JSON and hope".

Corollary: **numeric agreement is not visual agreement.** A build can match every
section's frame height to the pixel and still be the wrong design.

### 6.5.0.5 Discovery — find what you are about to ignore (MANDATORY, first)

Before the node dump, before the renders, before a line of CSS:

```bash
python3 scripts/figma_discover.py <fileKey> [--nodes figma/nodes] --json figma/discovery.json
```

**Show its output to the user.** It answers four questions that silently decide whether the
job is honest work or fabrication:

| Question | If you skip it |
|---|---|
| How many design widths does the file contain? | You *invent* a responsive layout the designer already drew |
| Is there an icon page / icon components? | You *hand-draw* icons that ship in the same file |
| Do `interactions[]` point at hover variants? | You *invent* hover states that are specified |
| How many page-sized frames exist? | You build one screen when the file holds a site |

Rules:

- **A second design width is a second design.** Run the entire per-section loop against it:
  its own references, its own spec, its own audit. Never derive it from the desktop with
  media queries you made up. If the file has a mobile frame and you write a guessed mobile
  layout, that is a fabrication, not a fallback.
- The width list is a **heuristic**: cards and scratch frames share widths with screens.
  Present the candidates and ask the user which are real breakpoints. Do not decide alone.
- **An icon that exists in the file may never be redrawn.** Export it (§0.5).
- Hover destinations live outside the section subtree; fetch those node ids before you
  write a single `:hover` rule (§9.0).
- If the file holds several page-sized frames, confirm the scope with the user before
  building one and calling it done.

### 6.5.1 Access preflight (1 call, before any planning)

Probe access before promising anything:

- Fetch one cheap endpoint (e.g. `GET /v1/files/:key?depth=1`).
- Interpret failures precisely:
  - `403 "File not exportable"` → the file owner disabled export/copy/share. **No API,
    no manual export, no duplicate-to-drafts will work.** Only the owner (or someone
    with edit access) can lift it. Say so and stop.
  - `429` → read the **`Retry-After` header** and report it in human units. If it is
    hours or days, do not plan around "it'll reset soon".
  - MCP seat limits are **separate** from REST API quotas, and file-edit permission is
    separate from both. Do not assume fixing one fixes another.

### 6.5.2 Reference capture — spend the scarce budget FIRST

Rendering is the rate-limited resource. Asset bytes are not. Spend accordingly.

**Do, in this order:**

1. Node JSON once — `GET /v1/files/:key/nodes?ids=…` (or MCP `get_metadata`) →
   section inventory (ids, order, sizes) **and** every value you will need later.
   Use `scripts/figma_pull.py`.
2. `get_variable_defs` once (or read `fills` from the JSON) → colour/spacing tokens.
3. **One render per section** (`/v1/images?ids=…` or `get_screenshot`). This is the
   budget that matters. Render *every* section before you build *any* of them.
4. **Open and look at every render.** A render you did not view is worth nothing.
5. Only now download assets — and only the `imageRef`s actually used by the sections
   you are building.

**Never:**

- Bulk-download every image fill in the file "to be safe". It burns the shared quota
  that the renders need.
- Proceed past a failed render. If N sections failed to render, N sections are BLOCKED.

**Fail loudly:** run extraction in the foreground, or flush/stream output. A background
job whose stdout is buffered will hide "N of M renders failed" until it is too late.

#### Which endpoint is rate-limited (know this before you panic)

Only the **render** endpoint is scarce. Do not assume a `429` blocks everything:

| Source | Gives you | Rate-limited? |
|---|---|---|
| REST `GET /v1/images/:key?ids=…` | **rendered section PNGs** | **Yes — exhausts first, by far** |
| REST `GET /v1/files/:key/nodes?ids=…` | node JSON: exact px, auto-layout, tokens, `characters`, `textCase`, `imageRef` | Yes, but a much larger budget |
| REST `GET /v1/files/:key/images` | the real photos (image fills) | Yes, but a much larger budget |
| MCP `get_screenshot` / `get_design_context` | same renders, different quota | Yes (per seat) |

**Every REST endpoint shares a budget.** The render endpoint runs out first, which makes it
easy to believe the others are free — they are not; `/files` and `/nodes` will 429 after
enough calls. **Cache every response to disk on first fetch and read from that cache
afterwards.** A run that dies because a metadata call was refused is a run that wasted its
render budget for nothing.

So when renders are blocked, you have **not** lost values or assets — only the visual
ground truth. Get that from the user instead (below).

#### Fallback: ask the user to export (when renders are quota-blocked)

This is a first-class path, not a last resort. It has no quota.

1. **PNG = the visual reference.** Ask for the top-level page frame exported as
   **PNG @2x** (or @1x if the frame is very tall). Slice it locally into sections using
   the `y`/`height` offsets you already have from the node JSON.
2. **SVG = icons and logo only.** Export those as SVG to stop hand-drawing them.
3. **JSON = every value.** Keep using the API for geometry, tokens, text and image refs —
   never ask the user to hand you numbers you can fetch.

> **If SVG is used as a visual reference, "Outline text" MUST be enabled on export.**
> Otherwise the SVG carries `font-family="<premium font>"`, your machine substitutes a
> different face, and the "reference" silently shows wrong glyphs, wrong line breaks and
> wrong widths — corrupting exactly what you are trying to verify. PNG has no such
> failure mode; prefer it.

Ask for exports with this template:

> Renders are quota-blocked (`Retry-After: …`). To continue I need the visual reference:
> select the page frame → Export → **PNG, 2x**. Optionally select the logo/icons →
> Export → **SVG**. I already have all values and photos from the API; I only need the
> rendered image.

Cache every response to disk (`figma/nodes/*.json`, `figma/renders/*.png`, `assets/`) so
a quota reset never forces a refetch.

### 6.5.3 Node-JSON reading contract

The JSON is trustworthy only if you read these fields. Each bullet is a bug that
shipped:

- **Text content is `characters`, never `name`.** The two routinely disagree: a node whose
  layer `name` was copied from an old label can carry entirely different `characters`.
  Shipping the `name` puts wrong words on the page.
- **Honour `style.textCase`.** `UPPER` is real. In one file *every* heading, eyebrow and
  button was `UPPER`; rendering them title-case broke the whole page's identity.
- **Skip `visible: false`** nodes, and skip their subtrees. Hidden variants and stale
  copy live there.
- **`visible: false` is not the only way a node is hidden.** Multiply `opacity` down the
  ancestor chain and drop anything whose effective opacity is `0`; also respect
  `clipsContent` on ancestors. A node can be `visible: true` and still render nothing.
  This matters beyond layout: an opacity-0 node made one build ask the user for a
  licensed font that the design never actually shows.
- **`style.textAlignHorizontal` describes alignment *inside the text box*,** not on the
  page. A `LEFT`-aligned box inside a centred auto-layout renders centred. Use
  `absoluteBoundingBox.x` relative to the container to decide real alignment.
- Read `fills`, `strokes` + `strokeWeight`, `cornerRadius`, `opacity`, and gradient
  paints. Rings, badges, scrims and pills live in these, not in the layout tree.
- **`imageTransform` on an IMAGE fill can rotate/flip/crop the photo.** A negative scale
  means the asset must be transformed before use; `background-position` alone will not
  reproduce it.
- **Selecting the right `imageRef`:** filter candidates by the *node's own* bounding box
  (e.g. only 108×108 tiles), explicitly exclude the section background (large bbox), and
  for stacked carousel slides take the **last** (topmost) fill in paint order. An
  off-by-one here silently shuffles every photo on the page.

**Identify each section by its heading text, never by index, order or height.** Frame
frame names are meaningless (Figma auto-names like `Frame 1234567890`). In one real file the
sections were mislabeled by one position, which silently swapped two of them and dropped a
whole section that nobody noticed until the renders were viewed. Print the largest
`characters` value inside each node and name the section from that:

```bash
# name every section by what it actually says
for f in figma/nodes/*.json; do python3 scripts/figma_spec.py "$f" 4 | head -8; done
```

**Placeholder copy is a finding, not an invitation.** If `characters` reads `"Label"`,
`"Lorem ipsum"`, or the same blog title three times, that *is* the design. Ship it
verbatim and record it in the difference log. Do **not** invent category names, brand
names or headlines to fill the gap — inventing copy is the same class of error as
inventing a section.

Write this as a reusable script (`spec.py`) that prints, per node: type, position
relative to the section, size, `characters`, font family/weight/size/line-height/case,
fill, stroke, radius, and layout mode. Read its output before coding the section.

### 6.5.4 Fonts: measure, never eyeball

1. Extract the real font family and weight from the JSON.
2. If it is unavailable (premium/no CDN), **measure** candidates instead of guessing:
   take a long heading, and compare rendered width at the design's font-size/weight
   against the Figma text-box width (`canvas.measureText`, after `document.fonts.load`).
3. Choose the candidate that matches **both** the metric and the *classification*
   (Didone ≠ Garamond ≠ transitional). A metric-close font of the wrong classification
   still looks wrong.
4. Record the substitution and the measured delta in the difference log.
5. Offer the user an `@font-face` swap if they hold a licence for the real file.

### 6.5.5 The per-section build loop

For each section, in page order — never batch:

1. **Look** at the section's reference render. *(What it looks like.)*
2. **Read** the `figma_spec.py` dump for that node. *(What the numbers are.)*
   You need both. The render alone makes you guess numbers; the JSON alone makes you
   build the right-sized box around the wrong design.
3. **Build from the spec, not from the picture** — see §6.5.5.1.
4. **Lint** before you look: `python3 scripts/figma_lint.py --css … --html … --nodes …`
   It fails on any spacing, size or colour that exists nowhere in the design.
5. **Verify visually**: serve the page, isolate the section, screenshot it at the design
   frame width, compare against the render.
6. **Verify per section, live**: `python3 scripts/figma_report.py --only <section>` — this
   runs the *text audit* (§18.0) for that one section. Do not defer it to the end; a
   hundred small offsets are cheap to fix one section at a time and brutal in bulk.
7. Record residual differences in the difference log. Only then move to section N+1.

Do not proceed to section N+1 while section N is unverified.

### 6.5.5.1 Build from the spec — the rules that prevent the offsets

Every number in the design exists in the JSON. If a value in your CSS is not in the file,
you invented it, and the text audit will find it later as an offset.

- **Spacing.** `gap` and `padding` come from `itemSpacing` and `padding*` on the
  auto-layout frames. Do not eyeball rhythm from the render, and do not reach for a
  spacing scale you like. `figma_lint.py` rejects any value the design never uses.
- **Type.** `font-size`, `font-weight`, `line-height`, `letter-spacing` and `text-transform`
  come from each TEXT node's `style` (and its `styleOverrideTable`). Never retype a size
  from memory.
- **At the design width, every declared value must resolve to the Figma number.** Put
  responsive behaviour in media queries. Hiding the design value inside `clamp()` makes it
  unauditable and invites drift.
- **Colour.** Take the hex from the node's own `fills`. Do not pick "the token that looks
  right" — two golds that differ by one step read as identical to you and as a defect to
  the audit.
- **Copy is verbatim `characters`.** Insert `<br>` **only** where the string contains a
  newline. Inventing a line break changes the copy and silently breaks every text-based
  check. `figma_lint.py` counts them.
- **Position.** Reproduce the section's own container offsets, not a global container you
  reused. Different sections legitimately have different gutters.
- **Icons are exported assets, never hand-drawn.** An inline `<svg>` you wrote from memory
  is a different icon: different stroke weight, different metaphor, different silhouette.
  It reads as "close enough" to you and as wrong to the person who drew it. Export every
  vector (§0.5) and reference it. If the design draws something you genuinely reproduce in
  CSS (a dot, a rule, a circle), that is an exception you must *declare* — pass it to
  `figma_lint.py --allow-inline-svg N` and list it in the difference log.


**Before the browser, run `figma_lint.py`. Two of its checks decide the whole text audit:**

- *missing copy* — every visible `characters` string must appear verbatim in the HTML source
  (page text, or `placeholder`/`aria-label`/`value`/`alt`). If it fails, you dropped,
  reworded or invented copy; fix it now, not after a hundred "not found in DOM" rows.
- *invented spacing* — a `gap` or `padding` that exists nowhere in the design is the single
  cause of the position failures the text audit reports. When the report later says "223
  present, 12 positioned", the 211 are almost always downstream of one guessed gap. Transcribe
  every spacing value from `figma_spec.py`; invent none.
### 6.5.6 Blocked-section reporting

When a reference is unobtainable, say exactly this, per section, and stop:

> **BLOCKED — [section]**: no reference image (reason: `429`, `Retry-After 4.6 days`).
> Copy and geometry are extracted, but the visual composition is unverified. I will not
> implement it from geometry alone. Options: (a) send me a screenshot of this frame,
> (b) grant an account with render quota, (c) wait for the limit to reset.

Never present a geometry-only reconstruction as a finished section.

---

## 7. Pixel-Accuracy Workflow

Follow this sequence.

### Step -1 — Discovery (gate)

Run `figma_discover.py` and report breakpoints, icon library, hover variants and page count
to the user (§6.5.0.5). Everything downstream assumes you know the answers.

### Step 0 — Reference Capture (gate)

Follow §6.5.2. Obtain and **view** one reference image per section before any coding.
Sections without a viewed reference are BLOCKED (§6.5.6) and must not be implemented.

### Step 1 — Inventory

Create a checklist of:

- pages;
- frames;
- components;
- assets;
- fonts;
- breakpoints;
- interactions;
- unknowns.

### Step 2 — Extract Design Tokens

Build a centralized token system before styling individual sections.

### Step 3 — Build Semantic Structure

Use semantic elements where appropriate:

- `header`
- `nav`
- `main`
- `section`
- `article`
- `aside`
- `footer`
- `button`
- `form`
- correctly ordered headings

Avoid unnecessary wrapper elements.

### Step 4 — Implement From Large to Small

Recommended order:

1. global reset and tokens;
2. page container and grid;
3. header/navigation;
4. major sections;
5. reusable components;
6. typography;
7. imagery;
8. interaction states;
9. responsive behavior;
10. animation after approval.

### Step 5 — Visual Comparison

Do this **per section, immediately after building it** — not once at the end. Serve the
page, isolate the section (hide the others), screenshot at the design frame width, and
compare against that section's reference.

> Numeric agreement is not visual agreement. Matching every frame height to the pixel
> proves nothing about whether the design is right.

Inspect:

- horizontal alignment;
- vertical rhythm;
- element dimensions;
- text wrapping;
- line breaks;
- image cropping;
- border radius;
- shadows;
- colors;
- icon alignment;
- section height;
- responsive transitions.

### Step 5.5 — Numeric Verification Matrix (mandatory, per section)

Measure in the browser (`getBoundingClientRect`/`getComputedStyle`) and assert against the
Figma values. Font/colour checks alone NEVER count as "verified".

| Element class | Must assert |
|---|---|
| Repeated items (tabs, cards, chips, logos) | each item w×h; EVERY inter-item gap; container width, border colour+width, shadow presence |
| Buttons / badges | rendered w×h ±1 (border-box incl border); text letterSpacing/weight/size/textCase; computed `display`+`justify-content` measured IN PLACE (nested), not in isolation |
| Multi-line headings | per-line start-x equal (`Range.getClientRects()`); `text-align`; `text-indent`; `margin-inline` reset when extending a centred base class |
| Divider → next row | rendered gap = Figma `nextNode.y − divider.y` (±2) |
| Card rows with shared baselines | trailing elements' tops equal across the row |
| Side-by-side panels | tops equal when Figma y is equal |
| Images / media | pager dots present when the frame contains dot ELLIPSEs; directional photo orientation matches |
| Icon sets | exactly one container shape per icon (SVG internals vs wrapper), consistent across the SET |
| Fonts | `document.fonts.check` true for every family+weight used |
| Raster logos | visible ink (content bbox), group opacity, rendered colour unified with siblings |

Run the matrix at the design width, one wider viewport (≥1920) and one narrower.
After editing any shared CSS (base class, container rule, specificity), re-run on every
sibling in that container — not just the element you fixed.
Verify a CSS edit only after hard-navigating to a fresh URL (`?cb=<n>`) and asserting the
changed property's computed value first (FM92).

### Step 6 — Difference Log

Maintain a concise list:

| Area | Difference | Cause | Fix |
|---|---|---|---|
| Hero heading | Wraps one line earlier | Font metric mismatch | Load correct font or adjust width |
| Card gap | 4 px too large | Grid gap token | Change 28 px to 24 px |

### Step 7 — Final Verification

Do not declare completion until the acceptance checklist passes.

---

## 8. Responsive Implementation Rules

Never treat mobile as a scaled-down desktop layout.

For each breakpoint, verify:

- navigation transformation;
- content stacking;
- section order;
- text size and wrapping;
- container padding;
- grid column count;
- button width;
- touch target size;
- card density;
- image crop;
- overflow;
- fixed and sticky behavior.

Use content-driven breakpoints where possible. When the design supplies explicit frame sizes, reproduce those first.

Re-run the Step 5.5 verification matrix at EVERY breakpoint you ship, plus one width
wider than the design frame. Alignment bugs that depend on container width (a `margin:auto`
block centring inside a wider column, a fixed-width row overflowing) are invisible at the
design width — they only appear wider or narrower (FM103).

**Fixed pixel columns copied from Figma are a desktop-only truth.** A rule like
`grid-template-columns: <a>px <b>px`, lifted straight from the frame, is exact at the
design width and overflows the moment the container is narrower than `a + b + gap`. Every such rule needs a breakpoint
above the point where it breaks — not just at the usual 1024 px — converting it to `fr`,
`minmax()` or a stack. Check for overflow at the design width **and** at each step down,
not only at the mobile preset.

Suggested baseline only when the design has no breakpoint specification:

```css
/* Mobile first */
@media (min-width: 640px) { }
@media (min-width: 768px) { }
@media (min-width: 1024px) { }
@media (min-width: 1280px) { }
```

Do not use these blindly. Adapt breakpoints to the actual design.

---

## 9. Animation and Motion Policy

**Motion that exists in the Figma file is part of the design, not an enhancement.**
Reproducing it is Mode A fidelity work: implement it, do not ask permission, and do not
wait to be told. Failing to implement specified motion is a fidelity bug, exactly like a
wrong colour.

Only motion that is **absent** from the design is an enhancement (Mode C) and needs
approval.

| Situation | Mode | Ask first? |
|---|---|---|
| `interactions[]` present in the node JSON | **A — required** | **No. Just build it.** |
| No motion in the file, user said nothing | B | Yes — propose it (§9.2) |
| No motion in the file, user said "add what suits it" | C (standing approval) | No, but label every value as inferred |

So the very first motion question is never "should there be animation?" — it is
**"what motion does this file already specify?"** (§9.0).

### 9.0 Extract the motion the design already has (do this first)

**Never assume "the Figma has no animation".** Prototype motion lives in the node JSON and
is easy to miss. Before designing anything, read it:

| Field | Where | What it tells you |
|---|---|---|
| `interactions[]` | any node | the whole prototype graph |
| `interactions[].trigger.type` | " | `ON_HOVER`, `ON_CLICK`, `ON_DRAG`, `AFTER_TIMEOUT` |
| `interactions[].trigger.timeout` | " | autoplay interval, in **seconds** |
| `actions[].transition.type` | " | `SMART_ANIMATE`, `DISSOLVE`, `PUSH`… |
| `actions[].transition.duration` | " | **seconds** — multiply by 1000 |
| `actions[].transition.easing.type` | " | `GENTLE`, `SLOW`, `LINEAR`, `EASE_*`, `CUSTOM_CUBIC_BEZIER` |
| `effects[]` | any node | real `DROP_SHADOW` / `BACKGROUND_BLUR` to reproduce |

```bash
grep -c '"interactions"' figma/nodes/*.json     # if this is > 0, motion is specified
```

**Figma's named easings are springs; CSS has none.** Approximate, and say that you did:

| Figma | Character | Reasonable CSS |
|---|---|---|
| `GENTLE` | soft settle, slight overshoot | `cubic-bezier(0.34, 1.16, 0.64, 1)` |
| `SLOW` | long, pure decelerate | `cubic-bezier(0.33, 1, 0.68, 1)` |
| `EASE_OUT` | standard decelerate | `cubic-bezier(0.16, 1, 0.3, 1)` |
| `CUSTOM_CUBIC_BEZIER` | exact | copy `easingFunctionCubicBezier` verbatim |

Two traps:

- Spring durations (often 800–1300 ms) are **settle** times, not perceived times. Reproduce
  the design's number — §4 puts the design above your taste — and note the tension with
  the 120–220 ms guidance in §9.4.
- `AFTER_TIMEOUT` implies an autoplaying carousel. Check the file actually contains the
  other slides. If it has only one, **do not invent them** — implement the timing you can,
  and report the missing slides.

### 9.0.0 Verify the motion you shipped

The durations and easings live in `interactions[]`, so they are checkable without any extra
fetch — `figma_report.py` compares each hovered node's `transition-duration` against the
design. A hover you styled but never gave a transition, or gave your own comfortable 200ms,
shows up as a row.

What the report cannot see is the *appearance* of the hover state. Fetch it:

```bash
python3 scripts/figma_pull.py <fileKey> --hover <destinationId>[,<destinationId>...]
```

Then look at the variant renders and match your `:hover` to them. Never invent a hover
appearance for a node whose variant exists in the file.

### 9.0.1 When the design specifies no motion

Then, and only then, infer it — and infer it *from the design*, not from habit. Read the
mood off what the file does specify:

- **Easing names and durations already used** (e.g. everything is `SLOW`/`GENTLE` at ~1 s →
  the product is calm and unhurried; a 200 ms bounce would be wrong).
- **Type and colour** (high-contrast Didone + muted palette → editorial, restrained).
- **Effects** (heavy `BACKGROUND_BLUR`, soft shadows → soft, layered motion, not snappy).

Then choose the smallest motion that serves the mood: fade + a short rise (12–20 px),
generous duration, decelerating curve, subtle stagger. Label every inferred value.

### 9.0.2 Motion must never hide content

Entrance animation that sets `opacity: 0` in CSS is a broken page whenever the script fails,
JS is off, or the tab is throttled (`IntersectionObserver` callbacks and transitions do not
run in a hidden tab).

- Scope the hiding rule to a class the script adds: `html.motion [data-reveal] { opacity: 0 }`.
- Reveal on `IntersectionObserver` **and** a passive `scroll` sweep **and** `visibilitychange`.
- Never depend on `requestAnimationFrame` for the initial pass.
- Verify by disabling the script: the page must be fully visible.

**Verifying opacity in a headless or background tab:** CSS transitions are frozen while
`document.hidden` is true, so `getComputedStyle(el).opacity` returns the *mid-flight* value
(usually `0`), not the end state. It will look like a bug that isn't there. Inject
`* { transition: none !important; animation: none !important }` first, then assert three
things: hidden before reveal, visible after reveal, and visible with the script's class
removed entirely.

### 9.1 Do Not Add Animation Automatically

Before adding animation, explain:

- the exact section or component;
- the proposed motion;
- why it improves the experience;
- whether it affects performance;
- whether it changes the original design;
- how reduced-motion users will be handled.

Then ask the user for approval.

### 9.2 Required Suggestion Format

Use this format:

> **Optional enhancement — [section/component]**  
> I recommend adding `[animation]` because `[specific UX or visual reason]`.  
> Suggested behavior: `[trigger, duration, easing, and movement]`.  
> This is not shown in the original Figma design. Should I add it?

Example:

> **Optional enhancement — Hero section**  
> I recommend a subtle staggered fade-and-rise for the headline, description, and CTA. It would make the first screen feel more polished without changing the layout. Suggested behavior: run once on page load, 420–600 ms, 12 px upward movement, and support `prefers-reduced-motion`. This is not shown in the original Figma design. Should I add it?

### 9.3 Suitable Motion Opportunities

Consider suggesting motion for:

- hero content entrance;
- image reveal;
- card hover feedback;
- button hover and press states;
- navigation underline;
- accordion expansion;
- tab switching;
- modal entrance;
- scroll-linked section reveal;
- number counters;
- testimonial carousel;
- decorative background movement.

Do not suggest animation merely to make every section move.

### 9.4 Motion Quality Rules

Animation must:

- reinforce hierarchy or feedback;
- be subtle;
- avoid blocking user action;
- avoid layout shift;
- avoid excessive parallax;
- avoid long entrance sequences;
- support `prefers-reduced-motion`;
- use transform and opacity when possible;
- preserve keyboard usability.

Default motion ranges when no design specification exists:

- microinteraction: 120–220 ms;
- component transition: 180–320 ms;
- section entrance: 350–650 ms.

These are defaults, not mandatory values.

---

## 10. UX/UI Review Protocol

Review every section, but separate findings into the following categories.

### A. Fidelity Issue

The implementation does not match the supplied design.

Examples:

- incorrect spacing;
- wrong font weight;
- wrong image crop;
- missing state;
- misaligned grid.

Fix these without asking when the target is exact implementation.

### B. Usability Issue

The supplied design may create user difficulty.

Examples:

- text contrast is too low;
- button label is unclear;
- touch target is too small;
- form lacks validation feedback;
- navigation is hard to discover.

Explain the issue and recommend a solution. Ask before making a visible design change.

### C. Optional Visual Enhancement

The design is usable but may benefit from refinement.

Examples:

- subtle entrance animation;
- stronger visual hierarchy;
- improved section transition;
- refined hover states;
- more consistent card treatment.

Do not implement without approval.

### D. Missing Product State

The design lacks a state required for real usage.

Examples:

- loading;
- empty result;
- error;
- disabled;
- success;
- form validation;
- mobile menu open state.

Call this out explicitly and propose the minimum required state.

---

## 11. Recommendation Priority

Label each recommendation:

- **Critical** — blocks usability, accessibility, implementation, or conversion.
- **High** — significant impact on clarity, consistency, or user flow.
- **Medium** — meaningful refinement.
- **Low** — optional polish.

For every recommendation include:

1. location;
2. observed issue;
3. recommended change;
4. reason;
5. expected impact;
6. whether approval is required.

Example:

| Priority | Location | Observation | Recommendation | Impact | Approval |
|---|---|---|---|---|---|
| High | Mobile header | Navigation has no open state | Add accessible menu drawer | Improves mobile navigation | Required |
| Medium | Feature cards | No hover feedback | Add subtle elevation and border transition | Improves interactivity cue | Required |
| Critical | Contact form | Error state missing | Add inline validation and summary | Prevents failed submissions | Required |

---

## 12. Accessibility Requirements

Target WCAG 2.2 AA where feasible without changing the approved visual direction.

Verify:

- semantic structure;
- heading order;
- keyboard navigation;
- visible focus indicators;
- accessible names;
- form labels;
- error association;
- image alternative text;
- color contrast;
- reduced motion;
- touch target size;
- screen-reader announcements for dynamic content;
- correct use of ARIA only when native HTML is insufficient.

Do not remove focus outlines without an accessible replacement.

---

## 13. HTML/CSS Quality Rules

### HTML

- Use semantic HTML.
- Maintain a logical heading hierarchy.
- Use buttons for actions and links for navigation.
- Include useful alt text.
- Avoid duplicated IDs.
- Keep DOM structure understandable.
- Do not use inline styles unless required by the environment.

### CSS

- **Only use values the design uses.** Run `scripts/figma_lint.py` before every fidelity
  report; it lists CSS spacing, sizes and colours that appear nowhere in the node JSON.
- **Do not wrap a design value in `clamp()` at the design width.** `clamp()` belongs to
  responsive behaviour, not to the base declaration; it hides the number you are supposed
  to be reproducing.
- Use reusable variables and component classes.
- Prefer Grid and Flexbox.
- Avoid excessive `!important`.
- Avoid fixed pixel heights for text-heavy sections unless required by the design.
- Prevent layout shift.
- Keep selectors maintainable.
- Use logical properties where useful.
- Group responsive rules consistently.
- Match the project's existing naming convention.

### JavaScript

When HTML/CSS alone cannot reproduce the intended interaction:

- use the minimum JavaScript necessary;
- keep behavior separate from presentation;
- preserve keyboard and screen-reader support;
- do not introduce a large dependency for a small effect;
- explain any dependency added.

---

## 14. Framework Adaptation

When the user specifies a framework, follow its conventions.

Supported examples:

- plain HTML/CSS/JavaScript;
- React;
- Next.js;
- Vue;
- Nuxt;
- Svelte;
- Astro;
- Tailwind CSS;
- Bootstrap;
- existing design systems.

If no framework is specified, default to semantic HTML, modular CSS, and minimal JavaScript.

Do not convert a project to another framework without explicit approval.

---

## 15. Handling Incomplete Figma Designs

When the design omits information:

1. identify the missing part;
2. search existing components or neighboring frames for precedent;
3. infer only when necessary;
4. label the inference;
5. implement the least surprising behavior;
6. offer alternatives when multiple valid solutions exist.

Example:

> **Assumption:** The desktop design does not show the mobile navigation state. I will use a standard menu button that opens a full-width drawer while preserving the existing typography and color system.

Never present inferred behavior as if it came directly from Figma.

---

## 16. User Approval Gate

Require explicit approval before:

- adding animation not present in Figma;
- adding or removing sections;
- changing layout hierarchy;
- changing colors or typography;
- rewriting visible copy;
- changing button labels;
- adding decorative graphics;
- replacing imagery;
- changing user flow;
- introducing a new library;
- changing a component's visual behavior;
- making conversion-oriented design changes.

Approval is not required for:

- semantic markup corrections;
- invisible accessibility metadata;
- CSS organization;
- browser compatibility fixes;
- performance optimizations that do not change the visual result;
- exact fidelity corrections.

---

## 17. Required Response Structure

When beginning a Figma implementation, respond with:

### A. Design Understanding

- target page or frame;
- implementation mode;
- target technology;
- available assets;
- **required fonts** — list every distinct `fontPostScriptName` on visible TEXT nodes,
  split into *free* (load from a CDN yourself) and *licensed* (the user must supply).
  Name the exact files and the exact folder. Do this in the **first** reply, not at
  delivery — the user cannot act on it after the fact;
- missing information;
- assumptions.

Produce the font list with `scripts/figma_fonts.py` (§0.3) — never from memory or from a
previous project — and state it in the **first** reply using the template in §0.3. It must
name, for *this* design:

1. every **licensed** face, by `fontPostScriptName`, and what it is used for;
2. the exact folder to drop them in (`design/fonts/`);
3. every **free** face, which you load yourself and must not ask for;
4. that they cannot be extracted from Figma or an SVG export;
5. what you will substitute meanwhile, and that the type will not be exact until they land.

### B. Implementation Plan

- global tokens;
- component list;
- responsive strategy;
- interaction strategy;
- validation method.

### C. Optional Recommendations

Only include recommendations supported by a concrete observation.

### D. Approval Questions

Group optional changes into one concise approval request where practical.

Example:

> I can reproduce the Figma exactly first. I also identified two optional improvements:
> 1. subtle hero entrance animation;
> 2. stronger hover feedback for feature cards.
>
> Neither appears in the source design. Should I include both, only one, or keep the implementation strictly identical?

---

## 18. Final Delivery Structure

### 18.0 Ship a fidelity report — evidence, not assurances (required)

Never close a build with a sentence like "it matches the design". Hand the user something
they can check without trusting you:

```bash
# 1. once per project: sign the icon set so identity (not just presence) is checked
python3 scripts/figma_icons.py --svg design/exports/page.svg --nodes figma/nodes --out figma/icons
# 2. every audit round:
python3 scripts/figma_report.py --page http://localhost:PORT/index.html \
        --nodes figma/nodes --selectors selectors.json --icons-dir figma/icons
```

`selectors.json` maps each Figma section frame to ONE CSS selector:
`{"hero": ".hero", "collection": ".collection", ...}` — keys must match the node JSON
filenames. Without it sections are matched by DOM order, which mis-maps silently; the
report header lists any selector matching 0 or 2+ elements — fix those before reading rows.
Skipping `--icons-dir` downgrades the icon audit to presence-only (it will say so).
`--assets-map figma/assets-map.json` (`{imageRef: filename}`) enables image IDENTITY —
without it the report cannot say the RIGHT photo is on the node (on the reference build
this check caught two cards silently reusing another card's photo). Known noise: a file
with stacked overlapping variants stamps the template's imageRef over real positions —
identity rows saying "expects <first-photo>" at spots that already pass with their own
ref are variant ghosts (FM99), not defects.

Version every stylesheet and script from the first commit (`styles.css?v=1`, `main.js?v=1`)
and bump on each edit — browsers heuristically cache unversioned assets and the report (and
you) will measure stale code (FM92).

It writes `fidelity-report.html`, which for every section shows the Figma reference beside
the **live** page, with a cross-fade slider and a *difference* blend (a perfect match goes
black), and computes — in the browser, at load time:

| Check | Why it exists |
|---|---|
| section height, Figma vs built | the obvious one |
| **content extents (left–right edge)** | heights match while a container is offset sideways; only this catches it |
| horizontal overflow | breaks silently below the design width |
| total page height | catches drift that per-section rounding hides |
| **every TEXT node: position, size, weight, colour** | the box can be perfect while the design inside it is wrong |
| **every icon: exported asset / hand-drawn / missing** | hand-drawn icons pass every geometric check and still look wrong |
| **every image: real photo / gradient placeholder / missing** | placeholders survive to production when nothing counts them |
| **every non-text box: fill colour, corner radius** | the text audit is blind to a panel with the wrong colour |
| **sections with no reference slice** | an unchecked section is how a whole section goes missing |
| **the section→selector mapping itself** | a selector matching 0 or 2 elements silently invalidates every row |
| **hover transition durations** vs `interactions[]` | the design states them; nothing else checks you shipped them |
| **stroke colour and drop shadows** on boxes | a rule the design draws as a stroke is easy to fake as an element |
| **image identity** (`--assets-map`) | "a photo is present" is not "the right photo is present" |
| **confirmed breakpoints not covered** (`--breakpoints`) | a second design silently never gets built |

**Do not stop at the geometry checks.** They pass on a page that looks nothing like the
design. In one build every section matched on height *and* content extents while only
**10 of 224 text nodes** matched on position, size, weight and colour. The geometry row is
a smoke test, not a verdict.

Three traps the text audit itself must avoid:

- Compare the **ink box** of the text (`Range.getBoundingClientRect()`), not the element
  box. A centred heading lives in a full-width block; comparing element rects reports a
  huge false offset.
- Only compare `font-weight` **within the same typeface**. And a declared `@font-face`
  whose file 404s still appears in `getComputedStyle().fontFamily` — ask
  `document.fonts.check(...)` whether the face actually loaded before trusting it.
- `text not found in DOM` is a real finding, not noise: it means your copy or your markup
  splits the string differently from the design.
- Group an icon at the **outermost pure-vector subtree**. Recurse further and every glyph
  outline of a logo is counted as its own missing icon.
- An icon reported `missing` may be a vector the design draws as a shape and you
  legitimately reproduce in CSS. That is a decision to record, not a row to ignore.

#### Guard the guards

An audit that can be fooled is worse than none, because it grants permission to stop
looking. Three holes are easy to leave open — close them:

- **Custom properties.** A linter that skips declarations containing `var()` can be
  defeated by moving the invented number into a token. Resolve `var()` before checking.
- **Section completeness.** A report that iterates over the references you happened to
  produce cannot notice a section you never sliced. Enumerate the design's sections and
  flag every one without a reference.
- **Selector mapping.** Require an explicit section→selector map, and fail if any selector
  matches zero or several elements. Falling back to DOM order will one day compare the
  wrong things and report green.

And in the box audit, separate a **wrong fill/radius** (a defect) from **no 1:1 element**
(a structural difference — Figma frames do not map one-to-one onto DOM elements). Reporting
them together produces a number that means nothing.

#### The audit runs in both directions

Every check that walks **design → DOM** ("the design has an icon here; is it in the page?")
is blind to whatever you *added*. That is not a small gap. A stray element, a doubled
control, a leftover from a refactor — none of them exist in the design, so nothing looks for
them, and the report keeps saying the build matches.

`figma_report.py` therefore also walks **DOM → design**: every graphic in a section that no
design node accounts for is listed as *not in the design*. Read that row. It is the only
place a mistake of commission can show up.

The same asymmetry applies to identity. "An icon is present at this node" and "the icon the
design puts at this node is present" are different claims, and only the second one is worth
anything. `figma_icons.py` stamps each exported icon with `data-icon-shape` (a scale- and
translation-invariant outline profile) and `data-icon-paint`; the report compares those,
with a tolerance on the shape and exactly on the paint. Two traps it exists to avoid:

- hashing the geometry — the same icon reused on the next card sits at sub-pixel-different
  coordinates, so a hash reports every legitimate reuse as a mismatch;
- comparing geometry alone — a filled star and an outlined star are the *same* outline and
  differ only in `fill`.

And because a comparator that always answers "different" makes a perfect build look broken,
the report proves it can recognise a file as itself before it reports a single verdict.

#### What this report still does *not* check

State this to the user, every time. A green report is evidence about what was measured and
nothing else.

- **the visual result of a hover state.** Durations are verified; what the variant *looks
  like* is not. Fetch the variants (`figma_pull.py --hover <destIds>`), look at them, and
  match your `:hover` by eye.
- opacity, gradients, z-order and overflow clipping
- focus and active states; keyboard behaviour
- accessibility and performance
- **regression** — there is no baseline diff; a fix that breaks another section shows up
  only if you read the whole report again
- anything at viewports other than the design width, and any breakpoint you did not build

Those need the difference-blend view, the reference frames, and your eyes.

Rules:

- The report's numbers are computed live from the page. **Do not paste a summary that the
  report does not show**, and do not claim a section matches while its row says *differs*.
- **Verify the verifier.** Before trusting a comparison view, confirm the reference and the
  live page are drawn at the same scale and offset; a mis-scaled overlay makes any build
  look correct. Confirm a known-bad section actually reports as bad.
- When you change CSS and re-measure through an iframe, **bust the cache** — a stale
  stylesheet will happily tell you the fix worked.
- Rows that legitimately differ (a decorative element you rendered as a shadow, a font
  substitution) belong in the difference log with the reason — not hidden by loosening the
  tolerance.
- A green report is *evidence about geometry*, not proof of visual fidelity. The
  difference-blend view is what proves that; look at it, and say what you saw.

At completion provide:

### 1. Completed Scope

List pages, sections, and states implemented.

### 2. Files Changed

List each created or modified file and its purpose.

### 3. Fidelity Notes

Point at `fidelity-report.html` first, then state:

- what matches the design;
- any unavoidable deviations;
- unavailable fonts or assets;
- assumptions used.

### 4. Responsive Coverage

List tested viewport sizes and behavior.

### 5. Accessibility and Performance Notes

State checks completed and remaining limitations.

### 6. Optional Next Improvements

List only unimplemented, user-approved, or still-pending suggestions.

Do not claim visual perfection without comparison evidence.

---

## 19. Acceptance Checklist

Before marking the work complete, verify:

### Visual Fidelity

- [ ] Container width matches reference
- [ ] Section spacing matches reference
- [ ] Grid and alignment match reference
- [ ] Typography matches reference
- [ ] Colors match reference
- [ ] Borders, radii, and shadows match reference
- [ ] Images use correct crop and aspect ratio
- [ ] Icons match size and alignment
- [ ] Text wraps similarly at reference viewport sizes

### Responsive Behavior

- [ ] Mobile layout is intentionally designed
- [ ] Tablet behavior is valid
- [ ] Desktop behavior matches reference
- [ ] No horizontal overflow
- [ ] Navigation works at all breakpoints
- [ ] Touch targets are usable
- [ ] Images remain sharp and correctly cropped

### Interaction

- [ ] `interactions[]` in the node JSON was read before any motion was written (§9.0)
- [ ] Figma's own durations/easings are used where they exist; springs are noted as approximations
- [ ] Inferred motion is labeled, and matches the mood the design already sets
- [ ] Entrance motion cannot hide content if the script fails (§9.0.2)
- [ ] Hover states work
- [ ] Focus states are visible
- [ ] Active and selected states work
- [ ] Keyboard operation works
- [ ] Form validation states exist when required
- [ ] Motion specified in Figma is implemented (no approval needed — it is the design)
- [ ] Motion *not* in Figma has user approval, or a standing instruction, and is labeled inferred
- [ ] Reduced-motion preference is respected

### Code Quality

- [ ] Semantic HTML used
- [ ] CSS variables defined
- [ ] Reusable components extracted
- [ ] No unnecessary duplication
- [ ] No arbitrary hacks without explanation
- [ ] No unsupported dependencies added
- [ ] No console errors

### Reference Coverage

- [ ] `fidelity-report.html` was generated, opened, and handed to the user
- [ ] The **text audit** was read, not just the geometry rows
- [ ] Every row in it is green, or every non-green row appears in the difference log
- [ ] No layout rule was weakened just to turn a metric green
- [ ] `figma_lint.py` passes: no invented spacing, size, colour, `<br>` or inline `<svg>`
- [ ] Icon audit is green, or every hand-drawn / missing icon is justified in the difference log
- [ ] Image audit is green: no gradient placeholders left
- [ ] The user was told what the report does **not** check
- [ ] Box audit reviewed: no wrong fills or radii among matched boxes
- [ ] No section is listed as "no reference slice"
- [ ] The section→selector map resolves to exactly one element per section
- [ ] Hover transition durations audited; hover *appearance* compared against the fetched variants
- [ ] `--assets-map` supplied so image identity, not just presence, is checked
- [ ] `--breakpoints` supplied; every confirmed width has its own report
- [ ] `figma_discover.py` was run **first** and its output shown to the user
- [ ] Every confirmed breakpoint frame was built and audited, not inferred
- [ ] No icon was hand-drawn that exists in the file's icon library
- [ ] Hover variants named by `interactions[]` were fetched and compared
- [ ] The scope (one screen vs a site) was confirmed against the file's page-sized frames
- [ ] Each section was audited with `--only <section>` as it was built, not just at the end
- [ ] The difference-blend overlay was actually looked at, not just the numbers
- [ ] Every implemented section has a reference image that was actually viewed
- [ ] No section was reconstructed from geometry/JSON alone
- [ ] Every section was screenshot-compared against its reference after being built
- [ ] Blocked sections are reported as blocked, not shipped as done
- [ ] Font substitutions are measured (§6.5.4), not guessed, and the delta is recorded
- [ ] Asset-to-node mapping was verified (no shuffled or off-by-one images)

### Final Honesty Check

- [ ] Assumptions are labeled
- [ ] Inferences are labeled
- [ ] Missing assets are disclosed
- [ ] Unverified claims are not presented as fact
- [ ] “100% identical” is not claimed without measurable verification
- [ ] Section heights matching is never presented as evidence the design matches
- [ ] Quota/permission failures are reported with the real cause (`Retry-After`, “File not exportable”), not glossed over

---

## 20. Recommended Folder Structure

A basic skill package may use:

```text
figma-to-html-pixel-perfect/
├── SKILL.md                          # this file
├── README.md                         # install + setup, for distribution
├── references/
│   ├── visual-review-checklist.md
│   ├── accessibility-checklist.md
│   └── animation-guidelines.md
└── scripts/
    ├── figma_discover.py             # FIRST: breakpoints, icon library, hover, scope
    ├── figma_icons.py                # extract every icon offline from the page SVG
    ├── figma_pull.py                 # preflight, node JSON, one render per section
    ├── figma_spec.py                 # correct node-JSON reader (§6.5.3 contract)
    ├── figma_fonts.py                # which fonts render, free vs licensed (§0.3)
    ├── figma_lint.py                 # build-stage guard: invented values, hand-drawn icons
    └── figma_report.py               # fidelity report: geometry + text + icon/image audits
```

`SKILL.md` is the only required file, but **use the scripts** — they encode §6.5.1–6.5.3.
Re-deriving them by hand is how the reading-contract bugs get reintroduced.

---

## 21. Core Principle

The supplied Figma design is the visual source of truth.

Implement first, verify second, recommend third, and change the design only after the user approves the change.

---

## 22. Known Failure Modes (all observed in real builds)

Every row below is a mistake that shipped. Re-read this before declaring a section done.

**Standing rule — when you find a new defect, close it in both stages.** Do not merely fix
the page. Ask: *what build rule would have prevented this*, and *what check would have
caught it*, then add both, add a row here, and add a line to the checklists. A defect that
is only fixed in the artefact will return in the next project. Everything you write must be
stated in terms of the design file, never in terms of one particular design.

| # | Failure | Symptom | Rule |
|---|---|---|---|
| 1 | Built a section without looking at its reference | Right height, wrong design | §6.5.0 |
| 2 | Bulk-downloaded every image fill | Render quota gone; `Retry-After` in days | §6.5.2 |
| 3 | Background job's stdout buffered | Most renders failed, unnoticed | §6.5.2 |
| 4 | Read `name` instead of `characters` | Button said the wrong thing | §6.5.3 |
| 5 | Ignored `style.textCase` | Whole page in Title Case, design is UPPER | §6.5.3 |
| 6 | Included `visible:false` nodes | Stale copy and ghost elements | §6.5.3 |
| 7 | Trusted `textAlignHorizontal` | Centred text "corrected" to left | §6.5.3 |
| 8 | Ignored `imageTransform` | Background photo upside-down | §6.5.3 |
| 9 | Sloppy `imageRef` filter | Every card photo shuffled by one | §6.5.3 |
| 10 | Named sections by order/height | Two sections swapped, one missing entirely | §6.5.3 |
| 11 | Invented copy where the design had `"Label"` | Fabricated category names and brands | §6.5.3, §0.5 |
| 12 | Guessed the fallback font | Wrong classification, wrong line breaks | §6.5.4 |
| 13 | Reported matching heights as proof of fidelity | Every height exact, design still wrong | §6.5.0 |
| 14 | Assumed "no animation in the design" | Thousands of `interactions[]` were sitting in the JSON | §5.6, §9.0 |
| 15 | Read only `style`, not `styleOverrideTable` | Hero's italic words: wrong family *and* size | §5.3 |
| 16 | Entrance motion hid content in CSS | Blank page whenever the script didn't run | §9.0.2 |
| 17 | Relied on `requestAnimationFrame` | Nothing revealed in a hidden/throttled tab | §9.0.2 |
| 18 | Passed `xmlns` to `xml.etree` as well | Duplicate attribute; every extracted icon broken | §0.5 |
| 19 | Copied Figma's fixed px columns verbatim | Overflow between the design width and 1024px | §8 |
| 20 | Misread `403 File not exportable` as a token problem | Chased duplicate/export workarounds that cannot work | §6.5.1 |
| 21 | Asked for the font at delivery | Too late to act on | §0.3, §17.A |
| 22 | Treated `visible:true` as "renders" | Counted an opacity-0 node; nearly demanded a font the design never shows | §6.5.3 |
| 23 | Checked only heights | Container offset sideways by a doubled gutter; every height still "matched" | §18.0 |
| 24 | Declared the build done from numbers | Handed the user a claim instead of a report they could check | §18.0 |
| 25 | Verified only the boxes | Every section "matched"; 10 of 224 text nodes actually did | §18.0 |
| 26 | Computed an SVG path's bbox by parsing numbers out of `d` | Curves and relative commands make it wrong; the logo silently cropped to a fragment. Measure with `getBBox()` in a browser | §0.5 |
| 27 | Removed a layout rule to make a metric pass | Dropped `100vh` on the hero so the height check would go green — optimised for the report, not the design | §18.0 |
| 28 | Invented spacing | `gap` values that exist nowhere in `itemSpacing`; became 129 vertical offsets in the audit | §6.5.5.1 |
| 29 | Invented line breaks | 15 `<br>` against 9 real newlines in `characters`; 78 text nodes then "not found in DOM" | §6.5.5.1 |
| 30 | Retyped sizes and colours from memory | Subtitle 18px vs 16px, one gold instead of the other | §6.5.5.1 |
| 31 | Ran the audit only at the end | Hundreds of offsets landed at once instead of one section at a time | §6.5.5 |
| 32 | Hand-drew icons from memory | 73 inline `<svg>` against 7 exported assets; every geometric check still passed | §6.5.5.1, §18.0 |
| 33 | Never counted icons or images at all | Placeholders and wrong icons survived to "done" | §18.0 |
| 34 | Believed a stale iframe | Verified a CSS fix that the browser had cached; re-check with a cache-busted reload | §6.5.5 |
| 35 | Trusted the verifier without verifying it | The overlay was drawn at two different scales, so a mismatch would have looked like a match | §18.0 |
| 36 | Linter skipped `var()` | Invented spacing hid inside custom properties and passed | §18.0 |
| 37 | Report only iterated the slices that existed | A section with no reference was silently unverified | §18.0 |
| 38 | Matched a design text to a whole element | Text sharing a parent with a `<span>` read as "not found"; repeated strings matched the wrong instance. Match the nearest **text run** to the expected position | §18.0 |
| 39 | Mixed "wrong colour" with "no matching element" in one count | Produced a meaningless score for the box audit | §18.0 |
| 40 | Believed `/files` and `/nodes` were not rate-limited | They 429 too; every REST endpoint shares a budget. Cache every response | §6.5.2 |
| 41 | Never looked for other design widths | Wrote a guessed mobile layout while a mobile frame sat in the file | §6.5.0.5 |
| 42 | Never looked for an icon library | Hand-drew dozens of icons the file already contained as components | §6.5.0.5, §0.5 |
| 43 | Never fetched the hover variants `interactions[]` point at | Invented hover states that were specified in the file | §6.5.0.5, §9.0 |
| 44 | Assumed the file held one screen | Built one page of what turned out to be a multi-page site | §6.5.0.5 |
| 45 | Claimed icons needed an API call | They are already in the page SVG export; the claim excused hand-drawing them | §0.5 |
| 46 | Exported a vector *group* as one icon | Two icons rendered stacked; looked plausible in a list, wrong on the page | §0.5 |
| 47 | Implemented hover timings, verified none | The design states every duration; comparing them costs one audit | §9.0.0 |
| 48 | Faked a stroke as an element | The design strokes a frame; the build draws a `<div>`. Only a stroke check sees it | §18.0 |
| 49 | Counted "a photo is present" as correct | Identity needs an `imageRef` → filename map, or any photo passes | §18.0 |
| 50 | Reported one breakpoint as if it were the design | Pass `--breakpoints` so uncovered widths are named in the report | §18.0, §6.5.0.5 |
| 51 | Exported a vector a photo paints over | `visible:true, opacity:1` ≠ renders. A later sibling with an opaque fill buries it | §0.5 |
| 52 | Called a photo an icon | A RECTANGLE/ELLIPSE with an IMAGE fill is a photo; exporting it sweeps up the paths behind it | §0.5 |
| 53 | Read only `<path>` from the SVG export | Figma also emits `<circle>`, `<rect>`, `<ellipse>`, `<line>`, `<polygon>`. Icons using them came out empty | §0.5 |
| 54 | Called a cluster of plain ellipses an icon | Carousel dots and rings are CSS shapes. An icon has a `VECTOR`/`BOOLEAN_OPERATION` in it | §0.5 |
| 55 | Exported a frame of several icons as one | A pager's two arrows, a five-star row. Split when the children are containers, disjoint, and icon-sized | §0.5 |
| 56 | Cropped the icon to its ink | The node's box is the icon's box. Cropping to the ink makes a 12px glyph fill a 40px button | §0.5 |
| 57 | Said "icon missing" when it was 60px off | Absent and misplaced are different defects; one word for both hides the fix | §18.0 |
| 58 | The report crashed and kept saying "measuring…" | A silent verifier reads as a passing one. Catch, banner, and syntax-check the report you emit | §18.0 |
| 59 | Left the nav in normal flow | It overlays the hero in the design; in flow it pushes every y below it down by its own height | §6.5.5.1 |
| 60 | Audited design → DOM only | Nothing you *add* to the page has a design node, so nothing looks for it. A stray toggle, a doubled arrow, a leftover element ships "verified" | §18.0 |
| 61 | Checked that *an* icon was there, never *which* | The mail icon sat on the YouTube row and the report said 95/106. Compare what the icon draws | §18.0 |
| 62 | Fingerprinted icons by hashing their geometry | The same icon reused on another card is sub-pixel-different: a hash calls every reuse a mismatch. And a filled star and an outlined star have identical geometry — a geometry-only fingerprint calls them equal | §18.0 |
| 63 | Wrote a comparator and never tested it | `sameIcon` was defined and never called; the operator left behind compared object identity, so every icon read "wrong". Prove the comparator can tell a file from itself | §18.0 |
| 64 | Drew a control the design draws as a vector | `appearance:none` plus a CSS triangle, *and* the exported chevron — two arrows on one select | §0.5 |
| 65 | Text audit cried "missing" over copy plainly on screen | The design splits `5`/`Bedrooms`; the build merges them; a `<br>` drops the joining space; a label renders as `placeholder=`. Match grouped runs, `innerText`, and form attributes — not just standalone text nodes | §18.0 |
| 66 | Reported one text number that hid the story | `10/224` read as "the text is broken" when 223 were present and only the *positions* were off. Decompose: present / positioned / sized / weighted / coloured | §18.0 |
| 67 | Let missing or reworded copy reach the browser to be found | `figma_lint.py` now fails the build if any visible `characters` string is absent from the HTML source — caught before a server ever starts | §6.5.5.1 |
| 68 | Measured a frozen mid-animation frame | The report's offscreen iframe has `document.hidden === true`, which freezes CSS transitions and IO. An entrance reveal (`opacity:0; translateY(18px)`) never completes, so **every** revealed element reads ~18px low and invisible — a perfectly-built page looked uniformly displaced. Force the final state (kill transitions/animations, neutralise reveal start-states) before measuring | §18.0 |
| 69 | Picked an outer wrapper as the text box | A `<label>` inside a group inside a field all share the same `innerText`; the taller outer ones sit higher and report a false y-offset. Keep only the leaf-most candidate | §18.0 |
| 70 | Compared ink-top to Figma's line-box-top | Figma's TEXT box top includes the line-height leading; the browser ink box starts at the glyph tops. The faithful analog is the element's own content-box top (when it wraps exactly that text) | §18.0 |
| 71 | Report measured stale cached CSS | The iframe re-loaded the HTML but the browser served the PREVIOUS `styles.css`, so a just-applied fix read as still-broken (a `width:100%` that was live on disk but not in the measured frame). Cache-bust the page AND re-point its same-origin `<link>`/`<script>`/`<img>`, awaiting the stylesheets before measuring | §18.0, §6.5.5 |
| 72 | A two-column space-between silently centred | `display:grid; justify-content:space-between` with fixed-width columns only distributes when the grid box spans the full width; left to shrink to content it centres, pushing one column inward by half the leftover | §6.5.5.1 |
| 73 | Compared a placeholder against the element's text colour | A design TEXT that renders as an `<input>` placeholder shows the `::placeholder` colour, not the element's `color` (which paints typed text). Read the pseudo-element colour when the match came from a form-field attribute | §18.0 |
| 74 | Merged number+label a design keeps as separate nodes | The build renders `"5 Bedrooms"` as one run; Figma stores `"5"` and `"Bedrooms"` separately. Match each substring's OWN range (fixed in FM75), then align it in CSS to the design's node x — a merged run whose substrings land at the design positions passes | §18.0, §6.5.5.1 |
| 75 | Whole-element match used the container rect for a substring | When an element's `innerText` merely CONTAINED the wanted text ("5" in "5 Bedrooms"), the audit used `selectNodeContents(element)` — the whole element's rect, which starts at the element's left (an icon), not the substring. Every split number/label across every card read a false 20-40px x-offset while the build was pixel-exact. Match EQUALS with the element rect; hand CONTAINS to the substring-ranging fallback so the position is the substring's own | §18.0 |
| 76 | Compared X at the left edge for centre/right-aligned text | Figma's `absoluteBoundingBox` is the LAYOUT box. A CENTER-aligned name in a full-column-width box has its ink far from the box's left edge, so comparing the built ink-left to the Figma box-left invents an offset the size of the box's slack (+195 on a centred name, +100 on a centred hero title). Read `textAlignHorizontal` and anchor the comparison at centre/right accordingly | §18.0 |
| 77 | Measured a form field at its border, not its text | A design TEXT that renders as an input placeholder/label was compared at the control's border box, but the design node is the TEXT, which sits inside the field's content padding — a uniform false offset the size of the padding. Anchor the comparison at the field's content box | §18.0 |
| 78 | Matched a `<select>` placeholder to a bare `<option>` | An `<option>` in a closed select has no layout box (rect at 0,0); the leaf-most-candidate filter then drops the real `<select>` in its favour and reports a nonsense −thousands-px offset. Match the control (`select`/`input`) via its `value`, and skip `<option>` in BOTH the attribute pass and the whole-element (innerText) pass, or the leaf-most filter keeps the zero-size option over the real select and the field reads "not found" | §18.0 |
| 79 | Drove the text-position score to 98% while a blank logo and a mis-broken heading shipped | The per-text-node audit sees NEITHER images NOR line-breaks/alignment. A high `x/y` pass rate is not "looks like the design." After the numbers plateau, STOP reading them and LOOK: open the difference-blend, scan every section against its reference slice, and check images and headings by eye | §18.0 |
| 80 | A wordmark logo vector-extracted to a solid white block | airbnb/agoda (line art) extracted fine; the Booking.com wordmark came out as 14 overlapping white paths that render as a filled rectangle. Complex/filled logos often do not survive vector extraction — LOOK at every extracted logo on its real background; if it is not the logo, use the raster (PNG) export instead | §0.5 |
| 81 | A two-line heading indented its second line | `white-space: pre-line` plus a source newline inside the `<h2>` inherited the HTML's source indentation, pushing line 2 in ~260px — invisible to the position audit, which compares the whole heading's centre. Break lines with an explicit `<br>`, not a source newline | §6.5.5.1 |
| 82 | Substitute font wrapped a heading to the wrong line count | A metrically-different fallback never reproduces design line breaks. Wire the real webfont first and assert `document.fonts.check('<w> <size>px "<family>"')` before trusting any heading geometry; never chase a wrap with size/spacing hacks | §0.4, §6.5.4 |
| 83 | Flex-centred text box collapsed to a narrow column and over-wrapped | Inside flex/grid, `max-width` alone lets a text box shrink-to-fit. Set the Figma box width as `width` so wrapping matches | §6.5.5.1 |
| 84 | Padding hacks pinned a heading's y but broke its box | Never tune paddings to hit a y-target. Rebuild the frame's own box model: panel padding = Figma inset, flow/flex children, bottom-anchored group via `margin-top:auto` | §6.5.5.1 |
| 85 | Design fonts never verified as loading | Fail lint when a design font-family has no `@font-face`/webfont link reference; flag headings whose rendered line-count differs from the design node's | §0.4, §18.0 |
| 86 | Pill button label wrapped to 2–3 lines | Design button labels are single-line: `white-space: nowrap` on the base button class | §6.5.5.1 |
| 87 | Card foot faked the button's x with nudges + mega-gap | A two-ended row is `flex; justify-content:space-between; align-items:center` with a small min gap. Delete positional nudges — they hold at one width only | §6.5.5.1 |
| 88 | Read only a TEXT node's base weight and missed a bold sub-run | Emphasis can live entirely in `styleOverrideTable`/`characterStyleOverrides`. Union base `style` with every override when reading weight/style/size/colour; compare the SET of weights against the CSS | §6.5.4, §18.0 |
| 89 | Guessed the active/selected state's colour from a generic token | The selected variant is its own node with its own fills. Read the selected child's fill AND its TEXT fill; assert both against the `.is-active` rule | §6.5.4 |
| 90 | Dropped a control's track/container fill | Segmented controls, toggle tracks and tab strips often have their own background fill. Read every container FRAME's `fills`; flag a visible solid fill whose CSS element is transparent | §6.5.4 |
| 91 | Sized an interactive box by eyeballing padding | Buttons/badges are fixed w×h frames. Measure the rendered rect vs the Figma frame (±1px, border-box including border) and re-measure after every change — a comment is not verification | §6.5.5.1, §18.0 |
| 92 | Rewriting `<link>.href` did NOT reparse the CSS | Verify a CSS edit by hard-navigating to a fresh URL (`?cb=<n>`), then assert the changed property's computed value BEFORE trusting any downstream measurement | §6.5.5, FM34 |
| 93 | Text-hugging pills + per-item `left:` nudges made uneven gaps | When a control's repeated items share one frame size, set that w×h on each item, centre the label with `inline-flex`, and use the container `itemSpacing` as flex `gap`. Never rebuild spacing with per-item offsets | §6.5.5.1, FM87 |
| 94 | Invented a grey container border + phantom shadow | Border colour/width come from `strokes`/`strokeWeight`; add `box-shadow` only if a DROP_SHADOW exists in `effects`. Flag CSS border/shadow colours that appear in no design stroke/effect | §6.5.4, FM90 |
| 95 | Claimed "verified" after checking only colours | A repeated-item control passes only when ALL match: each item's w×h, the FULL sequence of inter-item gaps, container width, border colour+width, and shadow presence. Fills matching while geometry is wrong is the most common false "done" | §18.0, FM91 |
| 96 | A house `letter-spacing` + transparent border bloated a button, then padding was fudged | Fix text metrics FIRST: match the button TEXT node's letterSpacing/weight/size/textCase exactly (often ls 0); a no-stroke button gets `border:0`; then the Figma padding yields the exact box. A ±1px box is a false pass while text metrics differ | §6.5.5.1, FM91 |
| 97 | A margin hack rendered 7px while its comment claimed "Figma 20" | Measure the RENDERED divider→next-row gap and assert it equals the Figma metric (`nextNode.y − divider.y`, ±2). In a flex column, `margin-top` ADDS to the container `gap`. When the user says a gap is off, extract the Figma number first — never guess the direction | §6.5.5.1, FM95 |
| 98 | A carousel was reduced to a static image | ≥2 small equal ELLIPSEs clustered on an image frame = slider pager. Reproduce the dots to spec and plan the slider (multiple assets + JS). The active indicator is often composite — an outer ring plus an inner dot: read both nodes | §6.5.4, §15 |
| 99 | Trusted the JSON node-dump as complete | Exported JSON can omit component internals, masks and vector strokes. Cross-check against a rendered image of the frame and reproduce render-visible details the JSON lacks — pixels are ground truth, JSON is a lossy index | §0.4, §6.5.4 |
| 100 | Fallback-era weight compensation survived the real font | After fixing a font substitution, re-derive every weight/size/ls that was fudged for the fallback from the Figma nodes, delete the "≈" comments, and `document.fonts.check` the exact weight. Verify each section's title weight individually — designs make exceptions | §0.4, FM85 |
| 101 | Trailing meta drifted across cards with variable body length | When trailing elements share a baseline in the design, give the variable-length text a `min-height` sized to the longest case; assert the trailing elements' tops are equal across the row | §6.5.5.1, FM95 |
| 102 | Audit checked heading fonts but never per-line alignment | For every multi-line heading also assert: computed `text-align`, `text-indent: 0`, and every line's start-x equal (`Range.selectNodeContents` → `getClientRects()`); inspect the HTML bytes around `<br />` for collapsed spaces | §6.5.4, FM95 |
| 103 | Declared "flush" from ONE viewport width | `text-align:left` does not stop a `max-width` block being centred by inherited `margin:auto` — reset `margin-inline: 0`. Verify alignment at the design width, a wider (≥1920) and a narrower viewport, AND against the siblings that share the edge | §6.5.5, §7, FM102 |
| 104 | Icon SVG and CSS both drew the ring — and the icon set was inconsistent | Open every icon's SVG source: a baked-in full-size `<rect rx>`/`<circle>` IS the container — the wrapper then adds none. Pick ONE owner of the shape, normalise the whole set, and verify every direction/state renders exactly one ring. `<img>` SVGs ignore CSS `color` | §6.5.4, §5 |
| 105 | Mirrored background photo; a nudge broke two panels' shared top edge | Check a directional photo's orientation against the design; flip via an absolutely-positioned `::before` with `transform: scaleX(-1)` (background-image itself can't transform). Panels that share a Figma y have NO vertical offset — delete nudges and assert equal tops | §6.5.4, FM87 |
| 106 | Logo strip passed on item sizes while the gaps were 3× too small | A logo row is a repeated-item control: measure every `item[i+1].left − item[i].right` against Figma; size the row container to the Figma row width and use `space-between` | §6.5.5.1, FM95 |
| 107 | Transparent PNG padding shrank the mark; opacity and colour ignored | Raster logos: crop to the content bbox (declared box ≠ visible ink — check `naturalWidth`/`getbbox`); apply the node's group `opacity`; match the RENDERED colour, not the stored brand fill (`filter: brightness(0) invert(1)` for a white-unified strip) | §5, FM106 |
| 108 | A generic container rule hijacked a nested button's padding AND display | Blanket rules (`.footer a { display:block; padding:5px 0 }`) silently steal a `.btn`'s box and centring. Give fixed-size buttons explicit w×h + their own later equal-specificity rule (`a.the-btn`); NEVER raise the broad selector's specificity (`:not(.btn)` out-ranked and broke sibling rows). Re-verify the whole container after any specificity change | §6.5.5.1, §13, FM91 |
| 109 | Sections were vertically CENTRED inside locked min-heights — every y floated with content height | A "lock each section to its Figma frame height" rule paired `min-height` with `display:flex; justify-content:center`, so each section's content sat at (min-height − content)/2. Every content-height change re-shifted every y in the section, offsets oscillated between audit runs, and a dozen nudges were tuned against the drift. Figma sections are TOP-anchored: content y = the section's own padding. Lock heights with `min-height` + `justify-content:flex-start` and set padding-top = the first node's Figma y; never centre a section whose design ys are absolute. If audit offsets CHANGE between runs without related edits, suspect a centring/auto-margin ancestor first | §6.5.5.1, FM103 |
| 110 | The measuring viewport's scrollbar shifted every x by a constant and failed the whole audit | The fidelity probe rendered the page at the design width, but the page scrolls, so the layout viewport was designW−15px: every centred/right-anchored element measured a constant ~7-15px left of Figma and the text audit failed wholesale (±4 tolerance < shift). Before ANY x-comparison, assert `document.documentElement.clientWidth === designWidth`; if short, widen the window/iframe by the scrollbar width. A CONSTANT x-offset across every node is a viewport artifact, not a build defect — fix the measurement, not the CSS. (figma_report.py now auto-widens its probe iframe.) | §6.5.5, §18.0 |
| 111 | The page had zero overflow at the design width and broke at EVERY narrower one | Below-design-width overflow came from five distinct classes, all invisible at 1600: (a) fixed component widths (`.card { width:440px }`, media `width:910px`) — size components with `width:100%` and let the grid track carry the design px; (b) `repeat(N, 1fr)` tracks — `1fr` = `minmax(auto,1fr)` and blows out on nowrap/min-content children; always write `minmax(0,1fr)`; (c) late-in-file wide-viewport overrides out-cascading earlier narrow breakpoints at equal specificity — scope them with range media (`min-width:X and max-width:Y`); (d) an override written for the wrong display type (`grid-template-columns` on a still-flex element does nothing); (e) removed `flex-wrap` on a pill row. Verify with an overflow sweep at ~8 widths (design, 1440, 1280, 1024, 900, 768, 640, 375): `scrollWidth − clientWidth === 0` per width, and after every fix RE-ASSERT the changed property in the probe before re-measuring | §8, FM92, FM103 |
| 112 | The verifier itself had five blind spots that read a correct build as broken (or hid real defects) | Fixed in figma_report.py; the classes recur in ANY audit tooling: (a) text inside a closed `<option>` has a 0×0 rect and, if collected, wins the leaf-most filter over the real `<select>` — skip option-descendant text nodes, match the control by value/aria-label; (b) a Figma box with an IMAGE fill exports its invisible SOLID underlay — never compare that colour to CSS, and treat a CSS background-image, a matched `<img>` itself, or a child img covering ≥80% as "image-covered"; (c) radii must be normalised before comparing: resolve `%` against the element box and clamp BOTH sides to min(w,h)/2 (Figma pill radii like 999/1353 = CSS 50%); (d) near-invisible strokes (opacity/alpha < .5) are not a border requirement, and a design stroke may render as any ONE border side — check all four; (e) the report's own cache-bust pass rewrote `src="x.svg"` to `x.svg?bust`, so its icon selector `src$=".svg"` matched nothing — after ANY self-modification of the page, selectors written against the original markup must be re-checked. Also: naming a new asset without checking for an existing file of that name overwrote an in-use icon (verify `ls` before `cp`) | §18.0, FM110 |
| 113 | Hover-timing audit read 0ms everywhere; the entrance reveal was also silently overriding every hover transition | Three coupled findings. (a) The report froze animations (`transition:none!important`) to measure geometry, then read `transitionDuration` — measuring what it had itself disabled (0/26). Duration reads are now QUEUED and flushed after the freeze style is removed, in steady-state (entrance markers stripped, since a hidden probe never fires IntersectionObserver). (b) Wrapper/element/icon often share one box: keep the whole tie-set of candidates and let the duration read take the max — a lone "nearest" pick lands on the wrapper (0s) or the icon `<img>`. (c) REAL defect class: a CSS-transition entrance (`[data-reveal] { transition: opacity .82s, transform .82s }`) out-cascades the element's own hover transition (same `transform` property, higher specificity) — every card hovered at the reveal's 820ms instead of the design's 1022ms. Run entrances via WAAPI (`el.animate(...)`, inline `opacity:0` until shown) so the `transition` property is never occupied and hover timing stays the element's own. Also: this Browser-pane environment freezes the animation clock (rAF dead, `playState:running` with `currentTime` stuck at 0) AND blocks all programmatic scroll — "stuck at opacity 0" and "reveal never fires" there are environment artifacts; verify wiring (attrs stripped, animations created, computed transition durations) instead of watching pixels move | §9, §18.0, FM110 |
| 114 | Assumed only the render endpoint was rate-limited; `/v1/files` (node JSON) also 429'd for hours | Figma REST quotas are plan-based and cover EVERY endpoint, not just renders — mid-project, `/v1/files` returned 429 Retry-After ~6h while the fill-URL endpoint still worked. The build survived only because all node JSON had been cached to disk on day one. Rule: the API is for ACQUISITION, the disk cache is the workspace — pull once into `figma/nodes/`, make every script read the cache, make the puller skip anything already on disk, and on any 429 report the Retry-After and continue offline from cache instead of blocking. Never design a step that needs the API on every run | §0.1, §6.5 |
