# Motion Guidelines

There are two kinds of motion, and they are governed by opposite rules.

| | Motion **in** the Figma file | Motion **you would invent** |
|---|---|---|
| What it is | Part of the design | An enhancement |
| Mode | **A — required** | **C — needs approval** (or a standing instruction) |
| Ask first? | **No. Build it.** | Yes (or confirm the standing instruction) |
| Label it? | No — it *is* the design | Yes — every value is inferred |

Not implementing motion the file specifies is a fidelity bug, exactly like a wrong colour.

## 1. Read the motion the file already has — first, always

```bash
grep -l '"interactions"' figma/nodes/*.json    # non-empty => the design specifies motion
```

Never write "the design has no animation" without having run this.

Per interaction, record:

| Field | Meaning |
|---|---|
| `trigger.type` | `ON_HOVER`, `ON_CLICK`, `ON_DRAG`, `AFTER_TIMEOUT` |
| `trigger.timeout` | autoplay interval, in **seconds** |
| `actions[].transition.type` | `SMART_ANIMATE`, `DISSOLVE`, `PUSH`, … |
| `actions[].transition.duration` | **seconds** — multiply by 1000 |
| `actions[].transition.easing.type` | `GENTLE`, `SLOW`, `LINEAR`, `EASE_*`, `CUSTOM_CUBIC_BEZIER` |
| `effects[]` | real `DROP_SHADOW` / `BACKGROUND_BLUR` to reproduce |

### Figma easing → CSS

Figma's named easings are springs; CSS has none. Approximate, and say that you did.

| Figma | Character | Reasonable CSS |
|---|---|---|
| `GENTLE` | soft settle, slight overshoot | `cubic-bezier(0.34, 1.16, 0.64, 1)` |
| `SLOW` | long, pure decelerate | `cubic-bezier(0.33, 1, 0.68, 1)` |
| `EASE_OUT` | standard decelerate | `cubic-bezier(0.16, 1, 0.3, 1)` |
| `CUSTOM_CUBIC_BEZIER` | exact | copy `easingFunctionCubicBezier` verbatim |

Two traps:

- Spring durations (often 800–1300 ms) are **settle** times, not perceived times. Reproduce
  the design's number — the design outranks your taste — and note the tension with the
  microinteraction ranges below.
- `AFTER_TIMEOUT` implies an autoplaying carousel. Check the file actually contains the
  other slides. If it has only one, **do not invent them**: implement the timing you can
  and report the missing slides.

## 2. When the file specifies no motion

Then, and only then, infer it — from the design, not from habit. Read the mood off what the
file *does* specify:

- **Easings and durations already in use** — if everything is slow and gentle, a snappy
  200 ms bounce is wrong.
- **Type and colour** — high-contrast display serif with a muted palette reads editorial
  and restrained.
- **Effects** — heavy blur and soft shadows imply soft, layered motion, not snap.

Then pick the smallest motion that serves that mood: fade plus a short rise (12–20 px), a
generous duration, a decelerating curve, a light stagger. Label every inferred value.

Propose it in this form:

> **Optional enhancement — [section/component]**
> I recommend `[motion]` because `[specific reason]`.
> Behaviour: `[trigger, duration, easing, movement]`.
> This is not in the Figma file. Should I add it?

## 3. Motion must never hide content

Entrance animation that sets `opacity: 0` in CSS is a blank page whenever the script fails,
JS is off, or the tab is throttled — `IntersectionObserver` callbacks and CSS transitions do
not run in a hidden tab.

- Scope the hiding rule to a class the script adds: `html.motion [data-reveal] { opacity: 0 }`.
- Reveal on `IntersectionObserver` **and** a passive `scroll` sweep **and** `visibilitychange`.
- Never depend on `requestAnimationFrame` for the first pass.
- Verify by disabling the script: the page must be fully visible.

## 4. Default ranges (only when nothing is specified)

| Category | Duration | Use |
|---|---|---|
| Microinteraction | 120–220 ms | hover, press, toggle, focus |
| Component transition | 180–320 ms | accordion, tab, dropdown |
| Section entrance | 350–650 ms | hero reveal, scroll-linked reveal |

Defaults, not mandates — and always outranked by a value the file states.

## 5. Quality rules

Motion must reinforce hierarchy or give feedback; stay subtle; never block input; never
cause layout shift (animate `transform`/`opacity`, not `width`/`top`); avoid heavy parallax
and long entrance sequences; preserve keyboard use; and respect `prefers-reduced-motion`.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Prefer targeted handling over the blanket reset for essential state changes (an accordion
should still open — instantly, not never).

---

# Full Motion Policy (moved from SKILL.md §9)

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
