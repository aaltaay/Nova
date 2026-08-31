# 2026-08-26 -- Previous-day Gappers empty snapshot and live closed copy

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed (scanner history snapshots; continuity-only for this session)
- **Related:** `CHANGELOG.md` 2026-08-26 previous-day Gappers · `PROBLEM_LOG.md` 2026-08-26 Previous-day Gappers empty snapshot + live closed copy · `deferred_log=none`

## Task

Explain why picking a previous day in the scanner date picker showed an empty Gappers table with live "Market is closed" copy, then stop that from happening again.

## Goal

History view tells the truth about that day's file. A later empty projection cannot wipe a day's gappers JSON. Empty dates drop out of the picker. Aug 24's wiped file is not reconstructed.

## Why it mattered

The operator thought previous-day results were broken or that the market-closed overlay was hiding the list. The list for Aug 24 was actually gone on disk, and the overlay was tonight's live session leaking into history.

## What we changed

- `cache.save_*_snapshot` refuses empty payloads
- `list_history_dates` skips empty snapshots
- `load_snapshot_for_date("movers")` composes `gainers-` + `losers-` files
- `gapper_view` does not persist an empty projection
- `freeze_table` persists the frozen roster when it still has rows (HTTP-loop hop)
- History `EmptyState` names the date; live freeze badge is hidden while `historyDate` is set

## How it works now

Gappers history is the last non-empty dated JSON for that session day, usually the 09:30 freeze. Picking a past date loads that file and does not reuse live `mode` or `tableMeta`. Days whose file is `[]` do not appear in the picker.

## Why this approach

Refusing empty writes is smaller and safer than trying to guess whether a zero projection is "real no gappers" vs a names-first unpriced wipe. Live UI can still show an empty Gappers table during premarket; only the day's history file is protected. Rebuilding Aug 24 from archive/tape was rejected: those cold files are July bars, not scanner rosters.

Rejected: showing live rows under a history banner (lies about the date). Rejected: keeping empty dates in the picker with only a better message (operator would keep picking dead days).

## Verification

- `py -3 -m pytest backend/tests/test_scanner_roster_persist.py backend/tests/test_scanner_session_adr008.py backend/tests/test_scan_runners.py backend/tests/test_scanner_runners_afterhours.py backend/tests/test_cache_error_visibility.py backend/tests/test_scan_large_cap_route.py -q`
- `npx vitest run src/components/EmptyState.test.tsx` (frontend)
- `npm run build` (frontend, exit 0)
- Live API after restart: `connected=true session=ready`; history dates omit 2026-08-24; Aug 25 gappers=26
- Browser: picker has no Mon Aug 24; Tue Aug 25 shows Viewing 2026-08-25, WVVIP, 26 Gappers, no "Market is closed" copy

## Follow-ups

Aug 24 / Aug 18 / Aug 5 gappers files stay empty on disk. Do not reopen to "recover" them without a real second source.

## Keywords

historyDate, gappers snapshot, previous day, Market is closed, save_gapper_snapshot, gapper_view, names-first
