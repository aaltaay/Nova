# 2026-07-23 — AH sticky bridge-error fix + Former Momo watchlist bloat diagnosis

- **Status:** completed (bridge-error fix); diagnosed, awaiting user decision (Former Momo list size)
- **Agents:** parent
- **Domain:** market-feed / hod-momo
- **Related:** `CHANGELOG.md` § 2026-07-23 "Fix AH scanner sticky bridge-error banner never clearing" · `PROBLEM_LOG.md` §§ 2026-07-23 (two entries, same day as the WLDS active-set fix)

## Task

User pointed at a live Integrity banner screenshot after the earlier WLDS active-set fix and asked "seriously, what about these now?" — three still-visible symptoms: a `scanner_ibkr_bridge` error stuck at "(4165s ago)" and climbing, `hod_surge_after_seed` warning growing (10→13), and an `Uncovered (watched, not live)` list of symbols including ones the user has watched roll in after-hours.

## Goal

For each symptom: determine whether it is a real bug, a benign/expected signal, or a data problem — and fix whichever is safely fixable without destroying user data.

## Why it mattered

The user had just been told the WLDS-lockout cache bug was fixed, then immediately saw the banner still red. Distinguishing "still broken" from "different pre-existing issue" mattered for trust in the fix, and for deciding what (if anything) needs further action.

## What we changed

- `backend/scanner_runners/afterhours.py`: both `run_afterhours_discovery_scan()` and `run_afterhours_focus_scan()` now clear `state.ibkr_bridge_last_error` on a successful IBKR-sourced scan, matching the existing `movers.py`/`discovery.py` pattern.
- `backend/tests/test_scanner_runners_afterhours.py` (new): regression tests for both clear-on-success paths.
- `PROBLEM_LOG.md` / `CHANGELOG.md`: two new entries — the sticky-bridge-error fix, and a diagnosis-only entry for the Former Momo list bloat (data issue, not touched).

## How it works now

`state.ibkr_bridge_last_error` is set by `ibkr_bridge.run_ibkr()` on any bridge exception and stays set until a caller explicitly clears it — there is no automatic expiry. Every scanner runner that re-polls IBKR on a cycle (`movers.py`, `discovery.py`, now `afterhours.py`) must clear it on its own successful cycle, or a single transient timeout from early in the session paints the Integrity banner red/amber for the rest of the process's life regardless of how healthy the feed is afterward.

Separately (diagnosed, not fixed): Strategy #1's `former_momo_list` (`backend/.cache/hod-momo-config.json`) has 433 entries, not the small hand-curated watchlist the feature assumes. `former_momo_priority_symbols()` preserves list order, and `hod_momo_active.build_active_set()` admits priority symbols before any table-ranked row — so only the first ~39 entries in file order ever win one of the 40 active-set slots. WLDS is actually already in the list (~position 420) but can never win a slot at that position. This is the real mechanism behind the "39 former_momo priority slots, 1 live-mover slot" finding from the earlier WLDS fix's follow-up note — the earlier note assumed 39 was the list's true size; it is not.

The `hod_surge_after_seed` warning (9-13 symbols with empty 5-minute surge window despite a completed one-shot historical seed) was investigated but not changed: `hod_momo_market.seed_price_buffer()` unconditionally calls `mark_surge_seed_attempted()` at the end regardless of whether bars came back, so `surge_seeded_count` correctly tracks "attempted," and the None count reflects a mix of genuinely illiquid symbols (IBKR HMDS "no data", e.g. `SFWL`) and `503 interactive chart has priority` contention (e.g. `BIYA`, `MODD`) — pre-existing, `warn`-only (never blocks alerts while the tape is alive), and not part of this session's fix.

## Why this approach

- **Bridge-error clear:** mirrored the exact pattern already used by `movers.py`/`discovery.py` rather than inventing a TTL-based auto-expiry for `ibkr_bridge_last_error`. A per-label clear-on-success keeps the signal meaningful ("this label's *last* attempt succeeded") without adding a timeout constant someone has to tune; a blanket TTL would either fire too early (masking a real ongoing outage as "just old") or too late (same staleness bug, just bounded).
- **Former Momo list:** diagnosed but deliberately **not** auto-pruned. `update_config()`'s existing 40-symbol guard already stops the list from growing further through the UI, so there is no active bleeding to stop. Deleting ~390 entries from a config the user edited (however it got that large) is destructive and irreversible from the agent's side — the right owner of "which symbols matter" is the user, not a guess based on which tickers "look like" penny stocks. Reporting the mechanism (list-order-wins, capacity=40) plus the exact size gives the user what they need to decide: reset to default, hand-pick a short list, or ask for a capacity-floor reservation for live movers regardless of Former Momo size.
- **Surge-after-seed:** left as a `warn`-only signal rather than adding retry logic. The existing design is intentionally one-shot per symbol per session (avoids hammering IBKR's historical-data rate limits for names that will never have exploitable data, e.g. dead/no-print symbols); a smarter retry-with-backoff would trade a rare, non-blocking cosmetic warning for a new class of "silently re-fetching stale historical data forever" bug risk. Investigated deeply enough (found the real `seed_price_buffer` mark-as-attempted call site, ruled out a "silent success without marking" bug hypothesis) to be confident this is expected behavior, not a regression.

## Verification

- `py -3 -m pytest tests/test_scanner_runners_afterhours.py -v` — 2 passed (new regression tests for both AH clear-on-success paths).
- `py -3 -m pytest -q` (full backend suite) — 931 passed.
- Live: confirmed via `backend/logs/api-console.log` that `AH discovery (IBKR): source=ah_scan raw=50 rows=14`-style successes kept landing every cycle while `scanner_ibkr_bridge` stayed stuck and climbing (4165s → 5436s), proving the bug reproduces exactly as diagnosed.
- Live: confirmed `former_momo_list` has 433 entries via `GET /api/hod-momo/config`, cross-checked against `priority_reasons` in `GET /api/hod-momo/debug/integrity` (39/40 active slots = `former_momo`).
- **Not yet verified live-in-process:** the running dev API (pid 51892, started 18:07 ET, `NOVA_API_RELOAD=1`) did not pick up the `afterhours.py` edit via hot-reload after ~80s of waiting — no second `Started server process` line appeared in `api-console.log`. The Afterhours table also froze for the session at 20:00:00 ET (ADR 008) moments after the edit, so no further AH discovery/focus scans will run today regardless. The fix is correct and tested in isolation; it needs either a backend restart or tomorrow's AH session to be observed clearing the live banner.

## Follow-ups

- **User decision needed:** what to do with the 433-entry `former_momo_list` (reset to default `["SPRC"]`, hand-pick a short list, or request a capacity-floor design so live movers always get a minimum number of active-set slots regardless of Former Momo size).
- Investigate separately (not blocking) why this dev backend's `--reload` did not restart on a source-file save; confirm `watchfiles` file-system events are actually reaching uvicorn's watcher in this environment. Not chased further this session since it did not block shipping the fix.

## Keywords

ibkr_bridge_last_error, scanner_ibkr_bridge, afterhours.py, sticky integrity error, former_momo_list, 433 symbols, priority_reasons, build_active_set, WLDS, hod_surge_after_seed, seed_price_buffer, mark_surge_seed_attempted, uvicorn reload not picking up changes
