# 2026-08-28 -- Chart VWAP starts at premarket 04:00

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / chart UI (continuity-only; no specialist hop)
- **Related:** `CHANGELOG.md` 2026-08-28 -- Chart VWAP starts at 04:00 ET premarket; `PROBLEM_LOG.md` 2026-08-28 -- Premarket VWAP was 09:30-only; `DEFERRED_LOG.md` D-007

## Task

Operator said premarket VWAP was skipped and they need it.

## Goal

The orange line paints from 04:00 ET and includes premarket volume, without bringing back the leftover-to-open diagonal.

## Why it mattered

Gappers trade the 04:00-09:30 tape. A 09:30-only VWAP is blank for the whole morning, then jumps in at the bell. On AEMD that ignored 15.0 million shares.

## What we changed

- `CHART_VWAP_SESSION_START_SEC` now uses `SESSION_PREMARKET_START_MIN_ET` (04:00)
- Tests and `tools/vwap_probe.py` expect the line to start at 04:00; 09:30 is the what-if

## How it works now

One session VWAP from 04:00 to 16:00 on the newest ET day. Premarket counts. After 16:00 the close value still carries. Yesterday leftover still does not connect across midnight.

## Why this approach

Reuse the existing premarket-open constant instead of a second 04:00 literal. Keep 16:00 as the stop -- the ask was premarket, not after-hours accumulation. Keep latest-day + whitespace so the 241-minute 23:59-to-04:00 hole cannot become a new diagonal.

Rejected a second "RTH VWAP" overlay. One line is the decision level; the probe already prints the 09:30 what-if if someone wants to compare.

## Verification

- `npx vitest run src/chart src/chartIndicators.test.ts` -- 18 files / 138 passed
- `py -3 -m pytest tools/test_vwap_probe.py -q` -- 4 passed
- Live `py -3 tools/vwap_probe.py AEMD`: first painted $3.51 at 04:00, last $3.109 at 10:03; RTH-only $3.088

## Follow-ups

Hard-refresh the AEMD 1Min pane if HMR leaves the old 09:30 line. After-hours (16:00-20:00) stays frozen on purpose -- platform mismatch vs Webull/DAS is D-007; do not change paint until a live Webull compare.

## Keywords

vwap, premarket, 04:00, session start, AEMD
