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
