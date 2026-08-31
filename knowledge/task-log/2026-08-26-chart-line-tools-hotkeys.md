# 2026-08-26 -- Chart line-tool dropdown and Alt hotkeys

- **Status:** completed
- **Agents:** parent
- **Domain:** frontend / chart drawings
- **Related:** `CHANGELOG.md` 2026-08-26 chart line tools; ADR 015; D-004;
  D-005

## Task

Add Trendline, Horizontal Line, Vertical Line, Extended Line, Ray, and
Horizontal Ray to one chart dropdown, with a dedicated hotkey for each.

## Goal

Every chart surface exposes the six line tools without crowding the toolbar.
Alt+T/H/V/E/J/R arms the requested tool only on the last chart pane the
operator interacted with.

## Why it mattered

The old toolbar had only three line types as separate buttons. It lacked the
directional and extended lines used for support, resistance, and projected
trend work, and the four-pane Trader grid made global hotkeys unsafe without
an explicit pane owner.

## What we changed

- Added one split dropdown with six SVG line icons, labels, and hotkey hints.
- Added `ExtendedLine`, `Ray`, and `HorizontalRay` to the existing drawing
  manager and ADR 015 persistence/hydration path.
- Generalized placement into one-anchor and two-anchor registries.
- Added chart-local Alt hotkeys with editable-target, modifier, and repeat
  guards.
- Added last-interacted-pane ownership so one hotkey never arms all four Trader
  charts.
- Kept Crosshair and Clear All as separate toolbar buttons.

## How it works now

The line dropdown remembers the last chosen line tool for its chart pane. The
main half arms that tool and the caret opens all six choices. Toolbar selection
and Alt hotkeys both set the same `activeTool`; the existing drawing manager
collects one or two anchors, emits `drawing:added`, persists through the
symbol-keyed store, and then clears the active tool.

Each mounted chart has a unique focus token. Pointer enter or pointer down
claims the shared token; its key listener ignores drawing hotkeys unless it
owns that token. Delete and Backspace retain their existing selected-drawing
behavior.

## Why this approach

The installed drawing library already owns geometry, hit testing, JSON, and
hydration for all six tools, so custom canvas primitives would duplicate
tested behavior and risk breaking ADR 015 persistence. Chart hotkeys stay out
of the Nova Action dispatcher because that dispatcher is for trading actions
and safety gates. A tiny focus token is enough to coordinate the Trader grid
without creating a second global hotkey framework.

## Verification

- Red-first tests proved the missing hotkey resolver and menu component.
- `npx vitest run`: 172 files, 835 tests passed.
- `npx tsc --noEmit`: exit 0.
- `npm run build`: exit 0.
- Live browser: opened all six tools in Trader and Scanner Quote Panel; placed
  an Extended Line on SPY, saw it fan out to other intraday panes, confirmed
  `extended-line` through the API, reloaded, and saw it return.
- Live browser: Alt+H armed only chart 0; charts 1-3 remained inactive with
  default cursors.
- Removed the SPY test drawing and confirmed the persisted count returned to 0.
- Final run check: API `status=connected`, IBKR `connected=true` /
  `session=ready`, 21 Gappers, and frontend HTTP 200.

## Follow-ups

D-004 tracks a pre-existing test-isolation bug found during verification:
`vite-nova-start-api.test.ts` uses the live `start-api.lock` path. The first
full-suite run collided with the running Vite server; after cleanup, the retry
passed all 835 tests.

D-005 tracks the separate API lifecycle issue found in the final run check: an
aborted terminal left its Python child active but no longer listening. The
orphan was safely removed and Nova was restarted; prevention needs a focused
process-supervision change.

## Keywords

chart drawings, dropdown, Trendline, Extended Line, Ray, Horizontal Ray,
Alt hotkeys, focused pane, ADR 015
