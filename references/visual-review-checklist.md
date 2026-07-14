# Visual Review Checklist

Use this checklist during **Step 5 — Visual Comparison** and **Step 7 — Final Verification**.
Compare the implementation against the reference at identical viewport dimensions.

## Build gate (before you look at anything)

- [ ] `figma_lint.py` passes — no `gap`, `font-size` or colour that the design never uses
- [ ] `<br>` count does not exceed the newlines in `characters`
- [ ] Type values came from each TEXT node's `style`, not from memory
- [ ] Spacing came from `itemSpacing` / `padding*`, not from a scale you like
- [ ] No design value is hidden inside `clamp()` at the design width
- [ ] Every icon is an exported vector, not an inline `<svg>` drawn from memory
- [ ] No gradient/box placeholder remains where the design has a photo

## Gate (do this first, per section)

- [ ] A reference image for **this** section exists and I have actually looked at it
- [ ] The section was screenshot-compared against that reference after being built
- [ ] I am not relying on matching heights/spacing numbers as proof of visual fidelity
- [ ] Text case (UPPER/lower), real button labels, and asset→node mapping were checked
      against the node JSON (`characters`, `textCase`, `visible`) — not assumed
- [ ] Nodes with `visible:false` **and** nodes whose cumulative ancestor `opacity` is 0
      were excluded — `visible:true` does not mean "renders"
- [ ] Per-character overrides (`styleOverrideTable`) were read, not just `style`
- [ ] Motion the file specifies (`interactions[]`) is implemented, not skipped
- [ ] The **text audit** for this section was run (`figma_report.py --only <section>`)
      while building it — not deferred to the end
- [ ] Opacity/animation assertions were made with transitions disabled — a hidden tab
      freezes transitions and reports the mid-flight value

## Layout & Structure

- [ ] Max content width matches the reference container
- [ ] Container gutters / horizontal padding match
- [ ] Section vertical spacing (top/bottom) matches
- [ ] Grid column count and gap match
- [ ] Flex/grid alignment (start/center/end/space-between) matches
- [ ] Internal component padding matches
- [ ] Sticky / fixed elements behave as designed
- [ ] No unintended overflow (horizontal or vertical)
- [ ] Z-index / stacking order of overlapping elements is correct

## Typography

- [ ] Font family matches (or documented fallback in use)
- [ ] Font weight matches per text role
- [ ] Font size matches per breakpoint
- [ ] Line height matches
- [ ] Letter spacing matches
- [ ] Text transform (uppercase/capitalize) matches
- [ ] Text alignment matches
- [ ] Text color matches
- [ ] Heading hierarchy is correct and ordered
- [ ] Paragraph max-width / measure matches
- [ ] Text wraps at the same points as the reference

## Color & Surface

- [ ] Background colors match
- [ ] Surface / card colors match
- [ ] Accent / brand colors match
- [ ] Border colors and widths match
- [ ] Gradients match (direction, stops, colors)
- [ ] Opacity / transparency values match

## Depth & Shape

- [ ] Border radius matches per element
- [ ] Shadows match (offset, blur, spread, color)
- [ ] Blur / backdrop-filter matches
- [ ] Dividers and separators match

## Imagery & Icons

- [ ] Image dimensions and aspect ratios match
- [ ] object-fit / crop matches the reference
- [ ] Focal point of cropped images is preserved
- [ ] Icons match size, stroke weight, and alignment
- [ ] SVG vs raster usage is appropriate
- [ ] Background images position and scale correctly
- [ ] No missing or placeholder assets remain

## Spacing Precision (spot-check with dev tools)

- [ ] Gaps between repeated cards/items are exact
- [ ] Button padding matches
- [ ] Icon-to-text spacing matches
- [ ] Label-to-field spacing in forms matches

## Cross-Viewport

- [ ] Desktop matches the desktop reference frame
- [ ] Tablet behaves correctly (if a frame is supplied)
- [ ] Mobile matches the mobile reference frame
- [ ] Transitions between breakpoints are clean (no jumps/overlap)

## Coverage — what the report does not prove

- [ ] I told the user that colour/radius/stroke/shadow of non-text elements, z-order,
      hover and focus states, motion timings, and other viewports are **not** covered
- [ ] I looked at the difference-blend overlay myself and said what I saw

## Difference Log

Record every remaining discrepancy before declaring completion:

| Area | Difference | Cause | Fix | Status |
|---|---|---|---|---|
|  |  |  |  |  |

## Icons — the traps that look like success

- [ ] Every icon in the build is an `<img>` pointing at a file extracted from the design.
- [ ] You **opened the extracted icons and looked at them**, on a background that contrasts
      with them. White icons on a white contact sheet look like missing files.
- [ ] No icon is a photo (a shape with an `IMAGE` fill), a carousel dot, or a decorative ring.
- [ ] No icon is a component's placeholder artwork buried under a photo.
- [ ] A frame holding several icons was split, not exported as one.
- [ ] Each icon renders at the size of its node in the design, not the size of its ink.
- [ ] The fidelity report distinguishes *absent* from *placed wrong*; both are read.
