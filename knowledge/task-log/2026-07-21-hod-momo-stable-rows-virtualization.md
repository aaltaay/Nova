# 2026-07-21 — HOD Momo stable rows + virtualized table

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo (frontend UI)
- **Related:** `CHANGELOG.md` 2026-07-21 "HOD Momo rows pinned to first-catch time + true virtualized table" · `PROBLEM_LOG.md` 2026-07-21 "HOD Momo rows jump position and re-stamp their time on every re-fire"

## Task

User reported HOD Momo/Running Up rows "are not coming like a record… they're moving, they're just getting re-ordered," and expected each row to be a permanent, timestamp-anchored record created once when a symbol is first caught by a strategy gate. Follow-up: given the table will accumulate thousands of alerts per session, how would rendering avoid the browser lag the user had previously hit with unbounded-growth scrolling lists.

## Goal

1. A collapsed row's position and displayed time never move/change after it is first caught, regardless of how many times that ticker re-fires later.
2. The alert table's mounted DOM size stays flat (bounded) whether the session has 50 or 50,000 alerts, using continuous scroll (not click-through pagination — user's explicit preference).

## Why it mattered

Visually, re-ordering makes the scanner feel untrustworthy as a "log" — traders scanning for the earliest catches can't rely on row position once anything re-fires. Separately, the user had previously experienced real browser lag from an unbounded-growth list pattern elsewhere in the app and wanted confirmation this table wouldn't repeat it once alert volume scales to "thousands of hits" in a session.

## What we changed

- `frontend/src/hod_momo/collapseAlertsBySymbol.ts`: after the existing tag/burst-badge merge pass, added a second pass that finds each ticker's oldest ("first catch") occurrence in the full-session `alerts` array and overrides the collapsed row's `id`/`timestamp`/`created_ts` with it; final rows are sorted by that anchor descending instead of by walk-encounter order.
- `frontend/src/hod_momo/HodMomoAlertTable.tsx`: replaced the `renderedCount` batch-append-on-scroll state machine with a pure `computeVisibleRowRange(scrollTop, total, rowHeight, viewportHeight, overscan)` helper and two spacer `<tr>`s, so only the visible viewport + overscan is ever mounted.
- `frontend/src/hod_momo/HodMomoAlertRow.tsx` + `hodMomo.css`: capped inline strategy pills to `HOD_MOMO_MAX_INLINE_STRATEGY_PILLS` (with a "+N" overflow chip, full list still in the tooltip) and made row height fixed instead of `height: auto`, which the fixed-height windowing math requires.
- `frontend/src/constantGroups/chart_api.ts`: added `HOD_MOMO_OVERSCAN_ROWS`, `HOD_MOMO_MAX_INLINE_STRATEGY_PILLS`; removed the now-unused `HOD_MOMO_RENDER_BATCH_SIZE` / `HOD_MOMO_LOAD_MORE_THRESHOLD_PX`.
- Tests: rewrote `collapseAlertsBySymbol.test.ts` cases that had encoded the old (buggy) ordering as the expected behavior; added `HodMomoAlertTable.test.ts` for the windowing helper and a new `HodMomoAlertTable.render.test.tsx` that mounts the real component with 5,000 synthetic alerts and asserts mounted-row count stays bounded before and after a deep scroll.

## How it works now

`today_alerts` on the backend has no TTL mid-session (confirmed via explore agent), so the full history is always present in the `alerts` array passed to `collapseAlertsBySymbol` on every render — there is no need for cross-render memory. A ticker's *first* fire is always its *last* occurrence when walking the newest-first array, so a single backward pass finds every ticker's anchor cheaply. Live snapshot fields (price/rvol/change%) still come from the newest fire per the pre-existing, intentional "newest alert supplies price/metrics" behavior — only identity/position/stamp changed.

For rendering, `HodMomoAlertTable` tracks `scrollTop` in state and derives `{startIndex, endIndex, topSpacerPx, bottomSpacerPx}` from it plus the fixed `HOD_MOMO_ROW_HEIGHT_PX`/`HOD_MOMO_VISIBLE_ROWS`/`HOD_MOMO_OVERSCAN_ROWS` constants. It renders `alerts.slice(startIndex, endIndex)` (≈54 rows max) between two spacer rows sized in pixels so the scrollbar/scroll position still feel like a real N-row table. This only works because every row is guaranteed the same height — hence capping strategy pills to a single line instead of letting them stack vertically without bound.

## Why this approach

- **Pin to first-catch, not freeze the whole row:** considered freezing price/rvol/etc. at first catch too, but the pre-existing code comment ("Newest alert supplies price/metrics") signals that was an intentional design choice for a momentum scanner (you want current price on a still-hot symbol). The user's complaint was specifically about *position and stamp* instability ("moving," "re-ordered"), so only those fields were pinned; asked the user via `AskQuestion` to confirm this split but the question was cancelled before an answer — documented as the chosen default with an explicit callout in the plan so it's easy to revisit if wrong.
- **True fixed-window virtualization over pagination:** user was directly asked (`AskQuestion`) to choose between continuous virtualized scroll vs click-through pagination and explicitly chose virtualization ("windowing") to preserve the live-feed feel while keeping DOM bounded.
- **Fixed-height windowing over variable-height/measured virtualization:** the table already assumed a fixed `HOD_MOMO_ROW_HEIGHT_PX` for viewport sizing before this change; a measured/variable-height virtualizer (à la `react-window`'s `VariableSizeList`) would be significantly more code for a table whose only source of height variance (stacked strategy pills) was itself removable with a small CSS/JSX change. Capping pills to one line and enforcing a fixed row height keeps the windowing math exact (no reflow/remeasure step) and avoids adding a new dependency for a single-consumer table.
- **No new dependency:** row-count and alert volume here (hundreds to a few thousand per session) don't yet justify pulling in `react-window`/`react-virtual`; a ~35-line pure helper function is easier to unit-test and audit than wiring a third-party virtualizer into this table's existing markup.

## Verification

- `npx vitest run src/hod_momo` — all HOD Momo unit/component tests green, including 2 new files (`HodMomoAlertTable.test.ts` windowing-math tests, `HodMomoAlertTable.render.test.tsx` 5,000-row mounted-DOM-bound test) and rewritten `collapseAlertsBySymbol.test.ts` cases.
- `npx vitest run` (full frontend suite) — 98 files / 412 tests passed.
- `npm run build` — `tsc -b && vite build` clean, no TypeScript errors from removed exports.
- `npx eslint` on all changed files — clean.
- Live browser check (`agent-browser`) against the running dev server with a real IBKR-connected session (337 live HOD Momo alerts): confirmed exactly 42 rows mounted at `scrollTop=0` (matches `30 visible + 12 overscan` math), scrolling near the end of a 47-row filtered set mounted 41 rows (correctly bounded by remaining total, not the full 337), no new console errors, rows sorted newest-catch-first with intact "(N in Xsec)" burst badges.

## Follow-ups

- If the user later wants the whole row (price/rvol/volume/change%) frozen at first catch instead of live-updating, that's a small follow-up to the same override block in `collapseAlertsBySymbol.ts` — flagged in `CHANGELOG.md` / the plan, not implemented here since it wasn't confirmed.
- `RunningUpTab.tsx` shares `collapseAlertsBySymbol`/`HodMomoAlertTable`, so it inherited both fixes automatically — no separate change needed there.

## Keywords

HOD Momo, collapseAlertsBySymbol, row reorder, timestamp, first catch, virtualization, computeVisibleRowRange, windowing, DOM bound, infinite scroll, strategy pills, overscan
