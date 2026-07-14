# Accessibility Checklist (WCAG 2.2 AA target)

Verify without changing the approved visual direction. Where a fix would change the
visible design, flag it as a Usability Issue and request approval.

## Structure & Semantics

- [ ] Landmarks used correctly (`header`, `nav`, `main`, `footer`, `aside`)
- [ ] One `main` per page
- [ ] Headings are ordered (no skipped levels; single logical h1)
- [ ] Lists use `ul`/`ol`/`li`; tables use `th`/`caption` where relevant
- [ ] Buttons for actions, links for navigation
- [ ] No duplicate `id` attributes

## Keyboard

- [ ] All interactive elements are reachable by Tab
- [ ] Focus order is logical and matches visual order
- [ ] No keyboard traps
- [ ] Visible focus indicator on every focusable element
- [ ] Focus outline not removed without an accessible replacement
- [ ] Custom widgets (menu, tabs, accordion, modal) support expected keys
- [ ] Modal traps focus and restores it on close; Esc closes

## Names, Roles, Values

- [ ] All form controls have associated `<label>` (or `aria-label`)
- [ ] Icon-only buttons have accessible names
- [ ] Images have meaningful `alt`; decorative images use `alt=""`
- [ ] ARIA used only when native HTML is insufficient
- [ ] Dynamic updates announced (`aria-live` where appropriate)
- [ ] Error messages programmatically associated (`aria-describedby`)

## Color & Contrast

- [ ] Body text contrast ≥ 4.5:1
- [ ] Large text (≥ 24px, or ≥ 19px bold) contrast ≥ 3:1
- [ ] UI component / graphical object contrast ≥ 3:1
- [ ] Information is not conveyed by color alone
- [ ] Focus indicator contrast ≥ 3:1 against adjacent colors

## Target Size & Input (WCAG 2.2)

- [ ] Touch targets ≥ 24×24 px (prefer ≥ 44×44 px)
- [ ] Adequate spacing between adjacent targets
- [ ] Dragging actions have a single-pointer alternative
- [ ] No content relies solely on hover to be accessible

## Motion & Media

- [ ] `prefers-reduced-motion` respected for all non-essential animation
- [ ] Entrance animation cannot hide content if the script fails (hiding rule is scoped to
      a class the script adds; never CSS-only `opacity: 0`)
- [ ] No content flashes more than 3 times per second
- [ ] Auto-playing/moving content can be paused or stopped

## Forms

- [ ] Required fields indicated in text, not color alone
- [ ] Inline validation is associated with its field
- [ ] Error summary provided for longer forms
- [ ] Success confirmation is announced

## Verification Tools

- [ ] Automated pass (axe / Lighthouse) with issues triaged
- [ ] Manual keyboard-only walkthrough completed
- [ ] Screen reader spot-check on key flows
