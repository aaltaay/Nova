# Problem log (agent-maintained)

This file is a **shared memory** of errors fixed and problems identified in this repo. Agents should **search here first** (repo search or open this file) when symptoms look familiar.

## How agents update this file

1. **When:** After you fix a failing build, test, linter error, runtime error, or incorrect behavior; or after you identify a non-obvious root cause worth remembering.
2. **Where:** Prepend a new `##` section **immediately below** the `<!-- ENTRIES_START -->` marker (newest entries at the top).
3. **Keep it short:** A few lines per field is enough.

Entry template (copy and fill in):

```markdown
## YYYY-MM-DD — Short descriptive title

- **Symptom:** What failed or misbehaved (error text, stack trace one-liner, or user-visible behavior).
- **Cause:** Root cause in plain language.
- **Fix:** What changed (conceptually; file paths if helpful).
- **Keywords:** comma, separated, terms, for, search
```

<!-- ENTRIES_START -->

## 2026-07-16 — Swallowed exceptions hid IBKR/cache/Nova OS failures

- **Symptom:** `maintainer_checks.py` reported 11 `SWALLOWED_EXCEPTION` sites in production/tool code (`cache`, `scanner_push`, `tape_stream`, `ticks`, `nova_os/events`, `create_nova_agent`); queue-full and cleanup paths failed silently.
- **Cause:** Defensive `except …: pass` blocks (and a redundant outer swallow around `notify_nova_os_event`, which already logs internally) discarded real OSError/queue-pressure/unsubscribe failures with no log line.
- **Fix:** Narrow exception types, log at debug/warning, drop-oldest on `QueueFull` with visibility; Nova OS receipt notify uses ImportError-only guard; depth/HOD queue leftovers aligned. Regression tests added for cache cleanup, tape/depth queue drop, and Nova OS receipt path.
- **Keywords:** swallowed exception, maintainer_checks, error visibility, Phase 11, QueueFull, tape_stream, cache cleanup, nova_os events

## 2026-07-16 — HOD module extraction exposed stale facade/state aliases

- **Symptom:** HOD tests and consumers patched/read mutable globals on `hod_momo.py`; after extraction, a facade-level monkeypatch did not affect the focused module that held the real callable, and rebinding lists/dicts could leave consumers on stale objects.
- **Cause:** The monolith reassigned `_configs`, `_master`, `_today_alerts`, queues, and session collections directly. Imports/tests depended on module aliases rather than one explicit owner resolved at use time.
- **Fix:** Added `HodMomoState` as the sole owner; all focused modules call `get_state()` and tests patch/replace that owner. Added characterization for persistence, session rollover, queues, WebSocket clients, surge state, consolidation, and config/reset paths.
- **Keywords:** HOD Momo, stale alias, facade monkeypatch, state rebinding, session rollover, persistence, websocket clients, broadcast queue, Phase 10

## 2026-07-16 — Wedged API on port 8000 shows Backend unreachable

- **Symptom:** UI header: Disconnected — Backend unreachable; HOD banner: Integrity unreachable Failed to fetch; health HTTP timed out even though `netstat` showed `LISTENING` on `127.0.0.1:8000`.
- **Cause:** Orphan/wedged `python3.13` (PID listening since overnight) accepted TCP but did not serve `/api/health`. New `run_api.py` failed with WinError 10013 (port busy / access denied), so a second API never bound.
- **Fix:** `Stop-NovaPorts.ps1` for 8000 then restart API. Added header **Start API** button (Vite/Electron). Added outage flags: `API_WEDGED` (health timeout) vs `API_DOWN` (nothing listening); console `[Nova][API_FLAG]`.
- **Keywords:** Backend unreachable, Integrity unreachable, WinError 10013, port 8000, wedged uvicorn, Start API, API_WEDGED, API_DOWN, API_FLAG

## 2026-07-16 — Memory Markdown in `.cursor/agents/` discovered as callable agents

- **Symptom:** `*-memory.md` files under `.cursor/agents/` appeared alongside real agent prompts as if they were invocable Cursor agents, and status facts were duplicated across prompts, memories, and canvases.
- **Cause:** Cursor discovers every `*.md` in `.cursor/agents/` as an agent prompt; memory documents were co-located with prompts and there was no versioned registry/contract separating prompts, memory, and generated dashboards.
- **Fix:** Moved memories to `.cursor/agent-memory/`; added `.cursor/agent-system/contract.json` + `registry.json`; normalized the four agents; added `tools/agent_contract.py` (blocking), `create_nova_agent.py`, `sync_agent_surfaces.py`, specialist routing, and a fail-open lifecycle hook.
- **Keywords:** agent lifecycle, agent-memory, registry, contract, subagentStop, canvas snapshot, create_nova_agent

## 2026-07-16 — Ghost HOD integrity/surge-seed docs vs missing runtime

- **Symptom:** CHANGELOG/constants/CSS claimed fail-loud integrity + Squeeze bar seeding, but `hod_momo_integrity.py`, `integrity_live.py`, `hod_momo_surge_seed.py`, CLI, routes, and UI banner did not exist at master `d3a8985`. Live HOD still cold-started Squeeze and cycled slowly across a large watch set.
- **Cause:** Prior HOD work landed documentation/constants without the runtime modules (or was lost during branch/stash churn); agents treated docs as shipped.
- **Fix:** Implemented integrity evaluators + live builders + CLI/banner; IBKR surge seed loop; capacity-bounded active set with fair reprice batching; uncovered symbols explicit. Corrected changelog with a real ship entry.
- **Keywords:** HOD Momo, integrity, surge seed, active set, reqTickersAsync, HKIT, ghost docs, Warrior parity

## 2026-07-16 — Alert channel Test fire sent empty Discord embeds


- **Symptom:** POST `/api/alerts/test` (and Settings “Test”) delivered Discord embeds with empty `description`; Telegram got a JSON dump instead of the test sentence.
- **Cause:** `format_event_payload` only handled `hod_momo` / `nova_os`. Test events (`type=test` + `text=…`) fell through without copying `text`, so Discord used `payload.get("text", "")` → `""`.
- **Fix:** Formatters now prefer `event["text"]` for test/unknown events; Discord titles distinguish Test vs HOD vs Nova OS. Also sanitized Discord/Telegram/webhook exception return strings so webhook URLs / bot tokens never leak into `/api/alerts/status`.
- **Keywords:** Phase D, alerts, formatters, Discord embed, test channel, empty description, secret redact, telegram

## 2026-07-16 — Tab bar labels mashed (HOD Momo / Trading overlap)

- **Symptom:** Top nav showed overlapping unreadable tab text (e.g. HOD Momo and Trading painted on top of each other) when many modules were visible.
- **Cause:** `.tab` used `flex: 1 1 0` + `min-width: 0`, so equal-width flex items shrank below label width while `white-space: nowrap` let text bleed into neighbors.
- **Fix:** `.tab` → `flex: 1 0 auto` (grow into spare space, never shrink below content); drop `min-width: 0`. Narrow viewports still scroll via `.tab-bar-scroll`.
- **Keywords:** tab-bar, TabNav, overlap, HOD Momo, Trading, flex shrink, min-width, label bleed

## 2026-07-15 — Uncommitted Stock View CSS lost during phase automation

- **Symptom:** Playwright baseline failed: `documentElement must not page-scroll on Stock View`. Working tree no longer had `body:has(.container--ticker-detail)` / portal flex-fill rules even though `TickerChart.tsx` still had `measureChartFillHeight`.
- **Cause:** Stock View viewport-lock CSS lived only as uncommitted `index.css` edits. A phase subagent discarded those working-tree changes (checkout/resolve) while committing its own `index.css` additions — TS half survived, CSS half vanished.
- **Fix:** Re-apply viewport-lock + chart-fill CSS from the prior session; verify Playwright/Vitest/build; commit CSS together with dangling chart/nav work immediately. Lesson: never leave a verified fix uncommitted while parallel agents touch the same files — commit or stash first.
- **Keywords:** Stock View, index.css, uncommitted, phase agent, discarded, 100dvh, page scroll, Playwright baseline

## 2026-07-15 — Stock View double-click opened a browser tab instead of a window

- **Symptom:** Double-clicking a ticker opened Stock View in a new browser tab, not a detached OS window.
- **Cause:** `window.open(url, '_blank')` with no feature string is treated as “open tab” by Chrome/Edge. Only size/`popup` features request a real window.
- **Fix:** Pass `STOCK_VIEW_WINDOW_FEATURES` (`popup=yes`, width/height, …) and a named target `nova-stock-SYMBOL`; still clear `opener` (no `noopener` flag).
- **Keywords:** Stock View, detach, window.open, popup=yes, new tab, double-click

## 2026-07-15 — Stock View chart gaps + page scroll

- **Symptom:** Large empty black bands between the top chart row (1m/5m) and bottom row (full day/15m); Stock View required vertical page scrolling to reach the trade bar.
- **Cause:** (1) `.chart-portal-slot` / `.chart-portal-host` were `display:block` without flex fill, so grid cells did not pass height to `.chart-body`. Charts stayed at `CHART_HEIGHT_GRID` (180px) inside taller cells. (2) Shell used `min-height: 100vh` instead of a locked `100dvh` flex column, and `#root` was not part of the height chain, so content grew past the viewport.
- **Fix:** Viewport-locked Stock View flex shell (`body` / `#root` / `.container--ticker-detail`); portal slot/host + grid card body `flex: 1 1 0`; `measureChartFillHeight` + ResizeObserver on card/host; compact non-sticky trade bar with `max-height: 22vh`.
- **Keywords:** Stock View, chart-grid, CHART_HEIGHT_GRID, portal-host, fillParentHeight, 100dvh, page scroll, ATAI

## 2026-07-15 — tsc -b failed on Vitest ownership tests importing node:fs

- **Symptom:** `npm run build` (`tsc -b`) failed with `TS2591: Cannot find name 'node:fs'` on `tapeFeed.test.ts` / `modules.ownership.test.ts`.
- **Cause:** `tsconfig.app.json` includes all of `src/` with `types: ["vite/client"]` only — Vitest unit tests that import Node builtins are not part of the app compile graph.
- **Fix:** Exclude `src/**/*.test.ts(x)` from `tsconfig.app.json` so Vitest owns those files; app build stays browser-typed.
- **Keywords:** tsc, vitest, node:fs, tsconfig.app.json, exclude, ownership test


## 2026-07-15 — Vitest loaded Playwright e2e specs and failed the unit suite

- **Symptom:** `npx vitest run` failed on `e2e/baseline.spec.ts` with `Playwright Test did not expect test.describe() to be called here`.
- **Cause:** Vitest default include picks up `*.spec.ts`; Playwright specs under `frontend/e2e/` were executed as Vitest files.
- **Fix:** Exclude `**/e2e/**` in `vite.config.ts` `test.exclude`; import `defineConfig` from `vitest/config` so the `test` key type-checks under `tsc -b`.
- **Keywords:** vitest, playwright, e2e, baseline.spec.ts, test.exclude, vitest/config


## 2026-07-15 — Double-click Stock View only worked on scanners / HOD, not Journal / Trading / Debug

- **Symptom:** Double-clicking a HOD (or scanner) row opened Stock View, but Journal trades, Automation staged/open, Trading positions/orders, Decision cards, and HOD debug tables ignored the second click.
- **Cause:** Those surfaces still rendered plain `<tr>` / plain buttons and never received `onOpenTrading` / `selectedSymbol` props from their parents.
- **Fix:** Wrapped symbol rows in `SelectableTableRow` (Decision cards use the same click-vs-double helper), threaded select/open props from `DashboardPage` → Trading / Watchlist / HOD debug, and extracted `ExecutorTables` + `HodMomoDebugTables` so parents stay under file-size limits. Action cells `stopPropagation`.
- **Keywords:** double-click, Stock View, SelectableTableRow, JournalPanel, ExecutorTables, PositionsPanel, DecisionPanel, HodMomoDebugTables, onOpenTrading

## 2026-07-15 — HOD Momo “virtualized” table mounted all 6,603 rows in the populated browser

- **Symptom:** With the user's live HOD Momo dataset at 6,630 alerts, opening the tab remained crash-level slow and produced an effectively endless document. Browser measurement showed 6,603 mounted alert `<tr>` nodes, 137,325 total DOM nodes, a 212,564px-tall `.hod-table-wrapper`, and a 212,971px document.
- **Cause:** `@tanstack/react-virtual` observed `.hod-table-wrapper`, but that element was `flex: 1` in a parent without a constraining height and retained its intrinsic table height. The wrapper expanded to the full table, so the virtualizer considered the full dataset visible and returned every row. Previous verification used an empty alert list, so it could not expose this failure.
- **Fix:** Removed the virtualizer from `HodMomoAlertTable` and made the mounting contract deterministic: render 40 rows initially and exactly 40 more per distinct internal-scroller bottom reach. The wrapper is fixed at 532px with `flex: 0 0 auto`, `min-height: 0`, contained overscroll, and a bottom-event latch.
- **Verified by:** The same populated browser session now reports 40 mounted rows, 964 total DOM nodes, and a 532px wrapper with 6,630 alerts loaded; one bottom reach produces exactly 80 rows and 1,792 DOM nodes while document height stays unchanged. HOD tab open-to-two-animation-frames measured 52.2ms. Browser console is clean; frontend build and all 75 tests pass.
- **Keywords:** HOD Momo, virtualization, 6603 rows, 137325 DOM nodes, flex intrinsic height, endless scroll, render 40, incremental rendering, populated browser verification

## 2026-07-15 — HOD Momo tab still crash-level laggy after three prior "fixes" — every alert was silently duplicated in frontend state

- **Symptom:** User reported the HOD Momo tab was so laggy that opening it felt like it would crash the browser, despite this having been "fixed" repeatedly (virtualization, alert-persistence throttling, batched live prepends — see the three 2026-07-14/15 entries below titled "HOD Momo freezes" / "HOD Momo UI lag"). Browser console (`npx agent-browser console`) showed a continuous flood of React `"Encountered two children with the same key"` errors, one per HOD alert id, for nearly every visible row.
- **Cause:** All three prior fixes addressed *rendering cost* (row virtualization, batching, save throttling) but never looked at *data integrity* of the `alerts` array itself. `frontend/src/hod_momo/useHodMomoStream.ts`'s WebSocket handlers only guarded on a single shared `mountedRef.current` boolean. React 18 `<StrictMode>` (enabled in `main.tsx`, active for every `npm run dev` session) deliberately mounts → cleans up → remounts effects in development: the cleanup set `mountedRef.current = false` and called `ws.close()` on the first socket, but the immediately-following remount flipped `mountedRef.current` back to `true` and opened a second socket *before* the first socket's close handshake and any in-flight messages had fully drained. Any 'alert' broadcast the stale first socket received during that overlap was no longer blocked by the (now-true) `mountedRef` check, so it got pushed into `pendingRef`/state a second time — identical `id` (backend `alert_id = f"{int(ts*1000)}-{symbol}-{strategy_id}"`), identical payload. Verified backend-side: `backend/.cache/hod-momo-2026-07-15.json` had **zero** duplicate ids among 4097+ alerts — the corruption was 100% client-side. This is the exact "ignore events from a non-current WebSocket instance" anti-pattern the `single-market-data-feed.mdc` rule already mandated and other hooks (`useIbkrDepth`, `useIbkrTape`, `useTickerStream`) already implement — `useHodMomoStream` was simply never brought in line with that pattern when it was written, so every dev session doubled (or, after many hot-reloads across a long edit day, multiplied further) the in-memory alert list, and every duplicate-keyed row forced expensive/incorrect React reconciliation on every re-render, compounding as the day's alert count grew into the thousands.
- **Fix:** `useHodMomoStream.ts` now guards every WS handler on `wsRef.current === ws` (per-instance identity) in addition to `mountedRef`, and the cleanup explicitly nulls `onopen/onmessage/onerror/onclose` before calling `close()` so a lingering socket cannot fire into a torn-down instance. Added a persistent `seenIdsRef: Set<string>` (rebuilt only once, from the `initial` payload) so any duplicate `alert.id` — from this bug, a flaky reconnect, or a future backend re-send — is dropped in O(1) before ever reaching state, instead of doing an O(n) full-array rescan per incoming alert.
- **Verified by:** Live-tested against the running dev server with `agent-browser`: before the fix, clicking the tab produced hundreds of duplicate-key console errors within seconds; after the fix and a fresh reload, the tab was watched for 75+ seconds while live alerts grew from ~4097 to 4458 with **zero** console errors. `npm run build` and `npm run test` (73/73) both pass.
- **Keywords:** HOD Momo, duplicate key, React StrictMode, mount cleanup remount, useHodMomoStream, stale WebSocket instance, wsRef, mountedRef race, dedup, seenIdsRef, alert_id, single-market-data-feed, why fixes didn't stick

## 2026-07-15 — Nova OS event-time replay: decide() saw the whole day (hindsight); evening review scored outcome backward from close, not forward from decision

- **Symptom:** The Nova OS hardening audit's section 5 ("implement no-hindsight replay, rewind, ask, and review loop") named this an unimplemented gap. Reading `archive/replay.py::replay_day()` confirmed a concrete bug, not just a missing feature: it loaded every `bars_1m` row for the whole archived day into `by_symbol[sym]` (sorted ascending), then called `decide(candidate, bars, ...)` exactly once per symbol with that *entire* series — the candidate's `price`/`change_pct`/`volume` were built from `bars[-1]` (the day's close) and `bars[0]` (the day's open), and every gate that reads `bars` (`gate_setup`, `first_minute_volume`, `evaluate_setups`) saw the full day too. A "replay" whose decide() call can see the closing price before "deciding" is not a fair simulation of live decision quality — it is hindsight-biased by construction. `evening_review._outcome_for_decision()` had a second, independent bug: it computed `ref = bars[-(horizon_min+1)]` and `fwd = bars[-1]` — always the *last* bars of the whole day, regardless of when a decision supposedly fired, so "outcome N minutes after the decision" was actually "price N minutes before the close vs at the close," with no relationship to any real decision moment.
- **Cause:** `replay_day()` was written as "one decision per symbol per day" with no concept of an as-of point in time — there was no mechanism to slice a symbol's bars to only what existed at some earlier moment, so the whole day was the only option. `evening_review` inherited that same one-decision-per-day shape and, needing *some* timestamp to anchor its "N minutes after" window, fell back to the day's last bar, which is unrelated to when a decision actually happened.
- **Fix:** Added `archive/replay.py::slice_bars_as_of(bars, as_of_ts)` (bars with `ts <= as_of_ts` only) and a shared `_decide_snapshot()` helper used by both `replay_day(as_of_ts=...)`/`replay_at()` (single no-hindsight point-in-time decision) and new `walk_day()` (steps through a day in `ARCHIVE_REPLAY_WALK_STEP_MIN`-minute increments, calling decide() at each step with bars sliced to that step's own `as_of_ts` — the "rewind" timeline). `replay_day()` without `as_of_ts` keeps the old whole-day behavior only for backward compatibility with the existing CLI/route default, and its response now says `"hindsight": True` explicitly so nobody mistakes it for a fair test. `evening_review()` was rewritten on top of `walk_day()`: for each symbol it picks the first real (no-hindsight) BUY decision from the walk — or the final step's decision if none ever fired — then `_outcome_for_decision()` scores it by looking at bars strictly *after* that exact `as_of_ts`, finding the closest one to `as_of_ts + horizon_min*60`. Using bars *after* the decision to grade it is correct (that is how you check whether a decision paid off); the bug was letting decide() see those same bars *before* deciding, which no longer happens. New REST routes (`/api/archive/walk/{day}`, `/api/archive/review/{day}`, `/api/archive/ask`, plus `as_of` on the existing `/replay/{day}`) and CLI subcommands (`at`, `walk`) expose the fix; `ArchiveRewind.tsx` now drives a real scrubber off `/walk` instead of a single whole-day button.
- **Keywords:** hindsight bias, no-hindsight replay, lookahead, replay_day, decide() sees future bars, walk_day, replay_at, slice_bars_as_of, as_of_ts, evening_review, outcome scored backward from close, forward-looking grading vs decision-time information, Nova OS hardening section 5, rewind

## 2026-07-15 — Nova OS archive durability: silent missing-manifest skip + non-atomic cold writes + L2 never bridged

- **Symptom:** The Nova OS hardening audit's section 4 ("persist all feeds and prove crash-safe local/R2 durability") found: (a) `archive/r2.py::upload_day()` and `archive/restore.py::restore_day_to_temp()` both did `if not man_path.is_file(): continue` for a table's missing cold manifest — if `compact_day()` crashed after writing 4 of 5 table manifests, the day could still be marked `verified_remote: True` in R2 (or `ok: True` in a restore drill) as long as the tables that DID get manifests uploaded/restored cleanly; the missing table's data was silently gone with no failure signal. (b) `compact.py`'s `_write_jsonl()` opened the final path directly in `"w"` mode — a crash mid-write left a truncated file on disk while an *old* manifest (from a previous successful run, never rewritten because the crash happened before `write_manifest()`) still claimed the old, now-wrong, row_count/sha256 for it. (c) `archive/capture.py::record_l2_snapshot()` was an unwired, in-memory-only stub (no production caller — confirmed via repo-wide grep) capped at 10k rows and dropped on restart; the counter it bumped looked like evidence L2 depth was being durably captured, when in production nothing called it at all. L2 depth *was* actually being durably captured all along, just by a completely different, older subsystem (`l2/continuous.py` → `l2/db.py`) that the archive package's own P6 stub docstring referenced but never bridged into cold/R2.
- **Cause:** (a) `continue` was written to mean "nothing to upload for this table" instead of distinguishing "genuinely empty" (which `compact_day` always represents with a row_count=0 manifest) from "manifest never got written." (b)/(c) were both write-path integrity gaps: no atomic replace on the jsonl, and a real persistence mechanism (`l2/db.py`) that pre-dated the Nova OS archive package but was never connected to its cold-compaction/R2 pipeline.
- **Fix:** `archive/manifest.py::write_manifest()` and a new `archive/compact.py::write_jsonl_atomic()` (renamed from the old private `_write_jsonl`) now write to a sibling temp file, fsync, then `os.replace()` into the final path — a crash mid-write can never leave the final path holding partial content that doesn't match its manifest. `r2.py::upload_day()` and `restore.py::restore_day_to_temp()` now treat a missing manifest as an explicit `ok: False` failure entry (not a skip), and `upload_day()` additionally calls `manifest.verify_payload()` on the local file against the manifest's recorded sha256 immediately before uploading — a mismatch (stale/corrupted local file) is refused and never reaches R2. New `archive/l2_bridge.py` bridges `l2/db.py`'s `l2_snapshots`/`tape_trades` tables (ts-range queried per America/New_York calendar day, since that db has no `session_date` column) into the same checksummed-JSONL-manifest pattern, with its own R2 upload (`upload_l2_day`), verified index (`_r2_verified_l2.json`, deliberately separate from the primary index so a stalled L2 backup never falsely marks the bars/tape_ibkr day verified or vice versa), and restore drill (`restore_l2_day_to_temp`). Wired into `archive/scheduler.py::run_maintenance_once()` as a best-effort step per finished day (wrapped in its own try/except so an L2 failure never blocks the primary compaction). `capture.py`'s dead stub is left in place (still nothing calls it) but its docstring now explicitly redirects to `l2_bridge` so a future reader doesn't mistake it for the real capture path.
- **Keywords:** archive durability, missing manifest silent skip, upload_day, restore_day_to_temp, atomic write, os.replace, write_jsonl_atomic, l2_bridge, l2.db, l2_snapshots, tape_trades, R2 verified index, sha256 mismatch, Nova OS hardening section 4, persist all feeds

## 2026-07-15 — Nova OS mode-receipt split-brain + unsafe flatten/recovery

- **Symptom:** An audit of Nova OS P2–P7 found (a) every decide() receipt from the scanner and `/api/nova-os/decide*` claimed `mode: "signal"` and `would_execute: false` even while the operator had actually raised control mode to `confirm`/`auto_paper` and orders were staging/placing for real — the audit trail didn't match reality; (b) `flatten_positions()` could SELL after an unfilled parent was cancelled and could leave protective legs working after a position closed; (c) staged-ticket approval and auto_paper placement only checked safety gates once, not at the moment of action, so a kill switch or risk halt seconds later didn't stop an in-flight approval; (d) startup recovery ran before `ibkr.client.startup()` completed, so it always reported "ambiguous — can't verify" for every open position; (e) the loss policy used `consecutive_losses`, which an intervening win resets, instead of a same-day total.
- **Cause:** `strategy/setups_stream.py` and `routes/nova_os.py` hardcoded `mode=NOVA_OS_DEFAULT_MODE` into `decide()` calls instead of reading the real `control_mode.get_mode()`. `flatten_positions()`/`place_from_ticket()`/`staged_tickets.approve()` treated "mode was raised" or "ticket was staged" as a standing permission rather than re-validating at execution time. `app_lifespan.py` called `run_startup_recovery()` before the IBKR client finished connecting. `strategy/risk.py`'s `RiskState` had no independent daily-loss counter.
- **Fix:** Pass the real control mode through `setups_stream._scan_once()` and both `/api/nova-os/decide*` routes (also `record=False` there — they're polling endpoints). Extract `flatten_preview`/`flatten_positions` into `strategy/executor_flatten.py` with real-IBKR-position reconciliation and unconditional protective-leg cancellation. `place_from_ticket()` and `staged_tickets.approve()` re-check kill switch/mode/concurrency/gates/risk immediately before acting, with an explicit `placement_declined`/`approve_blocked` receipt per rejection reason; approval claims the ticket atomically via `dict.pop`. Reorder `app_lifespan.py` so IBKR startup completes before recovery/`risk.reconstruct_from_journal()` run. Add `RiskState.losses_today`, drive `codes.loss_policy_mode()` from it, and rebuild it from the trade journal on restart.
- **Keywords:** would_execute, mode split-brain, decide() hardcoded mode, flatten unsafe sell, staged ticket race, approve atomic, startup recovery ambiguous, consecutive_losses vs losses_today, Nova OS hardening, placement_declined receipt

## 2026-07-15 — Chart Loading stuck: setups_stream starved IBKR historical

- **Symptom:** Open-ticker chart stayed on "Loading…" for 20–30+ seconds (or until timeout) even with Gateway connected.
- **Cause:** `strategy/setups_stream` pulled IBKR `reqHistoricalData` for up to 15 symbols every 15s on the same socket/event loop as the chart. Requests queued; chart hit the 30s timeout while UI spun.
- **Fix:** `ibkr/historical_gate` serializes historical pulls and gives interactive chart priority; throttle setups under ibkr (top 3 / 60s / inter-symbol delay); shorten 1Min lookback to `1 D`; client abort at 25s so Loading cannot hang forever.
- **Keywords:** chart loading, IBKR historical, setups_stream, pacing, reqHistoricalData, TimeoutError, Loading

## 2026-07-15 — Exchange dropdown transparent (missing --card-bg token)

- **Symptom:** Filter Exchanges menu rendered with no background — checkboxes floated over the Settings form behind it.
- **Cause:** `.hod-filter-dropdown` used `var(--card-bg)` / `var(--hover-bg)`, but those CSS variables were never defined in `:root` (only `--panel-bg` existed), so the background resolved to transparent.
- **Fix:** Define `--card-bg: var(--panel-bg)` and `--hover-bg` in `:root`; point the filter dropdown at `--panel-bg` explicitly with a stronger shadow.
- **Keywords:** exchange filter, transparent dropdown, --card-bg, design tokens, Filter Exchanges

## 2026-07-15 — Chart maximize collided with app header; bars blanked then loaded late

- **Symptom:** Maximize chart → Nova header / Symbol Look Up mixed into chart toolbar; candlesticks missing then appeared much later.
- **Cause:** `.side-panel` `container-type: inline-size` made `position: fixed` relative to the panel, not the viewport. Chart `useEffect` listed `maximized` as a dependency, so toggle destroyed and recreated lightweight-charts (empty until refetch).
- **Fix:** Stable portal host reparented to `document.body` while maximized; remove `maximized` from chart create deps; resize in place; Escape to restore.
- **Keywords:** chart maximize, header overlap, container-type, position fixed, side-panel, createPortal, lightweight-charts remount

## 2026-07-15 — HOD Momo alerts wiped on every API restart after 4 AM ET

- **Symptom:** Full-day HOD list (~1000 alerts) shrank to ~90 after restarting the backend; UI scroll ended because the data was gone, not because of virtualization.
- **Cause:** `load_state()` loaded today's snapshot, then `_check_and_reset_session()` saw empty `_session_date` ≠ today and treated it as a rollover, setting `_today_alerts = []`. The next `_save_alerts` overwrote `hod-momo-YYYY-MM-DD.json` with the small new list.
- **Fix:** Initialize `_session_date` without clearing on first boot; archive prior-day alerts on real rollover; add explicit `DELETE /api/hod-momo/alerts` + Clear today UI.
- **Keywords:** HOD Momo, session rollover, restart wipe, persistence, load_state, _session_date, clear alerts

## 2026-07-15 — HOD Momo UI lag at ~1000 alerts despite virtualization

- **Symptom:** Browser extremely laggy on HOD Momo tab with ~1000 alerts today; scrolling/UI felt frozen.
- **Cause:** Hand-rolled windowing + later a custom Prev/Next pager still fought the problem awkwardly; user correctly asked for a standard virtual-scroll library instead.
- **Fix:** Switched the alert table to `@tanstack/react-virtual` (`useVirtualizer`) for continuous scroll with only viewport+overscan rows mounted; removed custom pager/`useWindowedRows`.
- **Keywords:** HOD Momo lag, @tanstack/react-virtual, virtualization, 1000 alerts, HodMomoAlertTable

## 2026-07-15 — reset_config(12) rejected; HOD Momo debug path queued stale fundamentals symbol

- **Symptom (bug 1):** `POST` to the HOD Momo config-reset API for strategy 12 ("Running Up Alert") silently returned `None`/404-equivalent — that one strategy could never be reset to defaults individually, even though `reset_all()` and every other strategy ID worked fine.
- **Cause (bug 1):** `hod_momo.reset_config()` validated the incoming `strategy_id` against a hardcoded `range(1, 12)` (exclusive upper bound → IDs 1–11 only) instead of the `HOD_MOMO_STRATEGY_ID_MAX` constant (=12, inclusive per `HOD_MOMO_STRATEGY_NAMES`/`HOD_MOMO_STRATEGY_DEFAULTS` and per the sibling `_load_configs_from_disk()`, which already used `range(1, HOD_MOMO_STRATEGY_ID_MAX + 1)`). Strategy 12 (Running Up) was added later (schema v3) and this bound was never updated to match.
- **Fix:** `reset_config()` now checks `strategy_id not in range(1, HOD_MOMO_STRATEGY_ID_MAX + 1)`, matching the existing inclusive-bound pattern already used elsewhere in `hod_momo.py`. Added `test_reset_config_resets_strategy_12_running_up` and `test_reset_config_still_rejects_out_of_range_ids` in `backend/tests/test_hod_momo_engine.py`.
- **Symptom (bug 2):** The HOD Momo debug-symbol endpoint (`get_debug_symbol` → `_would_fire_now`) could enqueue the wrong ticker (or nothing useful) into the fundamentals-fetch queue instead of the symbol actually being inspected.
- **Cause (bug 2):** `_would_fire_now(symbol)` called `_evaluate_strategy(..., lambda: mark_needs_fundamentals(_active_symbol()))`, reusing the same callback shape as the live `on_trade_update` path. But only `on_trade_update` sets the module-level `_active_symbol_name` global (to the live symbol on entry, back to `""` on exit) — `_would_fire_now` never set it. Any debug-symbol request that ran between trades (i.e. always, since it's not invoked from inside `on_trade_update`) read a stale leftover symbol (or `""`) via `_active_symbol()`, so `mark_needs_fundamentals()` queued the wrong ticker.
- **Fix:** `_would_fire_now()` now calls `mark_needs_fundamentals(symbol)` directly using its own `symbol` parameter instead of routing through the `_active_symbol_name` global that only `on_trade_update` owns. The live `on_trade_update` path is unchanged. Added `test_would_fire_now_queues_symbol_being_debugged_not_stale_active_symbol` in `backend/tests/test_hod_momo_engine.py`.
- **Keywords:** reset_config, HOD_MOMO_STRATEGY_ID_MAX, off-by-one, strategy 12, Running Up Alert, _would_fire_now, get_debug_symbol, mark_needs_fundamentals, _active_symbol_name, stale symbol, fundamentals queue, hod_momo.py

## 2026-07-15 — Open-ticker detail loop still snapshotting symbols already streaming live

- **Symptom:** Suspected open-ticker (quote panel) lag under load (movers scans + multiple open panels), attributed to the detail refresh being snapshot-based instead of a persistent `reqMktData` stream.
- **Cause:** The open ticker had *already* moved to streaming (`ibkr/ticks.py`, `reqMktData`, added 2026-07-14) — but `ibkr/reprice.py`'s `detail_reprice_loop` "backstop" kept firing a full `reqTickersAsync` snapshot every `IBKR_REPRICE_INTERVAL_SEC` (3s) for **every** open detail symbol regardless of whether its stream was already delivering. That redundant snapshot request queued on the same Gateway connection as `table_reprice_loop`'s 1Hz chunked snapshots — real request-queue contention, just from a duplicate call nobody removed after streaming landed.
- **Fix:** `ibkr/ticks.py` now stamps `last_update_ts` on every `updateEvent` and exposes `is_fresh(symbol, max_age_sec)`. `detail_reprice_loop` / `reprice_detail_symbols` take an optional `is_stream_fresh` callback (wired in `app_lifespan.py` to `ticks.is_fresh(..., IBKR_DETAIL_STREAM_FRESH_SEC)`) and skip the snapshot+broadcast entirely for symbols whose stream is fresh, only backstopping symbols with no/stale stream.
- **Keywords:** open ticker lag, reqMktData already streaming, detail_reprice_loop, reqTickersAsync contention, ibkr/ticks.py, ibkr/reprice.py, IBKR_DETAIL_STREAM_FRESH_SEC, is_fresh, Gateway request queue, table_reprice_loop contention

## 2026-07-15 — Empty "IBKR bars failed for SYMBOL:" in Sentry

- **Symptom:** Sentry/logs showed `IBKR bars failed for AAPL:` / `PYPG:` with nothing after the colon; UI got opaque 503s.
- **Cause:** `reqHistoricalData` timeouts and Gateway cancel (Error 162) often raise exceptions whose `str(exc)` is empty (`TimeoutError()`). Chart path logged/raised with `{exc}` only. Those expected failures were also logged at ERROR, flooding Sentry.
- **Fix:** `ibkr/errors.describe_exc` / `is_transient_historical_failure` / `bars_failure_detail`; transient → warning + clear 503; unexpected → error+traceback. Still no Alpaca candle fallback under ibkr.
- **Keywords:** IBKR bars, chart_bars, TimeoutError, Error 162, Sentry empty message, historical cancelled, PYTHON-FASTAPI-6

## 2026-07-15 — Alpaca WS still connected under discovery=ibkr

- **Symptom:** Backend opened Alpaca market-data WS even when discovery=ibkr (HOD trades already ignored), burning the single connection slot and risking 406 under reload.
- **Cause:** `stream_loop` always connected; prior fix only skipped applying trades, not opening the socket.
- **Fix:** Idle + poll when `not alpaca_trades_drive_hod()`; break inner loop if discovery flips to ibkr mid-session.
- **Keywords:** Alpaca WS, idle, discovery=ibkr, 406, connection limit, stream_loop, ALPACA_WS_IDLE_POLL_SEC

## 2026-07-15 — Alpaca WS still fed HOD Momo under discovery=ibkr

- **Symptom:** HOD alerts / snaps could move on Alpaca IEX prints while scanner/quote prices came from IBKR — dual-feed drift after hours or on thin IEX.
- **Cause:** `handle_trade` already skipped scanner cache overlays under ibkr, but the stream loop still called `_hod_momo.on_trade_update` and `l2.tape.on_alpaca_trade` for every Alpaca trade.
- **Fix:** Early-continue when `not alpaca_trades_drive_hod()`; IBKR `table_reprice` / detail ticks remain the HOD feed.
- **Keywords:** dual-feed, HOD Momo, Alpaca WS, on_trade_update, discovery=ibkr, single-market-data-feed, l2.tape

## 2026-07-14 — Ticker WS used missing main._ibkr_ticks after Phase 4 extract

- **Symptom:** Opening a ticker under discovery=ibkr could fail to subscribe ticks / raise AttributeError if the old route path ran (`m._ibkr_ticks`).
- **Cause:** `routes/ticker.py` still did `import main as m` and called `m._ibkr_ticks.subscribe`, but ticks live in `ibkr.ticks` and were never re-exported on `main` after the router extract.
- **Fix:** Route imports `from ibkr import ticks as _ibkr_ticks`, `alpaca` helpers, and `websocket.mark_resub` directly — no main indirection for tick subscribe.
- **Keywords:** routes/ticker, _ibkr_ticks, AttributeError, websocket ticker, Phase 4 extract

## 2026-07-14 — Strategy bars + catalyst prices mixed Alpaca when discovery=ibkr

- **Symptom:** Strategy endpoints (`/api/strategy/gap-and-go`, `/api/strategy/setups`) always used Alpaca IEX bars regardless of provider; Catalysts tab prices disagreed with IBKR scanner rows. REST `/api/ticker/{sym}` silently served Alpaca snapshot when IBKR snapshot was empty.
- **Cause:** (1) `routes/strategy.py` and `strategy/setups_stream.py` imported `bars.fetch_bars` directly (Alpaca-only) instead of the provider-aware `chart_bars.fetch_chart_bars`. (2) `_run_news_catalyst_scan` always called `_fetch_snapshots` (Alpaca) for prices regardless of `_get_discovery_provider()`. (3) `_build_ticker_detail` explicitly fell back to `_fetch_ticker_snapshot` (Alpaca) when IBKR returned `{}`.
- **Fix:** (1) Strategy routes + setups stream → `chart_bars.fetch_chart_bars(discovery_provider=...)`. (2) Catalyst scan → use `_find_ibkr_cache_row` for prices when `ibkr`, Alpaca path only for `alpaca`. (3) REST ticker — removed Alpaca fallback; logs warning and returns empty snapshot matching WS behavior.
- **Keywords:** strategy bars, setups_stream, catalyst price, _build_ticker_detail, Alpaca fallback, single-market-data-feed, fetch_chart_bars, discovery_provider

## 2026-07-14 — Scanner table prices stale 7–10s (giant reqTickersAsync)

- **Symptom:** Header showed "stale · updated 7s ago" / up to ~10s on Gainers even while Connected; prices felt stuck.
- **Cause:** `table_reprice_loop` called one `reqTickersAsync` for ~100 symbols (gainers+losers+AH+HOD seeds). That call often took 7–10s; skip-if-busy then emitted stale heartbeats until it finished, so the UI age never reset mid-batch.
- **Fix:** Chunk snapshots (`IBKR_TABLE_REPRICE_CHUNK_SIZE=20`) with per-chunk timeout; one chunk per 1Hz tick + rotate; push after each chunk; drop HOD seeds from `_table_reprice_symbols` (scanner rows only).
- **Keywords:** stale updated 7s ago, table reprice, reqTickersAsync, IBKR_TABLE_REPRICE_CHUNK_SIZE, price_patch, scanner

## 2026-07-14 — HOD same-ticker spam (no Warrior consolidation)

- **Symptom:** HOD feed repeated the same ticker row after row (CNEY/TRT/…) instead of one row with "(3 in 5sec)".
- **Cause:** Each queued alert set its own `emit_after = now + consolidation_sec`, so staggered fires in the same burst never landed in one flush bucket.
- **Fix:** First alert opens the window; later same-ticker fires share that deadline; emit newest price + real `consolidation_span_sec`; UI shows `(N in Xs)` under Symbol and collapses leftover consecutive rows.
- **Keywords:** HOD Momo, consolidation, Warrior, N in Xs, same ticker, TRT, AEHR

## 2026-07-14 — HOD Momo freezes with 3k+ alerts (save + UI thrash)

- **Symptom:** UI glitches/freezes with HOD Momo at ~3000 alerts; whole app felt sticky. Follow-up: truncating the live list to 500 hid older alerts users still needed.
- **Cause:** (1) Every emitted alert serialized+wrote the full day list to disk on the asyncio thread. (2) Each live alert re-rendered App. (3) Mounting every `<tr>` (pre-virtualization). Truncating data was the wrong fix for (3).
- **Fix:** Rate-limit alert persistence (5s); keep **all** alerts in memory/WS; virtualize row render only; batch live prepends (150ms); rAF-throttle scroll.
- **Keywords:** HOD Momo freeze, 3000 alerts, _save_alerts, virtualization, useHodMomoStream, do not truncate

## 2026-07-14 — After-hours HOD missed Warrior names (ATHE/TRT/XCUR)

- **Symptom:** Warrior Small Cap HOD AH showed ATHE/TRT/XCUR; Nova HOD showed DYAI squeeze spam; XCUR open in quote but not alerting; After Hours tab ~2 rows.
- **Cause:** (1) AH discovery used Alpaca IEX full-universe scan while `discovery=ibkr` — often 0–2 rows, starving HOD universe. (2) First IBKR AH call raced Gateway connect → 0 rows → **silent Alpaca fallback** locked in a 2-row snapshot for the discovery interval. (3) Enrichment/fundamentals overwrote RVOL with thin yfinance volume. (4) AH scan loop stopped refreshing Top Gainers. (5) `_effective_min_rvol` ignored `afterhours_min_rvol`.
- **Fix:** AH rows reshape from live IBKR `_gainer_cache` every AH cycle (no Alpaca fallback when discovery=ibkr); IBKR focus reprice + HOD snap seed; enrichment/on_trade `ibkr_pace` RVOL; AH loop runs `_run_gainers_update`; master gate uses `afterhours_min_rvol`.
- **Keywords:** after hours, HOD Momo, ATHE, TRT, XCUR, DYAI, IBKR TOP_PERC_GAIN, ibkr_pace, yfinance_pace, afterhours_min_rvol, Alpaca fallback

## 2026-07-14 — HOD Momo ≠ Warrior Day Trade Dash (wrong universe / RVOL / gates)

- **Symptom:** Warrior Small-Cap HOD showed TSSI / YG / FRE with Squeeze and Medium Float strategies; Nova showed CNEY spam (Former Momo + Squeeze) and missed the same names.
- **Cause:** (1) Watch set was only Top Gainer/Gapper shortlist — Warrior scans the tape including volume runners. (2) RVOL was raw daily/avg, not Warrior "Daily Rate" pace RVOL. (3) Master gate required +3% in 5min on *every* strategy, blocking Medium Float HOD grinds. (4) Former Momo with empty list treated every symbol as a former runner.
- **Fix:** IBKR HOT_BY_VOLUME / TOP_VOLUME_RATE / MOST_ACTIVE seeds; pace RVOL via `market.pace_relative_volume`; master surge default 0 + schema v2 migrate; Former Momo requires non-empty list; table reprice includes HOD seeds.
- **Keywords:** HOD Momo, Warrior Trading, Day Trade Dash, pace RVOL, Daily Rate, Former Momo, HOT_BY_VOLUME, master surge, Medium Float

## 2026-07-14 — HOD Momo tab empty (total_trades_seen=0)

- **Symptom:** HOD Momo showed no alerts all session; debug counters had `universe_size≈6022`, `snaps_populated≈6020`, but `total_trades_seen=0` and empty decisions.
- **Cause:** `_refresh_hod_momo_universe` subscribed Alpaca IEX trades to the full common-stock list (~6k). Free IEX does not deliver a usable tape at that scale (probe: 5 top-gainers → trades; 6k subscribe → silence). Ross / Warrior scanners watch a Top Gainer shortlist, not the full tape — already noted in `Scanner-Provider-IBKR-Primary.md`. A follow-on bug shadowed `import hod_momo_universe as _hod_momo_universe` with the `_hod_momo_universe: set` global (`AttributeError: 'set' object has no attribute 'build_focus_universe'`), which broke the scan loop until the import was renamed `_hod_uni`.
- **Fix:** Default `HOD_MOMO_UNIVERSE_MODE=focus` builds watch set from gappers/gainers/losers/AH + open details; chunk Alpaca subscribe; feed IBKR 1Hz table reprice into `on_trade_update` when discovery=ibkr; import alias `_hod_uni`; add universe + engine tests.
- **Keywords:** HOD Momo empty, total_trades_seen, Alpaca IEX, 6000 symbols, Ross shortlist, focus universe, table_reprice, on_trade_update

## 2026-07-14 — Empty Time & Sales; Level 2 cramped beside it

- **Symptom:** Quote panel showed Level 2 and Time & Sales squeezed side-by-side; T&S headers visible but no prints. Data sources still listed Interactive Brokers for both.
- **Cause:** (1) Layout: `DepthAndTape` used a horizontal flex split inside the half-width quote column. (2) Data: the live uvicorn process had not picked up `/ws/ibkr/tape/{symbol}` — unmatched WS paths return HTTP 403, so `useIbkrTape` never got `subscribed`/prints. Empty-state text also collapsed (`flex: 1 1 0` with no min-height).
- **Fix:** Stack L2 + T&S as full-width rows under Watchlist; give `.ts-panel` a min-height; restart API so the tape route loads; surface IB tick-by-tick subscription errors on the WS.
- **Keywords:** Time & Sales empty, Level 2 cramped, DepthAndTape, /ws/ibkr/tape, WebSocket 403, reqTickByTickData, AllLast, Watchlist layout

## 2026-07-14 — Scanner “updated 10–12s ago” / table prices frozen during movers scan

- **Symptom:** Header age climbed to ~10–12+ seconds; Gainers table prices lagged the open quote panel even though both said IBKR.
- **Cause:** `reprice_table_caches` only ran inside `_sleep_with_ibkr_reprice` after `_run_gainers_update` finished. A full IBKR movers scan often takes 20–90s, so table prices and `_gainer_cache_ts` (drives “updated Xs ago”) did not advance during the scan.
- **Fix:** Independent 1Hz `table_reprice_loop` + `/ws/scanner` patches + honest stale UI; contract cache for snapshots; removed mid-sleep table reprice.
- **Keywords:** updated 10s ago, table lag, IBKR_TABLE_REPRICE_INTERVAL_SEC, table_reprice_loop, scan loop starvation, reqTickersAsync, scanner_push, stale

## 2026-07-14 — Level 2 book from prior ticker under new quote (MVO vs ~$7 NXTC)

- **Symptom:** Quote panel showed MVO at $0.80 (+363%) while Level 2 showed bids/asks around $7.14–$7.28 (prior ticker NXTC). Data sources said IBKR for quote/L2 but “Broker listing (Alpaca)” looked like a mixed feed.
- **Cause:** (1) `useTickerStream` kept prior `detail` across symbol changes, so `DepthLadder symbol={detail.symbol}` stayed on the old name while the header/scanner reflected the new selection. (2) SidePanel rendered whenever `detail` was truthy without `detail.symbol === selectedSymbol`. (3) `useIbkrDepth` did not ignore stale WebSocket instances or `msg.symbol` mismatches. Separately, `chart_bars` silently fell back to Alpaca when IBKR failed — a second class of “unaware dual feed” risk.
- **Fix:** Clear detail on switch; gate panel on symbol match; bind L2 to `selectedSymbol` + WS/`msg.symbol` guards; IBKR-mode chart bars hard-fail (no Alpaca fallback); project rule `single-market-data-feed.mdc`; retitle listing as metadata.
- **Keywords:** Level 2 wrong symbol, MVO, NXTC, stale detail, useTickerStream, useIbkrDepth, single source of truth, Alpaca fallback, chart_bars, quote panel gate

## 2026-07-14 — 1Min chart looked wrong vs other tools; live candle not tick-fast (IBKR mode)

- **Symptom:** With `NOVA_DISCOVERY_PROVIDER=ibkr`, the quote price could move (slowly) while the 1-minute chart looked sparse/"weird" vs Webull/other tools, and the forming candle did not update tick-by-tick. Level 2 still felt live.
- **Cause:** (1) Chart bars always came from Alpaca IEX (`bars.fetch_bars`) regardless of discovery provider — thin IEX history vs IBKR live quotes = mismatched candles. (2) Live `trade_update`s were only from 3s `snapshot_quotes` reprice, and broadcasts were scheduled through `_run_ibkr` on the contended IB bridge, so gaps often stretched to ~10–14s. No `reqMktData` last-price stream existed for detail panels (unlike Level 2).
- **Fix:** Added `backend/ibkr/bars.py` + `chart_bars.fetch_chart_bars` (IBKR historical when connected, Alpaca fallback). Added `backend/ibkr/ticks.py` streaming last-price on ticker-detail WS open/close. Reprice broadcasts now `run_coroutine_threadsafe` onto the main loop instead of `_run_ibkr`. Relaxed frontend `CHART_REFETCH_SEC` for 1Min (ticks own the live candle).
- **Keywords:** chart wrong, IEX sparse bars, IBKR historical, reqHistoricalData, trade_update slow, reqMktData ticks, dual data source, chart_bars, ibkr/ticks.py

## 2026-07-14 — Agent shell env var (`NOVA_API_RELOAD`) silently survived across an entire session, made every "stable restart" still use `--reload`

- **Symptom:** Mid-session, an agent set `NOVA_API_RELOAD=1` once to force a hot-reload restart, then later deliberately started the backend "without reload" for stability several times (`py -3 run_api.py`, no flag). Each of those "stable" restarts still printed `WatchFiles detected changes ... Reloading...` on the next file edit and then the whole process silently exited (`exit_code: 0`, no traceback) — looking exactly like a mysterious app crash-on-reload bug, when editing files should not have restarted anything at all.
- **Cause:** The agent's shell tool is a single persistent PowerShell session across the whole conversation. `$env:NOVA_API_RELOAD = 1` (or `[Environment]::SetEnvironmentVariable` / `$env:X=1` in an earlier command) persists for every subsequent command in that session, including ones run much later that never intended to touch it. `run_api.py` reads `NOVA_API_RELOAD` with a "false" default, so it looked safe — but the stale `1` from earlier silently overrode that default on every later restart, and was never printed or checked before declaring "backend restarted, stable, no reload."
- **Fix:** No code change — this is a process discipline issue. Before relying on a shell-scoped env var to be *unset* / at its default, explicitly check it (`$env:NOVA_API_RELOAD`) or explicitly clear it (`Remove-Item Env:\NOVA_API_RELOAD`) rather than assuming a fresh default. When a background process behaves unexpectedly right after a restart in a long agent session, check `Get-ChildItem Env:` for stale overrides before assuming the application code is at fault.
- **Keywords:** NOVA_API_RELOAD, stale env var, persistent shell session, WatchFiles Reloading, silent exit_code 0, uvicorn --reload, agent shell state, false debugging lead

## 2026-07-14 — Detail panel updates every ~30s instead of every tick (IBKR provider)

- **Symptom:** With `NOVA_DISCOVERY_PROVIDER=ibkr`, the ticker-detail panel's `trade_update` WS message (price/volume/prev_close) arrived only once every ~14-90s, not every `IBKR_REPRICE_INTERVAL_SEC` (3s) as intended — everything else in the panel looked frozen except Level 2, which streams independently.
- **Cause:** The fast "reprice between scans" mechanism (`_reprice_ibkr_caches`, called from `_sleep_with_ibkr_reprice` inside `_scan_loop`'s sleep) only got CPU time *after* that iteration's `_run_gainers_update()` finished. For the IBKR provider, `_run_gainers_update` runs a full market scan (`get_gainers()` + `get_losers()`, each doing `scan_symbols()` + `snapshot_quotes()` for up to 50 symbols) *before* the loop ever reaches the sleep/reprice step — that alone routinely took 20-90+ seconds. So even after first separating "reprice the 1-2 detail symbols" from "reprice the whole 100+ symbol table" into two functions, both were still nested inside the same slow scan loop and only got to run once per full (slow) iteration, not every 3s.
- **Fix:** Extracted the reprice logic out of `main.py` into `backend/ibkr/reprice.py` (`reprice_detail_symbols`, `reprice_table_caches`, `detail_reprice_loop`). `detail_reprice_loop` is now started as its **own independent `asyncio.create_task`** in `main.py`'s lifespan, on its own `asyncio.sleep(IBKR_REPRICE_INTERVAL_SEC)` timer, completely decoupled from `_scan_loop` — it can never be blocked by a slow discovery/movers scan. The bulk table reprice (`reprice_table_caches`) stays tied to the scan loop's sleep, since it's a best-effort refresh between full scans, not a per-tick guarantee. Added `backend/tests/test_ibkr_reprice.py` to lock in the separation and the "fall back to cached price when snapshot_quotes() comes back empty" behavior.
- **Keywords:** trade_update, detail panel frozen, _reprice_ibkr_caches, _sleep_with_ibkr_reprice, _run_gainers_update slow, IBKR_REPRICE_INTERVAL_SEC, ibkr/reprice.py, detail_reprice_loop, decoupled async task, scan loop starvation

## 2026-07-14 — Quote panel price/gap % desynced from IBKR scanner row

- **Symptom:** Same symbol (e.g. NXTC) showed scanner Price $9.02 / Gap +313.60% while the quote panel showed big line 2.28 (+16.92%) and Pre: 9.02 +6.74 (+295.46%). User thought React was not updating.
- **Cause:** `/ws/ticker/{symbol}` Phase 1 (`_build_ticker_fast`) always fetched Alpaca snapshots even when `discovery_provider=ibkr`. REST `_build_ticker_detail` already used IBKR. Alpaca `session_close` ≈ $2.28 vs IBKR scanner `prev_close` ≈ $2.18 produced two different gap %. `_fetch_ticker_snapshot_ibkr` also set `session_close` to the live price (wrong for Webull Pre: math). `trade_update` only patched `latest_trade.price`, not `prev_close`. Bid/ask bracketing last is normal L2, not a sync bug.
- **Fix:** `_build_ticker_fast` uses `_fetch_ticker_snapshot_ibkr` when discovery is ibkr; `session_close` = prior close; IBKR UI uses one live-vs-prev_close line; `trade_update` includes `prev_close` and `useTickerStream` patches snapshot accordingly.
- **Keywords:** NXTC, quote panel mismatch, scanner gap %, _build_ticker_fast, Alpaca vs IBKR, session_close, trade_update, useTickerStream, Webull Pre line

## 2026-07-14 — IBKR gappers empty in premarket (TOP_OPEN_PERC_GAIN returns 0)

- **Symptom:** After IB Gateway connected (`/api/ibkr/status` connected:true), `/api/gappers` still returned `[]` during premarket despite real gaps (NXTC +300%, etc. visible via IB `TOP_PERC_GAIN`).
- **Cause:** `get_gappers()` only used scan code `TOP_OPEN_PERC_GAIN` (today's open vs prior close). Before the regular session open, IB often returns 0 rows / error 162 "API scanner subscription cancelled" for that code. Premarket gaps are correctly described by `TOP_PERC_GAIN` (last vs prior close).
- **Fix:** `backend/ibkr/discovery.py` `get_gappers()` now falls back to `TOP_PERC_GAIN` when `TOP_OPEN_PERC_GAIN` is empty, then applies the existing `GAPPER_MIN_GAP_PCT` filter. Added scanner result logging.
- **Keywords:** TOP_OPEN_PERC_GAIN, TOP_PERC_GAIN, premarket gappers, error 162, scanner cancelled, get_gappers, IBKR discovery


- **Symptom:** User reported "nothing is being scanned" and knew real gappers existed, but `/api/gappers`, `/api/movers`, `/api/afterhours` all returned empty lists, and the UI showed the generic "No gappers with a gap of at least X% yet — scan running..." message that implied everything was healthy.
- **Cause:** `.env` has `NOVA_DISCOVERY_PROVIDER='ibkr'`, so scanner discovery is sourced from IBKR (`backend/ibkr/discovery.py`), not Alpaca — but IB Gateway was not logged in. Launching `C:\Jts\ibgateway\1045\ibgateway.exe` alone is not enough: until login (+ weekly 2FA) completes, Gateway opens **no** local API socket, so Nova's reconnect loop gets `ConnectionRefusedError` on `127.0.0.1:4001` forever. `_run_ibkr()` then returns `[]`, which the UI treated as "no gaps yet". Red herring: port `40001` was listening but owned by `Immersed-service` (VR), not IB — TCP connect succeeded then IB API handshake timed out with WinError 64.
- **Fix:** (1) Launch Gateway and bring its login window to the foreground; Nova already retries every ~10s once the API port opens after login. (2) `EmptyState` now takes `discoveryProvider` and, when `ibkr` + Gateway offline, shows `EMPTY_IBKR_DISCONNECTED` instead of the misleading "no gappers yet" copy (`frontend/src/components/EmptyState.tsx`, `constants.ts`).
- **Keywords:** empty gappers, no movers, ConnectionRefusedError, IB Gateway not logged in, NOVA_DISCOVERY_PROVIDER, _run_ibkr, /api/ibkr/status, silent degrade, port 4001, Immersed 40001, EMPTY_IBKR_DISCONNECTED

## 2026-07-14 — Block button in quote panel could not be undone

- **Symptom:** User clicked "Block" on a ticker (LVLU) in the quote panel, then clicked the button again to undo it — nothing happened. The ticker stayed on the HOD Momo blocklist with no way to remove it from that button.
- **Cause:** `TickerDetailContent.tsx`'s block button only ever called `POST /api/hod-momo/blocklist` (add) and set local `blocked` state to `true`, then rendered `disabled={blocked}` — once true, the button could never be clicked again, and there was no code path calling the `DELETE /api/hod-momo/blocklist/{symbol}` endpoint that already existed in `backend/main.py`/`hod_momo.py`. Separately, `blocked` was reset to a hardcoded `false` on every symbol change instead of checking the real blocklist, so an already-blocked symbol misleadingly showed "Block" instead of "Blocked" on first load.
- **Fix:** Fetch the real blocklist on mount/symbol-change and derive `blocked` from it. Replace the one-way `onBlock` with `onToggleBlock`, which `DELETE`s when already blocked (no confirmation — restorative) or shows a `window.confirm()` dialog before `POST`ing to block (per user request: confirm before every block). Button is never `disabled`; label reads "Block"/"Unblock" from the real state.
- **Keywords:** Block button, HOD Momo blocklist, disabled button, unblock, onToggleBlock, TickerDetailContent, quote panel, window.confirm

## 2026-07-14 — Catalyst rows always showed "unknown" source tier

- **Symptom:** Every row on the Catalysts tab classified `source_tier` as `unknown`/`none` and `confirmed_by_official` as `False`, even for headlines from official wires like Business Wire/PR Newswire, and the frontend had no way to show the reader where a catalyst headline actually came from.
- **Cause:** `_run_news_catalyst_scan()` in `backend/main.py` built `symbol_to_article` from the Alpaca `/v1beta1/news` response but only kept `created_at`/`headline`/`url` — it dropped the article's `source` field entirely. Downstream, `enrich_catalyst_row()` (`backend/news/enrich.py`) and the ticker-detail fallback path in `_gather_context()` (`backend/routes/news.py`) both hardcoded `"source": ""` when constructing the article dict passed into `evaluate_news_impact()`, so `classify_source_tier()` had nothing to classify beyond headline/URL keyword matches.
- **Fix:** Capture `article.get("source", "")` into `symbol_to_article` and thread it through as `catalyst_source` on each catalyst row; `enrich_catalyst_row()` and `_gather_context()` now read `row.get("catalyst_source")` instead of a literal `""`. Also added `news/sources.py::best_source_name()` and a new `source_name`/`headline_url` field on `NewsImpactVerdict` so the frontend can show the literal publisher name (not just the tier bucket) next to every headline, in both the Catalysts tab and the quote panel's `NewsImpactPanel`.
- **Keywords:** source_tier, confirmed_by_official, catalyst_source, enrich_catalyst_row, _gather_context, _run_news_catalyst_scan, best_source_name, NewsImpactVerdict, classify_source_tier

## 2026-07-13 — Stock View double-click lost to layout re-render

- **Symptom:** Double-clicking a ticker in Electron did not open Stock View in a new window (Quote Panel updated; no child window). Direct `novaDesktop.openStockView` IPC worked.
- **Cause:** Native `dblclick` requires both clicks on the same target. The first click called `setSelectedSymbol`, re-rendering the row / shifting layout so the second click was not paired as a double-click. Synthetic `dblclick` events still worked, which hid the bug in earlier checks.
- **Fix:** Replace `onDoubleClick` with timed click pairing (`createClickVsDoubleClick`, `SYMBOL_DOUBLE_CLICK_MS`). Second click within the window opens Stock View; single click selects after the delay. Electron child window `show()`/`focus()` after load.
- **Keywords:** Stock View, double-click, dblclick, layout shift, SymbolSelectButton, SelectableTableRow, clickVsDoubleClick, Quote Panel

## 2026-07-13 — Stock View double-click stayed in the same window

- **Symptom:** Double-clicking a ticker (Electron desktop) did not open a new window; Stock View replaced the scanner in the current window.
- **Cause:** `window.open(url, '_blank', 'noopener,noreferrer')` returns `null` when `noopener` is set (by design). `openStockView` treated null as "popup blocked" and called `setStockViewSymbol`, navigating the current tab. Electron also needs an explicit BrowserWindow path — `window.open` alone is unreliable without a trusted IPC open.
- **Fix:** Drop `noopener` from `window.open` (still clear `win.opener` after open). Add `novaDesktop.openStockView(url)` IPC → main creates a child `BrowserWindow`. Prefer IPC when running in the desktop shell.
- **Keywords:** Stock View, double-click, window.open null, noopener, Electron setWindowOpenHandler, nova:openStockView, same window fallback

## 2026-07-13 — LVLU Open 0 / wrong split date on quote card

- **Symptom:** LVLU side panel showed Open `0`, High/Low equal to a stale Previous Close, and Recent Split `1:15` with a calendar day that did not match the Nasdaq trading-effective date (Jul 7, 2025).
- **Cause:** (1) IBKR discovery snapshots omit session OHLC; when a feed sent `0` or the UI formatted a zero open, `fmtPrice(0)` painted `$0.00`. (2) `recent_split` used `datetime.fromtimestamp(epoch)` in the local timezone, so Yahoo’s UTC-midnight epoch for LVLU became `2025-07-06` in US/Eastern.
- **Fix:** Extracted fundamentals to `backend/fundamentals.py` with UTC `_yf_date_str` / `format_recent_split`. Coerce non-positive O/H/L to null in Alpaca `_bar` and IBKR snapshot. Frontend `fmtSessionPrice` / `sessionPriceOrNull` show "—" for missing OHLC.
- **Keywords:** LVLU, Open 0, fmtSessionPrice, recent_split, lastSplitDate, yfinance UTC, OHLC missing, IBKR discovery

## 2026-07-13 — Level 2 Reconnecting forever on Symbol cap + stale scan age

- **Symptom:** Scanner looked unstable: header showed "updated ~5962s ago" on Movers, Level 2 for SHPH showed a book with a yellow "Reconnecting…" badge that never cleared, latency looked high.
- **Cause:** (1) IBKR depth hard-capped at 3 symbols; EHGO/GFUZ/LVLU held the slots. Concurrent `subscribe_async` calls raced through `qualifyContractsAsync` before reserving a slot (triple `reqMktDepth` for EHGO in logs). Eviction either was not loaded in the live process or did not stop `l2.continuous`, so SHPH reconnects got `Symbol cap reached` and closed the WS. DepthLadder hid that error whenever a prior book existed and only showed "Reconnecting…". (2) `App.tsx` `fetchData` wrote `lastScan` from gappers, then movers, then afterhours — after-hours timestamps freeze after the session, so Movers inherited a multi-hour-old age.
- **Fix:** Serialize depth subscribe with an asyncio lock; reserve the subscription slot before qualify; make eviction async, loop until under cap, and stop continuous L2 for the victim. DepthLadder shows backend error text even with a cached book. Tab-aware `scanAgeForTab` drives the header age.
- **Keywords:** Reconnecting depth, Symbol cap reached, IBKR_MAX_DEPTH_SYMBOLS, subscribe race, qualifyContractsAsync, updated 5962s ago, last_scan afterhours overwrite, scanAgeForTab, EHGO GFUZ LVLU SHPH

## 2026-07-13 — Level 2 Connecting depth flicker on reconnect

- **Symptom:** Side-panel Level 2 for EHGO (and others) cycled between "Connecting depth for EHGO…" and a real book, then back again, without the user changing symbols.
- **Cause:** Stacked issues. (1) `DepthLadder` treated `!connected` as "wipe the ladder", so any WebSocket close/remount replaced a healthy book with Connecting even though the last book was still in state. (2) `ws_depth` unsubscribed / stopped continuous immediately on last-viewer close, so React remounts tore down `reqMktDepth` before reattach. (3) Live probe on EHGO showed the reconnect loop was actually hitting `Symbol cap reached (3 max…)` — slots stuck on AAPL/VMAR/SHPH from earlier browsing with leaked/orphaned viewer counts, so EHGO could never hold a stable subscribe.
- **Fix:** Keep last book visible across reconnects; ignore transient empty DOM frames; surface backend error text; add `IBKR_DEPTH_RELEASE_GRACE_SEC` + `release_when_idle()`; only stop continuous / unsubscribe after grace when still idle; `_evict_for_capacity()` frees idle slots (or force-evicts a leaked one) when a new symbol needs a line.
- **Keywords:** Connecting depth, Level 2 flicker, Symbol cap reached, IBKR_MAX_DEPTH_SYMBOLS, _evict_for_capacity, DepthLadder, useIbkrDepth, release_when_idle, EHGO, AAPL VMAR SHPH slot leak

## 2026-07-13 — SMART depth requested without isSmartDepth=True (false 10092 / L1-only forever)

- **Symptom:** User bought NASDAQ TotalView but Nova only ever showed L1 (`l1_fallback=True`) for every ticker tested (SHPH, YSXT, QTTB, F, AAPL). Gateway logs showed `snapshot perms=REALTIME_TOP` and every `reqMktDepth` was rejected with error 10092 ("Deep market data is not supported for this combination of security type/exchange").
- **Cause:** `backend/ibkr/depth.py` called `ib.reqMktDepth(contract, numRows=10)` on a SMART-qualified Stock with the default `isSmartDepth=False`. IBKR requires either a *direct* exchange (e.g. `ISLAND` for TotalView) or `isSmartDepth=True` on SMART (TWS API ≥974 / BookTrader-style aggregated depth). With `False` on SMART, Gateway rejects the combination for *all* symbols — independent of TotalView entitlement. Confirming evidence after the fix: Gateway warning 2152 listed `Depth: NASDAQ; IEX` as available for AAPL.
- **Fix:** Added `IBKR_DEPTH_SMART=True` and `IBKR_DEPTH_NUM_ROWS=10` to `constants.py`. `subscribe_async` now calls `reqMktDepth(..., numRows=..., isSmartDepth=True)`; `cancelMktDepth` / L1-fallback cancel use the same flag. Regression tests in `TestSmartDepthFlag`.
- **Keywords:** Level 2, TotalView, isSmartDepth, SMART, error 10092, REALTIME_TOP, reqMktDepth, L1 fallback, AAPL depth

## 2026-07-13 — Out-of-order chart trade crashed React and blanked the entire app

- **Symptom:** Clicking/switching symbols could turn the whole Nova page black. Chrome DevTools showed an uncaught `TickerChart` exception from `lightweight-charts` ("Cannot update oldest data ...") followed by React reporting that an error occurred in `<TickerChart>` and recommending an error boundary.
- **Cause:** `TickerChart` merged REST candles with live WebSocket trades. Its update effect handled only `trade bucket == latest candle` and `else`, treating every unequal timestamp as a newer candle. A delayed/out-of-order trade whose bucket was *older* than the latest REST candle therefore reached `candleSeries.update()`. `lightweight-charts` requires monotonic time and throws on older data. The exception was uncaught, and no chart-level error boundary existed, so React unmounted the application tree. Concurrent REST requests also lacked stale-response protection, allowing a previous symbol/timeframe response to overwrite the current chart after rapid switching.
- **Fix:** Extracted chart time/order helpers to `frontend/src/tickerChartData.ts`; `TickerChart` now rejects invalid and older trade buckets before calling the chart library. REST loads use a monotonically increasing request version so stale responses cannot mutate the current chart. Added `TickerChartErrorBoundary` around the imperative chart so any future library exception degrades only the chart, not the scanner. Extracted chart controls to keep `TickerChart.tsx` at 300 lines. Added Vitest and three ordering regression tests.
- **Keywords:** blank page, black screen, TickerChart crash, Cannot update oldest data, lightweight-charts monotonic time, out-of-order WebSocket trade, stale REST response, error boundary, rapid symbol switching

## 2026-07-13 — Root logger had no console handler, slowing down live debugging

- **Symptom:** While diagnosing the Level 2 flicker (entry below), `ibkr.depth`'s `logger.info`/`warning`/`error` calls that would have shown the bug immediately (`"IBKR: subscribed depth for SHPH"`, `"depth rejected server-side..."`, etc.) never appeared in the terminal running `uvicorn`/`run_api.py` — only `uvicorn`'s own access-log lines did. Had to open and `grep` `backend/logs/blast.log` by hand to see what our own code was actually doing.
- **Cause:** `main.py` only ever attached a `RotatingFileHandler` to the root logger (`logging.getLogger().addHandler(_file_handler)`), never a `logging.StreamHandler()`. Every module logger (`logging.getLogger(__name__)`) propagates to root by default, so all of it silently went to disk only.
- **Fix:** Extracted logging bootstrap out of `main.py` into `backend/logging_setup.py` (`configure_logging()`), which now attaches both a console `StreamHandler` and the rotating file handler to the root logger with the same formatter, plus the UTF-8 console reconfiguration that previously only existed in `run_api.py` (needed for the `uvicorn main:app` direct-import dev path, which skips `run_api.py`'s entrypoint fix). This is also a `backend-modularity`/file-size-limit cleanup — `main.py` was already over its 200-line target.
- **Keywords:** invisible logs, root logger no console handler, blast.log grep, StreamHandler, propagate, live debugging slow, logging_setup.py

## 2026-07-13 — Level 2 depth ladder flickered between empty and real book after L1 fallback

- **Symptom:** After the previous L1-fallback fix (see entry below), the user still reported "I only see 'Waiting for book data'... I don't really see level 2" and the panel sometimes needing a refresh. A raw WS probe against `/ws/ibkr/depth/SHPH` showed the real bug: every real L1 tick produced **two** `book` messages back-to-back — one empty (`bids=0 asks=0 l1_fallback=False`) immediately followed by the real one (`bids=1 asks=1 l1_fallback=True`) — repeating for the life of the connection.
- **Cause:** `ib_async`'s `Wrapper.startTicker` caches `Ticker` objects per `hash(contract)`, so `ib.reqMktData(contract, ...)` called during the L1 fallback returns the **same** `Ticker` instance that `ib.reqMktDepth(contract, ...)` had already returned. `backend/ibkr/depth.py`'s `subscribe_async()` and `_fallback_to_l1()` both did `ticker.updateEvent += lambda t: ...` without ever detaching the previous listener, so after falling back both `_on_update_book` (reads `ticker.domBids`/`domAsks`, empty forever since depth was cancelled) and `_on_update_ticker` (reads `ticker.bid`/`ticker.ask`, real L1 data) stayed wired to the one shared `Ticker`. Every real tick fired both, racing an empty book against the real one straight into the same WS queue — which is exactly what made the frontend ladder flicker/never settle, independent of the async-rejection timing fixed earlier.
- **Fix:** Added `_attach_update_handler(symbol, ticker, handler)` / `_detach_update_handler(symbol)` to `backend/ibkr/depth.py`, tracking the exact listener function wired per symbol in `_update_handlers`. `_attach_update_handler` always detaches the previous listener (via `ticker.updateEvent -= handler`) before wiring the new one, used in `subscribe_async()`'s depth path, its L1-fallback except branch, and `_fallback_to_l1()`. `unsubscribe()` also detaches on cleanup. Verified live: a fresh raw WS probe against SHPH after the fix showed 60+ consecutive `book` messages, all `l1_fallback=True` with populated bid/ask, no more empty interleaved frames. Added `TestUpdateHandlerReplacement` to `tests/test_ibkr_safety.py` (shared-ticker regression test).
- **Keywords:** Level 2 flicker, DepthLadder never stable, l1_fallback race, ib_async Ticker cache, startTicker hash(contract), updateEvent double listener, reqMktDepth reqMktData same ticker, stale listener leak, _attach_update_handler, _detach_update_handler

## 2026-07-13 — Level 2 DepthLadder stuck on "Waiting for book data" forever + WS viewer-count leak

- **Symptom:** After wiring `DepthLadder` into the scanner side panel, the Level 2 section for real symbols (e.g. SHPH) never showed a book — it stayed on "Waiting for book data…" indefinitely. Separately, the user also intermittently hit a fully blank page after clicking a symbol, requiring a manual refresh.
- **Cause (Level 2 stuck):** `backend/ibkr/depth.py`'s `reqMktDepth()` call for some small-cap NASDAQ contracts (`tradingClass=SCM`) returns successfully *synchronously* (no Python exception), so the existing `try/except` around it never fires the L1 fallback. IBKR Gateway then rejects the request **asynchronously** via `errorEvent` with code `10092` ("Deep market data is not supported for this combination of security type/exchange"). Since nothing listened for that event, `_on_update_book` never ran, the depth queue stayed empty, and the WS `stream()` generator only ever sent heartbeat "ping"s — so the frontend correctly showed `connected=true, book=null` forever. Confirmed via `backend/logs/blast.log` (root logger has no console handler, so these `logger.info`/`logger.warning` calls were invisible in the terminal — only written to the rotating file).
- **Cause (viewer-count leak, related):** `routes/trading.py`'s `ws_depth` sent the `{"type": "subscribed"}` frame *before* entering the `try/finally` that pairs `ws_viewer_opened()`/`ws_viewer_closed()`. If the client disconnected in that narrow window (React StrictMode double-invoking effects, or fast symbol switching), `send_text()` itself raised `WebSocketDisconnect` outside the try block, permanently inflating the viewer refcount with no matching decrement — eventually starving the `IBKR_MAX_DEPTH_SYMBOLS` budget.
- **Cause (blank page — investigated, not reproduced in a stable session):** Reproduced twice, but only while backend/frontend files were being actively edited (uvicorn `--reload` / Vite HMR churn tearing down WebSockets mid-render). A dedicated rapid-fire click test (`agent-browser batch`, 6 clicks across 4 symbols in <5s) with no concurrent edits did **not** reproduce it — body HTML stayed intact. Likely the same dev-server churn pattern already logged below ("client ID already in use"), now also affecting the frontend Vite HMR side. No code fix applied for this specific report; flag if it recurs with a stable, non-editing session.
- **Fix:** Added `IBKR_ERROR_DEPTH_NOT_SUPPORTED = 10092` to `constants.py`. `depth.py` now installs a one-time `ib.errorEvent` listener (`_install_error_hook`) per IBKR connection; on code 10092 it matches the rejected contract by `conId` and calls `_fallback_to_l1()` (cancels the depth request, subscribes L1 top-of-book instead, sets `l1_fallback=True`) instead of leaving the book empty forever. `routes/trading.py`'s `ws_depth` now performs `ws_viewer_opened()` + the "subscribed" send + the whole stream loop inside one try/finally, with a `viewer_opened` flag so `ws_viewer_closed()` only runs when `ws_viewer_opened()` actually ran. Added `TestDepthAsyncErrorFallback` (4 tests) to `tests/test_ibkr_safety.py`.
- **Keywords:** Level 2 waiting for book data, depth ladder stuck, IBKR error 10092, Deep market data is not supported, reqMktDepth async rejection, errorEvent, L1 fallback, ws_viewer_opened leak, blast.log, root logger no handler, blank page needs refresh, React StrictMode double effect, WebSocketDisconnect outside try

## 2026-07-13 — Ticker detail panel stuck on frozen premarket gapper price while movers table stayed live

- **Symptom:** With `discovery_provider=ibkr`, a symbol's ticker detail panel showed a stale price/prev_close (e.g. VEEE: price=12.01, prev_close=4.34) while the exact same symbol's row in the Gainers/Losers table was live and correct (price=25.05, prev_close=4.82). Confirmed via direct API comparison (`/api/movers` vs `/api/ticker/{symbol}`) — not a caching/browser issue.
- **Cause:** `_find_ibkr_cache_row()` in `main.py` searched `(_gapper_cache, _gainer_cache, _loser_cache)` in that order and returned the first match. Gappers intentionally stop refreshing once the market formally opens (see the "Market Open Halt" rule), so `_gapper_cache` holds a permanently frozen premarket snapshot for any symbol discovered as a gapper earlier in the session. When that same symbol later also becomes an active gainer/loser (continuously repriced every `IBKR_REPRICE_INTERVAL_SEC` by `_reprice_ibkr_caches`), the lookup kept resolving to the frozen gapper row instead of the live gainer/loser row, because gapper cache was checked first. `_fetch_ticker_snapshot_ibkr` (used by the ticker detail endpoint) relies on this helper, so the detail panel inherited the stale value while `/api/movers` (which reads `_gainer_cache`/`_loser_cache` directly, bypassing the helper) stayed correct.
- **Fix:** Reordered the search in `_find_ibkr_cache_row()` to `(_gainer_cache, _loser_cache, _gapper_cache)` so a live gainer/loser row always wins over a frozen gapper row for the same symbol; gapper cache is now only consulted as a fallback for symbols that aren't an active mover. Also removed leftover `[DEBUG]` print statements and a throwaway `_debug_timing.py` script used to diagnose this. Added `backend/tests/test_ibkr_cache_priority.py` covering the priority order.
- **Keywords:** ticker detail stuck, ticker panel stale, VEEE, _find_ibkr_cache_row, _fetch_ticker_snapshot_ibkr, gapper cache frozen, market open halt, IBKR discovery provider, movers table vs ticker detail mismatch

## 2026-07-13 — IBKR-sourced mover rows had internally inconsistent price/change fields

- **Symptom:** After switching `discovery_provider` to `ibkr`, some `/api/movers` rows showed `price - prev_close != change_abs` and `change_abs / prev_close != change_pct` (e.g. VEEE: price=24.42, prev_close=4.34, but change_abs=19.6 when it should be 20.08).
- **Cause:** `_handle_trade` (Alpaca's WS trade stream handler in `main.py`) always overlays the latest Alpaca trade price onto `_gainer_cache`/`_loser_cache` rows regardless of which provider built them, via `_apply_trade_to_mover_list`. It recomputes `change_pct`/`change_abs` from the row's own `prev_close`, so each individual update stays self-consistent — but it runs on Alpaca's own price ticks, which race against the periodic IBKR scan tick (every `GAINERS_INTERVAL_SEC`) that rebuilds the same rows from a different snapshot basis. The two feeds interleaving on the same cache produced rows whose fields were correct at two different instants, not one.
- **Fix:** Added an early return in `_handle_trade` when `_get_discovery_provider() == "ibkr"`, so Alpaca's WS overlay no longer touches gapper/mover caches while IBKR is the active provider. IBKR-sourced rows now only refresh on the scan cadence (20s), which is internally consistent by construction.
- **Keywords:** discovery provider, IBKR scanner, prev_close mismatch, change_pct inconsistent, _handle_trade, _apply_trade_to_mover_list, WS overlay race, movers endpoint

## 2026-07-13 — Live IB Gateway without paper; spend risk

- **Symptom:** User could not complete paper Gateway login; logged into live Gateway with real funds while wiring Nova.
- **Cause:** Paper account uses a separate username; Gateway “Paper Trading” mode must use that paper user. Connection mode was previously tied to `IBKR_LIVE_TRADING_CONFIRMED`, conflating data vs orders.
- **Fix:** `IBKR_GATEWAY_MODE` for port; `IBKR_ORDERS_ENABLED` default false; `ibkr/safety.py` SSOT blocks all place/bracket until unlocked.
- **Keywords:** IBKR live Gateway, paper trading, ORDERS_ENABLED, safety.py, spend lock, Level 2

## 2026-07-12 — News/hotness column missing from Gappers, Movers, After Hours tables

- **Symptom:** The red/orange/yellow news-freshness indicator was gone from the main scanner tables (only visible on the separate Catalysts tab).
- **Cause:** An earlier densify pass (`73acb8c`) trimmed `SCANNER_COLUMNS` in `frontend/src/constants.ts` down to 8 columns and dropped the `['newest_headline_at', 'News']` entry. The render path (`NewsCell`, the `case 'newest_headline_at'` in `renderCell`, and the `.news-flame`/`.flame-hot`/`.flame-warm`/`.flame-cool` CSS) was never removed — it just had nothing pointing to it since `SCANNER_COLUMNS` drives which columns `ScannerTable` renders.
- **Fix:** Re-added `['newest_headline_at', 'News']` to `SCANNER_COLUMNS` (after `Volume`, closest to the pre-densify layout). No changes needed in `ScannerTable.tsx` — the rendering logic was already intact.
- **Keywords:** News column missing, newest_headline_at, NewsCell, flame-hot, flame-warm, flame-cool, SCANNER_COLUMNS, densify regression

## 2026-07-11 — Sidebar chart sat beside Stock Quote again (layout regression)

- **Symptom:** After a layout update, single-click sidebar showed Price Chart and Stock Quote side-by-side; user had previously had chart on its own top row.
- **Cause:** JSX was stacked (chart then `.cq-info-row`) but `.cq-root--columns` CSS still used `display:grid` with three columns, so the chart and info-row became peer grid cells. `.chart-grid` styles for the full-page 2×2 were also missing.
- **Fix:** Root is now flex column (`cq-root--stacked`); multi-col only on `.cq-info-row`. Added `.chart-grid { grid-template-columns: 1fr 1fr }`.
- **Keywords:** sidebar regression, cq-root--columns, cq-root--stacked, chart beside quote, chart-grid 2x2

## 2026-07-11 — Single-click must keep sidebar; full page is double-click only

- **Symptom:** After the prior fix, any ticker click replaced the scanner with a full detail page — removing the side panel UX users still wanted for quick lookup.
- **Cause:** `selectedSymbol` was overloaded to mean “navigate to full page,” so single-click left the scanner.
- **Fix:** Split state: `selectedSymbol` → `SidePanel` only; `tradingSymbol` → `TickerDetailPage`. Symbol rows use `SymbolSelectButton` (click / double-click). Back clears `tradingSymbol` only.
- **Keywords:** double-click, SidePanel, tradingSymbol, selectedSymbol, TickerDetailPage, SymbolSelectButton

## 2026-07-11 — Clicking a ticker did not open a trading/detail screen with charts

- **Symptom:** User clicked a symbol and expected a dedicated trading/detail view with graphs; the UI stayed on the scanner with only a narrow side panel (often perceived as “no graphs”).
- **Cause:** `selectedSymbol` only drove `SidePanel` beside the scanner — there was no full-page navigation. Charts existed in the 380px panel but did not replace the main content.
- **Fix:** When `selectedSymbol` is set, `App.tsx` renders `TickerDetailPage` (Back + large `TickerChart` + fundamentals) instead of the scanner layout. Extracted `useTickerStream`, `TickerDetailContent`, types/formatters. Empty bars fall back to mock candles for drawing-tool verification.
- **Keywords:** ticker click, SidePanel, TickerDetailPage, chart missing, navigation, drawing tools, mock bars

## 2026-07-11 — `validate_trade_plan` accepted inverted longs and rejected exact $0.20 stops

- **Symptom:** (1) A long plan with stop *above* entry (e.g. entry `$5.00`, stop `$5.10`, target `$5.30`) could pass risk validation because distances used `abs()`. (2) A correct plan with stop exactly `$0.20` below entry (entry `$5.00`, stop `$4.80`) was rejected with "Stop of $0.20 exceeds the $0.20 max."
- **Cause:** (1) Absolute-value distance math treated upside-down longs as valid. (2) Binary float: `5.0 - 4.8 == 0.20000000000000018`, so `stop_distance > RISK_MAX_STOP_DOLLARS` was True at the exact ceiling.
- **Fix:** `backend/strategy/risk.py` `validate_trade_plan` now requires stop `<` entry and target `>` entry for longs, and rounds stop/reward distances to 2 decimal places (cents) before comparing to `RISK_MAX_STOP_DOLLARS` / computing R:R. Locked by `tests/test_arithmetic_correctness.py` and extended `tests/test_risk.py`.
- **Keywords:** validate_trade_plan, abs stop distance, inverted long, float precision, RISK_MAX_STOP_DOLLARS, 0.20 exceeds 0.20, round cents, profit loss ratio

## 2026-07-11 — `electron-builder` fails with `EPERM: ... rename 'release\win-unpacked.tmp' -> 'release\win-unpacked'`

- **Symptom:** `npm run electron:pack` (and a bare `npx electron-builder --win nsis --x64` retry) consistently failed at the packaging step with `⨯ EPERM: operation not permitted, rename '...\release\win-unpacked.tmp' -> '...\release\win-unpacked'`, immediately after `downloaded label=electron progress=100%`. The failure was 100% reproducible on retry (not a one-off), which ruled out the usual "transient antivirus scan" explanation. Manually deleting `release\win-unpacked.tmp` between attempts worked fine (proving the *directory* itself, not a locked file inside it, was the problem) — `[System.IO.File]::Open(...,'ReadWrite','None')` on the largest file in that folder (`electron.exe`) succeeded with no lock, confirming no single file was held open.
- **Cause:** Windows (unlike Linux/macOS) refuses to rename a directory while **any process holds an open handle on that directory itself or one of its ancestors** — even a read-only file-system-watch handle, not just a write lock. `Run Nova Desktop.bat` (`npm run electron:dev`) was left running in the background from an earlier step in the same session; its Vite dev server (chokidar-based file watcher) held a recursive watch handle rooted at `frontend/`. Because `electron-builder`'s output dir (`frontend/release/`) lives *under* that same watched root, extracting the electron.zip into `release\win-unpacked.tmp` and then renaming it inherited an ancestor-directory lock from the still-running watcher, so the rename was denied every time, regardless of retries.
- **Fix:** Stopped the dev Electron/Vite process tree (`taskkill /F /T /PID <bat-process-pid>`) before repackaging. Deleted the stale `release\win-unpacked.tmp` (now deletable, confirming the lock was gone) and re-ran `npx electron-builder --win nsis --x64` — succeeded immediately. **Going forward:** never run `npm run electron:pack` / `electron-builder` while `electron:dev` (or any other recursive watcher rooted at or above `frontend/`, e.g. a bare `vite`/`tsc --watch`) is running in the same workspace tree; stop dev watchers first, package, then restart dev mode if still needed.
- **Keywords:** electron-builder EPERM rename win-unpacked.tmp, electron-builder packaging fails Windows, directory rename access denied Windows open handle, chokidar file watcher directory lock, vite dev server holds directory handle, electron:pack fails while electron:dev running, NSIS build EPERM

## 2026-07-11 — Backend API served stale code after `taskkill /F` on a `uvicorn --reload` PID

- **Symptom:** `GET /api/journal/metrics` consistently returned a JSON payload missing the newly added `includes_mock_data` field, even after multiple `WatchFiles detected changes ... Reloading...` cycles confirmed in the uvicorn log and even though calling `compute_metrics()` directly via `py -3 -c` in the same shell/cwd returned the correct, up-to-date dict. `netstat -ano | findstr :8000` showed **two** PIDs both `LISTENING` on `127.0.0.1:8000`, one of which (`tasklist`/`Get-Process`) belonged to a genuinely running `python3.13.exe` using ~264MB of memory that was never referenced by the current terminal's uvicorn output.
- **Cause:** Earlier in the session, port 8000 was already bound by a stale backend from a previous run. `taskkill /F /PID <that-pid>` was used to free the port — but that PID was the **outer process** in the `uvicorn --reload` parent/child pair (the reloader process spawns a separate worker subprocess that actually serves requests). Force-killing only the outer PID left the **child worker orphaned**, still bound to the port and still serving the old, pre-edit code. A brand-new `uvicorn --reload` was then started successfully on the same port (Windows allowed a second `LISTENING` socket to coexist), so two servers were live simultaneously: the new one with fresh code (receiving my direct test requests inconsistently) and the orphaned old one (pinned to the frontend's already-established keep-alive HTTP connections, so the running UI kept talking to stale code no matter how many times the new code reloaded).
- **Fix:** Identified the orphan via `tasklist | findstr python` cross-referenced against the uvicorn terminal log's own reported PIDs, then `taskkill /F /PID <orphan-worker-pid>` (not the reloader PID) to kill the actual leftover worker. After that, `netstat` showed exactly one `LISTENING` entry and the API immediately returned current code. **Going forward:** when a port conflict requires killing a prior `uvicorn --reload` instance, kill the entire process tree (e.g. `taskkill /F /T /PID <pid>` to include child processes) rather than a single PID, and afterward verify with `netstat -ano | findstr :PORT | findstr LISTENING` that only one PID remains before trusting any response from that port.
- **Keywords:** uvicorn --reload orphan process, stale code served, duplicate LISTENING socket same port Windows, taskkill /F leaves child worker running, WatchFiles reload not reflected, FastAPI response missing new field, netstat two PIDs same port, taskkill /T process tree

## 2026-07-10 — UnicodeEncodeError crashing the API process on Windows console output

- **Symptom:** Log/print statements containing non-ASCII characters (e.g. `→`) raised `UnicodeEncodeError: 'charmap' codec can't encode character ... : character maps to <undefined>` when run from a plain Windows console/`cmd.exe` window. The error persisted even after adding a console-stdio fix (below) — it kept firing from inside `logging.StreamHandler.emit`.
- **Cause:** Two separate encoding gaps, found by live-running the app after the first fix:
  1. Windows consoles default to the `cp1252` codepage for Python's `stdout`/`stderr`, which cannot represent most Unicode characters. `uvicorn --reload` also spawns a fresh child interpreter via `multiprocessing.spawn`, which re-reads `PYTHONIOENCODING` from the environment at startup rather than inheriting the parent's already-reconfigured streams.
  2. **Root cause of the residual crash:** `backend/main.py` creates a `logging.handlers.RotatingFileHandler("blast.log", ...)` with no `encoding=`/`errors=` argument. Python opens files with the platform's locale-preferred encoding (`cp1252` on Windows) and **strict** error handling by default — unlike `sys.stderr`, which Python already defaults to `errors="backslashreplace"`. So even with console stdio fixed, the file handler alone still raised on any non-ASCII character.
- **Fix:** `backend/run_api.py` calls `_force_utf8_io()` before importing `uvicorn` (sets `PYTHONIOENCODING=utf-8:backslashreplace` / `PYTHONUTF8=1` env vars plus `sys.stdout`/`stderr.reconfigure(...)`) to cover console output. `backend/main.py`'s `RotatingFileHandler` now passes `encoding="utf-8", errors="backslashreplace"` explicitly to cover the log file. Verified by actually starting the app (`scripts/Start-NovaApi.ps1`) after each change — the first fix alone still crashed; both together started clean. `tools/course_memory/recall.py` now also reconfigures its own stdout/stderr before printing arbitrary Obsidian or Pinecone content; replacing one literal arrow was insufficient because retrieved notes can contain any Unicode character.
- **Keywords:** UnicodeEncodeError, charmap codec, cp1252, Windows console encoding, PYTHONIOENCODING, PYTHONUTF8, uvicorn --reload multiprocessing spawn, stdout reconfigure, RotatingFileHandler encoding, logging FileHandler default encoding strict errors

## 2026-07-10 — pytest collection SyntaxError "source code string cannot contain null bytes"

- **Symptom:** `py -3 -m pytest backend/tests/test_ibkr_safety.py` failed at collection with `SyntaxError: source code string cannot contain null bytes`, even though the test file itself had no syntax errors.
- **Cause:** `backend/tests/__init__.py` was created via PowerShell `'' | Out-File 'backend/tests/__init__.py'`, which defaults to **UTF-16 with BOM** encoding on Windows PowerShell. Python's import machinery reads `.py` files as UTF-8/ASCII by default, so the UTF-16 null bytes between characters were interpreted as literal null bytes, breaking the package import before the test module itself was even reached.
- **Fix:** Rewrote `backend/tests/__init__.py` using the `Write` tool (which writes plain UTF-8, no BOM) instead of PowerShell `Out-File`/`echo` redirection.
- **Keywords:** SyntaxError, null bytes, pytest collection error, UTF-16 BOM, PowerShell Out-File, __init__.py encoding, Windows

## 2026-05-04 — GitHub Actions invalid workflow due to secrets in job conditional

- **Symptom:** GitHub Actions Check Suite failed immediately with "Invalid workflow file... Unrecognized named-value: 'secrets'". The deploy didn't trigger in Railway.
- **Cause:** GitHub Actions does not allow accessing `secrets.*` within job-level `if` conditionals. The expression `secrets.RAILWAY_TOKEN != ''` caused a parsing error that failed the entire workflow before any jobs could run.
- **Fix:** Removed the secret check from the job's `if` condition in `.github/workflows/deploy.yml`. Instead, moved the check into the `Deploy backend service` bash step, where it verifies `[ -z "$RAILWAY_TOKEN" ]` and safely exits if the token is omitted.
- **Keywords:** GitHub Actions, Invalid workflow file, Unrecognized named-value: 'secrets', job conditional, deploy.yml
## 2026-04-28 — Empty gapper list after server restart (SIP feed not supported)

- **Symptom:** No gappers appeared after starting the backend despite many market gaps. Logs showed: `Alpaca WS auth failed: code 409, 'insufficient subscription'` (repeating), `avg_volume bars API returned 403: "subscription does not permit querying recent SIP data"`, `HOD Momo enrichment: snapshot fetch returned empty`. `gappers-2026-04-28.json` contained `{"gappers": []}`.
- **Cause:** `_get_feed()` defaulted to `"sip"` (hardcoded fallback) when `ALPACA_DATA_FEED` was not set in `.env`. The user's Alpaca account only supports the IEX (free) feed, so all SIP REST calls got 403 and the SIP WebSocket got 409 — resulting in zero data.
- **Fix:** Changed default to `"iex"` via `DATA_FEED_DEFAULT` in `constants.py`. Added auto-fallback (`_try_fallback_to_iex()`) triggered on 403 REST and 409 WS errors. Added UI Settings dropdown for feed selection. Set `ALPACA_DATA_FEED=iex` in `.env`.
- **Keywords:** gappers empty, SIP, IEX, 403, 409, insufficient subscription, data feed, ALPACA_DATA_FEED, fallback

## 2026-04-23 — GitHub Actions “Backend tests” exit 5 with no tests

- **Symptom:** `CI / Deploy` failed on **Backend tests** with “Process completed with exit code 5”; **Frontend build** passed; **Deploy to Railway** skipped.
- **Cause:** `pytest` exits **5** when no tests are collected. The workflow intended to treat 5 as success, but GitHub’s `bash` runs with **`set -e`**, so the shell exited as soon as `pytest` returned 5—before `PYTEST_EXIT=$?` and the `if` ran.
- **Fix:** Run pytest under `set +e`, capture `$?`, then `set -e` and branch on 5 vs other codes.
- **Keywords:** GitHub Actions, pytest, exit code 5, set -e, errexit, no tests collected

## 2026-04-23 — Railway “Wait for CI” skipped frontend; GitHub Actions failed

- **Symptom:** Frontend deployments **SKIPPED** with “CI check suite failed”; backend kept updating; latest UI commits never went live.
- **Cause:** `frontend/scripts/check-railway-api-base.mjs` treated **any** environment with `RAILWAY_PROJECT_ID` as a Railway build. That variable is sometimes copied into **GitHub Actions** repo/org variables; GitHub runners are not Railway, and `VITE_API_BASE_URL` is often unset there → `prebuild` exited 1 → `frontend-build` job failed.
- **Fix:** Require `RAILWAY_PROJECT_ID && !GITHUB_ACTIONS` for the strict check; add a bash default `VITE_API_BASE_URL` in `.github/workflows/deploy.yml` for the build step.
- **Keywords:** Wait for CI, GitHub Actions, RAILWAY_PROJECT_ID, prebuild, frontend-build, skipped

## 2026-04-23 — HOD Momo tab still invisible after tab-bar `overflow-x: auto`

- **Symptom:** Production showed only Gappers / Movers / After Hours / Catalysts; **HOD Momo** never appeared even after adding horizontal scroll on `.tab-bar`.
- **Cause:** `.tab-spacer { flex: 1 }` sat between the tab buttons and “updated … ago” in the **same** flex row. The spacer kept absorbing free space in a way that blocked a proper `min-width: 0` scroll region, so the fifth tab stayed clipped.
- **Fix:** Wrap only the tab `<button>`s in `.tab-bar-scroll` (`flex: 1; min-width: 0; overflow-x: auto`); keep the scan-age as a sibling with `flex-shrink: 0`; remove `.tab-spacer`.
- **Keywords:** HOD Momo, tab bar, flex, overflow, tab-spacer, clipped

## 2026-04-23 — Railway frontend “unreachable” while `/config.json` returned 200

- **Symptom:** Backend healthy; frontend still disconnected; fetching `/config.json` on the frontend host returned HTTP 200 but HTML, not JSON.
- **Cause:** Static hosting SPA fallback served `index.html` for unknown paths when `config.json` was absent from `dist` (postbuild skipped or file not deployed). Bootstrap treated the failed JSON path as failure and fell back to `http://localhost:8000`.
- **Fix:** Inject `<meta name="nova-api-base">` at Vite build from `process.env.VITE_API_BASE_URL`; read meta first in `resolveApiBase`. Validate `/config.json` bodies look like JSON before parsing.
- **Keywords:** Railway, static, SPA fallback, config.json, VITE_API_BASE_URL, localhost, CORS

## 2026-04-23 — `/api/health` stuck at `{"status":"loading",...}` on Railway

- **Symptom:** Hitting the deployed `/api/health` always returned `loading` with `latency_ms: 0`; UI appeared broken; browser console empty for that symptom.
- **Cause:** `_cached_health` defaults to `loading` and is only updated by `_ping_health()` (Alpaca `/v2/account`). Lifespan called `_ping_health` only when `_alpaca_headers()` was non-`None`. With **no** `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` in the Railway Backend environment, the ping never ran and scans returned early without updating health.
- **Fix:** If credentials are missing at startup, set `_cached_health` to `error` with a clear message and `logger.warning(...)`.
- **Keywords:** health, loading, APCA_API_KEY_ID, APCA_API_SECRET_KEY, Railway, Alpaca, lifespan

## 2026-04-23 — Production UI “backend unreachable” (follow-up: Vite inlining missing)

- **Symptom:** After setting `VITE_API_BASE_URL` on Railway, the hosted UI still showed “Backend unreachable”; the production JS bundle still referenced `http://localhost:8000` only.
- **Cause:** Some Railway frontend builds did not substitute `import.meta.env.VITE_API_BASE_URL` into the emitted chunks even when the variable existed in the dashboard (stale asset hash `index-B-3w0dfo.js` unchanged), so the browser never called the real backend URL.
- **Fix:** Emit `dist/config.json` in `postbuild` from `VITE_API_BASE_URL` / `NOVA_API_BASE`, and resolve the API base in `main.tsx` before loading `App` (fetch `/config.json` when Vite did not inline). `constants.ts` prefers `window.__NOVA_API_BASE__` from that bootstrap.
- **Keywords:** Railway, Vite, VITE_API_BASE_URL, config.json, runtime bootstrap, backend unreachable, localhost

## 2026-04-23 — Production UI “backend unreachable” while Railway backend is healthy

- **Symptom:** Hosted frontend on Railway stayed on loading then showed disconnected / “Backend unreachable”; `curl` to the backend `/api/health` and `/api/gappers` returned 200. Downloaded production `assets/index-*.js` still contained `localhost` / `:8000`, not the Railway backend hostname.
- **Cause:** `VITE_*` variables are inlined at **Vite build time**. Setting `VITE_API_BASE_URL` in the Railway dashboard without a **new** frontend build left the old bundle. Optional: GitHub Actions was configured for `main` only while the repo default branch is `master`, so “wait for CI” could block or never align with pushes.
- **Fix:** Documented behavior via a `prebuild` script that exits non-zero on Railway when `VITE_API_BASE_URL` is unset. Extended `.github/workflows/deploy.yml` to `main` and `master` (including the deploy job condition). Operators must **Redeploy** the Frontend service after setting or changing the variable.
- **Keywords:** Railway, Vite, VITE_API_BASE_URL, build time, CORS, backend unreachable, localhost, Wait for CI, master branch

## 2026-04-16 — Railway Railpack “could not determine how to build” on monorepo root

- **Symptom:** Railway build failed with Railpack: `Script start.sh not found`, `Railpack could not determine how to build the app`, and the analyzed tree showed the full repo (`.cursor/`, `backend/`, `frontend/`, etc.) with no Python at the service root.
- **Cause:** Default builder Railpack only inspects the configured build root. With **Root Directory** left at the repo root, there is no `requirements.txt` or `pyproject.toml` at `./` (Python lives under `backend/`). The old `backend/railway.toml` alone is not applied unless the service points “Config as code” at `/backend/railway.toml`, and `builder = "nixpacks"` is ignored when the platform defaults to Railpack.
- **Fix:** Added a **root `railway.toml`** that sets `builder = "DOCKERFILE"` and `dockerfilePath = "Dockerfile"`, plus a **root `Dockerfile`** that `COPY backend/` and runs uvicorn on `$PORT`. Added **`backend/Dockerfile`** and switched **`backend/railway.toml`** to the same Docker builder for deployments where Root Directory is `backend`. Added **`.dockerignore`** to shrink build context.
- **Keywords:** Railway, Railpack, monorepo, Dockerfile, root directory, Nixpacks, build failed, start.sh

## 2026-04-16 — Volume frozen in scanner lists and ticker detail panel despite continuous data loading

- **Symptom:** Volume column in gapper/mover tables never updated while price changed in real time. Ticker detail panel "Volume" field also stuck at the value fetched on initial load. Zero-volume tickers showed `—` instead of `0`.
- **Cause:** (1) `_handle_trade()` only read `S` (symbol) and `p` (price) from the Alpaca trade WS message, discarding `s` (trade size). (2) `_broadcast_trade_update()` payload had no volume field, so ticker-detail WS clients never received updated volume. (3) `fmtVolume()` used `if (!v)` which treats `0` as falsy.
- **Fix:** `_handle_trade` now extracts `size = int(msg.get("s") or 0)` and adds it to the `volume` field of every updated cache entry (gapper, after-hours, gainer, loser). `_apply_trade_to_mover_list` accepts a `size` param and accumulates it. `_handle_trade` returns the new cumulative volume. `_ws_stream_loop` passes that to `_broadcast_trade_update`, which now includes `volume` in its JSON payload. Frontend `TickerTradeUpdate` interface gains `volume: number | null`; the `trade_update` handler updates `daily_bar.volume` and recomputes `rel_volume` accordingly. `fmtVolume` changed to `if (v == null)`. Drift from WS gaps self-heals via the existing periodic `_fetch_snapshots` scan loop.
- **Keywords:** volume, fmtVolume, _handle_trade, _broadcast_trade_update, trade size, real-time, accumulate, daily_bar, TickerTradeUpdate, rel_volume

## 2026-04-16 — Gapper gap % wrong during pre-market (using day-before-yesterday close)

- **Symptom:** Pre-market gapper table showed inflated gap percentages (e.g., BIRD +432% instead of -22%). Stocks with a large yesterday move appeared as massive gappers even if they were gapping DOWN in pre-market. Stock quote panel also showed wrong change % vs previous close.
- **Cause:** Alpaca snapshot `prevDailyBar` semantics differ by session. During pre-market (before 9:30 ET), `dailyBar` = yesterday's completed regular session bar, and `prevDailyBar` = the session before that (two days ago). The code always used `prevDailyBar.c` as "previous close" regardless of session, so during pre-market it computed gap vs the wrong reference (two days ago vs yesterday).
- **Fix:** Added `_pick_prev_close(snap)` helper in `backend/main.py` that inspects `dailyBar.t` (the bar timestamp). If the bar's date in ET is before today, `dailyBar` is yesterday's close and is returned. Otherwise returns `prevDailyBar.c`. Updated `_compute_gappers()` and `_run_focus_scan()` to use this helper. Updated `_fetch_ticker_snapshot()` to expose `prev_close`, `session_close`, `session_prev_close` fields. Frontend `TickerDetailContent` now uses `snap.prev_close` and shows a Webull-style two-line quote (main line = last regular-session close, sub-line = Pre:/After: with extended-hours price and change vs session close) during pre-market/after-hours.
- **Keywords:** gapper, prev close, prevDailyBar, dailyBar, pre-market, gap percent, Alpaca snapshot, bar timestamp, session close, two-line quote, pre-market quote

## 2026-04-15 — Quote side panel flashes empty / “screen disappears” on ticker click

- **Symptom:** Clicking a scanner row to open a quote briefly blanked the side panel or showed “No data found” before the spinner or quote appeared.
- **Cause:** After `selectedSymbol` updates, React renders **once before** the WebSocket `useEffect` runs. In that frame `loading` and `refreshing` were still false and `detail` was null, so the UI matched the **empty-state** branch (`!loading && !refreshing && !detail && selectedSymbol`). Runtime logs (`panel_branch` with `showEmpty: true` then `showSpinner: true`) confirmed the ordering.
- **Fix:** Treat that pre-effect gap as loading: `awaitingPreEffectFrame = selectedSymbol && !detail && !loading && !refreshing && !fetchFailed`, and `showFullSpinner = loading || awaitingPreEffectFrame`. Show “No data found” only when `fetchFailed` is set after a real WS close/error without an `initial` message (not StrictMode cleanup).
- **Keywords:** side panel, ticker click, flash, empty state, useEffect ordering, WebSocket, quote, StrictMode

## 2026-04-15 — After-hours tab: strong ticker missing despite large move (e.g. MAMO)

- **Symptom:** A symbol looked like a clear after-hours mover (large % change, volume) but never appeared on the After Hours list / tab count stayed low; manual Alpaca snapshot showed a large move vs `dailyBar.c`.
- **Cause:** The gap math and 10% threshold were fine. Alpaca’s `/v2/assets/{symbol}` can return **`tradable: false`** for an otherwise active listing (e.g. `overnight_halted` while another mover like AREB stays `tradable: true`). The scanner only requested snapshots for symbols passing **`tradable`** in `_get_tradable_symbols`, so those names were never scanned.
- **Fix:** Added `SCAN_REQUIRE_TRADABLE` (default `True`) and env **`BLAST_SCAN_REQUIRE_TRADABLE`** (`true`/`false`) so operators can include non-tradable active listings when needed; documented in `constants.py`.
- **Keywords:** after hours, MAMO, tradable false, Alpaca assets, scan universe, overnight_halted, BLAST_SCAN_REQUIRE_TRADABLE

## 2026-04-15 — Alpaca WS “connection limit exceeded” (406) and stale live prices

- **Symptom:** Scanner UI did not update second-by-second; backend log showed repeated `Alpaca WS auth failed` with `code: 406`, `msg: 'connection limit exceeded'`. Sometimes two “connecting” lines appeared close together in `blast.log`.
- **Cause:** `uvicorn --reload` without the `watchfiles` package falls back to **StatReload**, which ignores `--reload-exclude`. The rotating log (`backend/logs/blast.log`) and disk cache (`backend/.cache/`) changed frequently; each change restarted the worker. Overlapping processes each tried to open Alpaca’s market-data WebSocket; Alpaca allows **one** concurrent WS per API key, so new workers got 406 until slots cleared. Multiple long-lived terminals could also leave several backends running at once, making the limit worse.
- **Fix:** Add `watchfiles` to `backend/requirements.txt` so reload exclusions apply; pass `--reload-exclude logs --reload-exclude .cache` in `Run Stock Alert.bat`; keep `ALPACA_WS_BACKOFF_CAP` at 60s to avoid hammering reconnects. When debugging, kill **all** `python3.13` / uvicorn workers (not only `py.exe`) and avoid running several API instances in parallel.
- **Keywords:** Alpaca, WebSocket, 406, connection limit exceeded, uvicorn reload, StatReload, watchfiles, reload-exclude, blast.log, .cache, gappers.json, live data, stale

<!-- (New entries go above this comment; keep newest at top.) -->
