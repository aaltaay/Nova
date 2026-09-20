# 2026-08-04 -- HOD Momo sort by TIME not emit lag

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo
- **Related:** `CHANGELOG.md` 2026-08-04 -- HOD Momo rows sort by TIME · `PROBLEM_LOG.md` 2026-08-04 -- HOD Momo TIME order wrong

## Task

Explain/fix HOD Momo list order where AEHG (earlier TIME) sat above PTIR/PLTU (later TIME) and IPCX (first-in) was at the bottom.

## Goal

TIME column order matches row order (newest first-catch on top); rows stay pinned to first trade catch except burst merge.

## Why it mattered

Operators read TIME as first-in truth. Shuffle vs that clock looks like alerts replacing each other and breaks trust in the scanner.

## What we changed

- `alertDisplayUnix` prefers trade `timestamp` over delayed `created_ts`.
- First-catch pin = earliest trade TIME per ticker.
- Sort + burst gap use the same clock.
- Regression test with live AEHG/PTIR/PLTU/IPCX skew numbers.

## How it works now

One row per symbol. TIME and list position use first print catch (newest first-catch on top). Later re-fires update price/tags in place; `(N in Xs)` only inside the burst window. `created_ts` remains emit/wall for backend consolidation.

## Why this approach



## Verification

`npx vitest run src/hod_momo/collapseAlertsBySymbol.test.ts src/hod_momo/collapseConsecutiveTickerAlerts.test.ts` -- 9 passed. Live API confirmed AEHG created_ts > PTIR while timestamp was earlier.

## Follow-ups

Optional: when a later re-fire is outside the burst window, preserve the first-catch burst badge counts (separate from sort).

## Keywords

HOD Momo, TIME, created_ts, consolidation, sort, AEHG, first-catch
