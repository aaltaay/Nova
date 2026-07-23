# 2026-07-23 — Fix HOD active-set stale cache (WLDS lockout)

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo (HOD Momo scanner data-quality)
- **Related:** `CHANGELOG.md` §2026-07-23 "Fix HOD active-set stale cache..." · `PROBLEM_LOG.md` §2026-07-23 "HOD active-set stale cache permanently excluded symbols admitted after freeze (WLDS lockout)"

## Task

User asked why WLDS — a stock they could see "rolling high in afterhours" (+104% change, RVOL 5743x) — never showed up in the HOD Momo alert system. Investigation traced this to a stale caching bug in the active-set builder; the user then approved a three-part plan (remove the stale cache, surface a silent seed-failure log, persist session highs across restarts) and asked for it to be implemented end to end.

## Goal

`refresh_hod_active_set()` must never return a permanently stale snapshot once scanner tables freeze for the day. A failed one-shot historical seed must be visible in logs. `session_highs`/`day_highs`/`session_high_source`/`session_high_seeded` must survive a backend restart within the same ET trading session.

## Why it mattered

Silently locking a live, actively-moving symbol out of every HOD strategy — with no error, no log line, and a debug endpoint that still showed live-looking price data — is exactly the kind of failure that erodes trust in the alert engine: the user has no way to know an alert *should* have fired but structurally couldn't. Separately, losing already-correct high-of-day truth on every dev `--reload` meant the engine kept re-doing work it had already done correctly, and briefly evaluated symbols against a wrong (zero/unseeded) floor after each restart.

## What we changed

- `backend/ibkr_bridge.py` — `refresh_hod_active_set()` no longer memoizes on an `id()+len()` signature of the three scanner-table caches; it always calls `hod_momo_active.build_active_set(...)` fresh. Deleted `_hod_active_cache`, `_hod_active_cache_sig`, the `force=` parameter, and `invalidate_hod_active_cache()`.
- `backend/hod_momo_session_focus.py` — removed `_invalidate_active_cache()` and its call site (pointless once there is no cache to invalidate).
- `backend/hod_momo_surge_seed.py` — the "no usable bars" one-shot seed-failure log is now `logger.warning` instead of `logger.debug` (was suppressed by the `INFO` root logger).
- `backend/hod_momo_state.py` — added `highs_dirty` / `last_highs_save_mono` fields (same shape as the existing alert-save dirty-flag pair).
- `backend/constants_hod_momo.py` — added `HOD_MOMO_HIGHS_PREFIX`.
- `backend/cache.py` — added `save_hod_momo_highs()` / `load_hod_momo_highs()`, modeled directly on the existing dated alert-snapshot pair (atomic write, date-guarded read, discarded if stale).
- `backend/hod_momo_persist.py` — added `save_highs()` / `flush_pending_highs_save()` / `_load_highs_from_disk()`; wired the load into `load_persisted_state()`.
- `backend/hod_momo_high.py` — `apply_session_high()` now calls the new throttled persist on every high update.
- `backend/hod_momo_alerts.py` / `backend/hod_momo.py` / `backend/app_lifespan.py` — wired `flush_pending_highs_save()` into the 1s consolidation loop and the shutdown flush, alongside the existing alert flush.
- Tests: new regression test in `test_ibkr_bridge.py` proving a symbol appended in-place to an unchanged-`id()` cache is still admitted; removed the now-dead `_invalidate_active_cache` monkeypatch from `test_hod_momo_session_focus.py`; new highs-persistence tests in `test_hod_momo_persist.py` and `test_cache_error_visibility.py`.

## How it works now

`build_active_set()` is a pure, in-memory merge/rank/dedupe over at most ~40-70 small dict rows (Gappers + Gainers + Afterhours + pinned Former Momo) — no IBKR call, sub-millisecond. It is cheap enough to run unconditionally on every L1 tick, so there is no cache to go stale: whatever the three table caches currently contain is exactly what gets evaluated, every time, including after ADR 008 freezes them for the rest of the session. Session-high truth persists the same way alerts already did — a throttled dirty-flag write to a dated JSON file under `backend/.cache/`, gated on the same 04:00-ET-anchored session key `cache.py` already uses for alerts, reloaded on `load_persisted_state()` only if that file's stored date matches today's session (a real new day still starts fresh via the existing midnight-ET session-rollover reset in `hod_momo_session.py`).

## Why this approach

Memoization here was solving a problem that didn't exist: `build_active_set` was already cheap enough to call on every tick, so the "cache" only ever bought staleness risk with no real performance benefit — deleting it outright (rather than fixing the invalidation logic, e.g. switching to a TTL or a deep content hash) is strictly simpler and removes an entire class of "did the signature actually change" bugs. A TTL-based cache was considered and rejected: HOD active-set membership needs to react immediately to a real roster change, not wait out a fixed window, and once ADR 008 freezes a table, a TTL cache would just re-derive the exact same stale snapshot forever anyway — a TTL does not fix an underlying signature that stops changing. For the seed-failure visibility, retry logic (2-3 attempts) was explicitly rejected by the user in favor of the simplest fix: the active-set repair already means `on_trade_update` resumes for a previously-locked-out symbol, and IBKR's per-tick day-high tick (type 6) plus the surge buffer both self-heal from live ticks within minutes — a failed one-shot bar seed only needed to stop being invisible, not be retried. For highs persistence, we deliberately persist only the four small dicts/sets that represent settled truth (`session_highs`, `day_highs`, `session_high_source`, `session_high_seeded`) and explicitly leave `price_buffer` and `surge_seeded`/`pending_surge_seed` in-memory-only — those are larger, purely transient rolling buffers that already refill from live ticks within 5-10 minutes once the active-set fix restores ticks, so persisting them would add real serialization surface for comparatively little benefit.

## Verification

Full backend suite: `py -3 -m pytest -q` → 929 passed (a Windows-only torch/torchvision native-DLL stderr dump during `test_news_impact.py`'s first sentiment-pipeline import is pre-existing/unrelated — the test still passes). New/changed tests: `test_ibkr_bridge.py::test_refresh_hod_active_set_always_recomputes`, `test_hod_momo_persist.py::test_save_highs_rate_limited_and_flushed` + `test_session_highs_survive_a_restart`, `test_cache_error_visibility.py::test_load_hod_momo_highs_ignores_stale_prior_day_file` + `test_save_then_load_hod_momo_highs_round_trips`, and a fix to `test_hod_momo_session_focus.py` (removed a monkeypatch of the now-deleted `_invalidate_active_cache`). Live: hit the running dev API's `/api/hod-momo/debug/integrity` — `hod_active_set` reports `active=40/40` with quote-age p95/max of 0.6s, confirming the active set is being freshly recomputed and fully utilized in real time (previously, once tables froze, this would have been the same stale set for the rest of the session).

## Follow-ups

Live verification surfaced a **separate, pre-existing** issue, explicitly out of scope for this fix: WLDS is still excluded from the active set right now, not by the cache bug (confirmed gone) but because `build_active_set()` admits the manually-curated Former Momo priority list unconditionally *before* any table-ranked round-robin, and that list currently holds 39 of the 40 total capacity slots — leaving only 1 slot for all of Gappers+Gainers+Afterhours combined. Needs a separate decision: prune the Former Momo list, raise `HOD_MOMO_ACTIVE_SET_CAPACITY`, or reserve a minimum number of slots for live top movers regardless of priority-list size. Do not reopen the cache fix itself for this — it is verified working; this is a capacity/ranking tradeoff in a different function.

## Keywords

WLDS, refresh_hod_active_set, active-set cache, id len memoization, ADR 008 table freeze, session_highs persistence, hod_momo_surge_seed, Former Momo priority capacity crowd-out, hod_momo_persist, save_highs
