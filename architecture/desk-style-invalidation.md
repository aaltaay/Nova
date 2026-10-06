# Bound live-desk style invalidation (#707)

Owner: Desk Catalyst presentation and the shared AlertDialog primitive. Follows
[ADR 006](decisions/006-css-itcss-cascade-layers.md): reusable primitive styles
belong in the components layer; Desk composition stays in its feature sheet.

## Current defect and evidence

The selector/memo and GPU items previously recorded on #707 are already fixed.
The remaining drawing slowdown reproduces in a production demo at 2560 × 1400,
DPR 1.5, with approximately 66 tape prints per second. Normal tape virtualization
inserts and removes rows. Chromium marks BODY's `:has()` state dirty, then uses a
shared pseudo-class invalidation set containing two whole-subtree selectors:

- The Desk's keyboard-focused actions hide Catalyst `> *` descendants.
- AlertDialogTitle's generated Tailwind `group-has` utility contains an ancestor
  `:has()` followed by a universal descendant inside `:is()`.

Those selectors make unrelated body descendants eligible for recalculation,
even while neither the Desk board nor a dialog is showing. The production trace
regularly restyles 1,535–1,538 elements for a tape update. Merely removing the
body layout selectors or promoting panes/rail to layers does not fix this cause.

A browser-only probe that constrains the two descendant targets reduces these
passes to 1–53 elements. Three quiet four-second baseline/probe pairs measured
43.1–44.7 fps versus 54.4–57.8 fps, with style recalculation falling from
1,139–1,167 ms to 191–206 ms. These are local fixture results, not a physical-PC
measurement or a guarantee of frame rate on another desk.

## Implementation contract

1. Keep the Desk's existing hover and `:focus-visible` conditions. Hide the
   Catalyst's named chip, clock and absent-value children rather than `> *`.
2. Keep AlertDialogTitle's media behavior: at the existing `sm` breakpoint, a
   default-size dialog containing media starts its title in column two. Small
   dialogs and dialogs without media keep their current layout. Replace the
   generated `group-has` utility with a components-layer selector whose final
   target is the title's explicit data slot.
3. Preserve text, controls, focus, keyboard navigation, tape/depth updates and
   order confirmation. No feed throttling, hidden content, new compositor
   policy, trading-policy change or duplicate memo/containment work.
4. Future relational selectors must identify the descendant whose style changes.
   A global `:has()` invalidation set must not make an unrelated live update
   restyle the whole document.

## Verification plan

- Before production edits, reproduce the failure with a Chromium regression
  that inserts/removes tape-like DOM rows and checks the trace's affected style
  element count against a population of unrelated canary elements. Use counts,
  not a timing/FPS threshold, so CPU contention does not decide correctness.
- Check actual Desk hover, row keyboard focus and action keyboard focus, plus
  mouse-focus release, with Catalyst text unchanged.
- Check real AlertDialog title layout for default/small sizes, media present or
  absent, and widths on both sides of the existing responsive breakpoint.
- Run the neighboring Desk and order-confirmation checks, frontend build/lint
  and maintainer gate. Repeat paired production measurements after a quiet
  window becomes available; report the fixture and measurement limits.
