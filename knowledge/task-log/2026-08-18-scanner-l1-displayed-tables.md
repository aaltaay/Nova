# 2026-08-18 — Scanner L1 follows every displayed table

- **Status:** completed
- **Agents:** parent (took over a failed investigation)
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-18 (Scanner L1 follows every displayed table) · `PROBLEM_LOG.md` 2026-08-18 (whole scanner column froze) · ADR 008

## Task

The user still saw frozen Gainers prices on the live desk after a previous session
claimed the issue fixed. Diagnose from the current symptom without assuming the
prior root cause, and ship an architectural fix rather than a patch.

## Goal

Reproduce what the user sees in the browser, name the real root cause with
evidence from this session, fix it in the correct module, and prove the fix on
the same surface the user watches.

## Why it mattered

The scanner price column is the desk's primary read on live movers. It was
silently dead -- not slow, not partially stale, but **zero** price updates -- with
`l1_error: null` and an integrity check that still reported `pass`. A trader
cannot tell a frozen feed from a quiet tape, so this is a trust-destroying
failure on a live trading surface. The prior session had also spent a day
chasing IB historical pacing, so the wrong-cause cost was already high.

## What we changed

- `backend/scanner_tab_registry.py` -- per-client **set** of displayed tables
  (`set_tabs`), `get_active_tables()` union ordered by client demand.
  `set_tab` / `get_dominant_tab` kept as thin compat wrappers.
- `backend/ibkr/scanner_l1.py` -- `_active_tab_symbols: set[str]` became
  `_active_tab_tables: dict[str, str]` (symbol -> owning table).
  `_collect_tab_symbols` builds the ordered union + ownership map.
  `flush_loop` groups pending ticks by table and pushes one `price_patch` per
  table. `subscription.error` is set when a displayed table has rows but
  streams nothing.
- `backend/scanner_push.py` -- accepts `tabs: [...]`, replies with `tables`.
- `backend/app_lifespan.py` -- reconcile loop takes `get_active_tables`.
- `frontend/src/hooks/useScannerPriceStream.ts` -- `activeTabs`, exported
  `tabHints()`, sends `tabs`.
- `frontend/src/scanner/ScannerDataContext.tsx` -- separate main / dock slots
  composed into `activeTabs`.
- `frontend/src/hod_momo/HodMomoDock.tsx` -- declares the dock's table in an
  effect (mount included) instead of only on click.

## How it works now

The invariant is: **Nova streams IBKR L1 for every scanner table currently on
screen, and each price patch is tagged with the table that asked for it.**

A client sends the full set of tables it renders. The backend unions those sets
across clients, fills the active-tab budget from the most-demanded table first,
and records which table owns each symbol. A frozen table contributes no symbols
(ADR 008 unchanged) but no longer zeroes anything else. `flush_loop` can emit
patches for two tables in the same flush without cross-tagging, which is what
makes "main tab + dock showing different tables" expressible at all.

## Why this approach

The bug was a **contract** defect, not a bad value. A single dominant-tab string
cannot represent "main = Gappers (frozen) + dock = Gainers (live)", so any fix
that keeps one string is a guess about which table the user cares about.

Rejected alternatives:

- **Make `symbols_for_tab` fall back to a live table when the requested one is
  frozen.** Violates ADR 008 in spirit (the backend would stream a table nobody
  asked for) and still cannot serve two tables at once.
- **Change `DEFAULT_ACTIVE_TAB` to a live table, or persist `activeTab`.** Fixes
  only the reload path. Leaves the dock case and the multi-window majority-vote
  starvation intact -- exactly the "patch, not architecture" the user rejected.
- **Keep one hint but broadcast every pending tick untagged.** This is the bug
  ADR 008 was written to kill: HOD-pool ticks leaking into frozen rows.

The chosen shape also fails loud. The original defect survived a day because a
total feed outage produced `l1_error: null` and a passing `scanner_l1_stream`
check, so the honest-error branch matters as much as the union.

Deliberately left alone: `plan_stream_symbols` stays a pure symbol-list planner
(its existing tests keep passing) -- ownership mapping is assembled by the
caller, so the planner did not need to learn about tables.

## Verification

- `py -3 -m pytest backend/tests -q` -> **1209 passed** (from repo root; the one
  pre-existing `tools` import error only appears when run from `backend/`).
- Red-first: 6 new `test_scanner_tab_registry.py` tests plus
  `test_frozen_requested_table_does_not_zero_the_other_live_table`,
  `test_no_requested_table_streams_nothing`,
  `test_flush_emits_one_patch_per_displayed_table` all failed before the
  implementation (`AttributeError: no attribute 'set_tabs'`, etc.).
- `npx vitest run` on the touched specs -> 24 passed; `npx tsc --noEmit` clean.
- **Before fix, live:** `/api/integrity` `l1_active_tab: 0`, `l1_active_hod: 40`,
  50 gainer rows, gainers cache 199s old. `/ws/scanner` listener:
  `dominant_tab=gappers`, **0 patches in 12s**, reproduced after three reloads.
  Clicking Gainers flipped it to `active_tab=38`, 33 patches / 79 price changes
  in 14s -- clean isolation of the hint as the cause.
- **After fix, live** (API restarted onto the new build): `l1_active_tab` 49,
  gainers cache 3s, `scanner_l1_age_sec` 2.9s, HOD ticks 5s (was 199s stale).
- **Browser (localhost:5173):** Gainers column moved across two screenshots 25s
  apart -- PFSA $16.98 -> $17.37, IPST $19.80 -> $19.95, CDTG +122.95% ->
  +120.00%, with up/down flash styling.
- **Multi-window regression:** 2 WS clients on `gappers` + 1 on `gainers` ->
  `tables=['gappers','gainers']`, 38 gainers patches / 88 price changes across
  43 symbols. Old majority-vote arbitration would have returned `gappers` and
  streamed nothing for the Gainers window.

## Follow-ups

- `IBKR_L1_ACTIVE_TAB_MAX` (50) is now a **total** across displayed tables.
  Premarket with Gappers and Gainers both live and both on screen will share it
  and report `rejected`. Raise it (budget is 95) if that becomes real.
- The main `activeTab` is still not persisted, so a reload lands on Gappers. The
  scanner dock mode also appears to be reset by an async default shortly after
  mount -- worth a look, since it silently changes what is displayed.
- `l1_active_hod` reads ~1 whenever the active tab holds the HOD names, because
  `plan_stream_symbols` dedupes the overlap out of the HOD owner list. The
  symbols still stream (tab-owned), but the counter misleads any future triage.
- Not reproduced this session: why HOD-owned L1 went 199s without a tick while
  `active_tab` was 0. It recovered with the fix; if it returns, correlate
  `scanner_l1_age_sec` against `l1_active_hod` before blaming pacing.

## Keywords

gainers frozen, price_patch, l1_active_tab 0, dominant tab, set_active_tab tabs,
displayed tables union, scanner dock, ADR 008, frozen table starves L1,
multi-window starvation, fail loud, market-feed
