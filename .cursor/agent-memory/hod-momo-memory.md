# HOD Momo Parity Specialist memory (living)

Living knowledge for the Nova `hod-momo` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/hod-momo.md`

---

## Current snapshot

```yaml
captured_at: 2026-09-19T00:00:00Z
source_revision: migration
result: not-run
metrics: {}
blockers: []
dashboard_freshness: refresh-required
```



---

## How to continue improving

> Use the hod-momo subagent to continue HOD Momo parity

Or:

> Improve the hod-momo agent — work the next backlog item in `.cursor/agent-memory/hod-momo-memory.md`.

Durable facts get **promoted into `hod-momo.md`**. Run history, parity metrics, and the root-cause ledger stay **here**.

---

## IBKR API cheat sheet (memorize)

Promoted into `hod-momo.md` as a compact table (2026-07-17). Keep this expanded form here for teaching / recall.

### One-line memory chain

| Need | Call |
|------|------|
| Who's moving? | Scanner (`reqScannerData`) |
| What's the live price / day high? | Level‑1 (`reqMktData`) |
| Quick quote, don't stream? | `reqTickersAsync` |
| What was the high earlier today? | Historical bars (`reqHistoricalData`) |
| Book depth? | Level‑2 (`reqMktDepth`) |
| Every print? | Tick-by-tick (`reqTickByTickData`) |

### 1. `reqScannerData` / `reqScannerDataAsync` — "Who's on the list?"

- **Specialty:** Ranked membership only (gainers, losers, gappers, volume, AH movers).
- **Gives you:** Symbols + rank. **No prices.**
- **Limit:** ~50 contracts per scan code; max ~10 concurrent scanner subscriptions.
- **Nova modules:** `backend/ibkr/discovery.py`, `hod_momo_seed.py` / universe builders.
- **Codes (session-aware):** `TOP_PERC_GAIN` / `TOP_PERC_LOSE`, `TOP_OPEN_PERC_GAIN` (gappers), `TOP_AFTER_HOURS_PERC_GAIN` / `LOSE`, volume: `HOT_BY_VOLUME` / `TOP_VOLUME_RATE` / `MOST_ACTIVE`.

### 2. `reqMktData` — "Level‑1 live quote stream"

- **Specialty:** Continuous Level‑1: last, bid/ask, volume, **day high/low**.
- **Gives you:** Live updates (~250ms aggregation). Tick type **6 = day High**, **7 = day Low** (`ib_async`: `ticker.high` / `ticker.low`).
- **Limit:** ~100 concurrent lines (practical).
- **Nova modules:** `backend/ibkr/ticks.py`, `ibkr/scanner_l1.py` → `/ws/scanner` `price_patch`; open ticker quote; HOD `on_trade_update` ticks.
- **Not:** Depth ladder, not every print, not "who's a gainer."
- **HOD truth (planned):** use tick‑6 High + bar seed — never invent `session_highs` from first observed tick alone (`hod_momo_trade.py` cold-start bug).

### 3. `reqTickersAsync` — "One-shot snapshot"

- **Specialty:** Cold/slow snapshot for symbols you do not want to stream.
- **Gives you:** One quote when IB finishes (~11s to `tickSnapshotEnd`).
- **Nova use:** Discovery / enrichment only — **not** the hot table freshness SLA (that is `reqMktData`).

### 4. `reqHistoricalData` — "Bars / past candles"

- **Specialty:** OHLCV history (1‑min, etc.).
- **Gives you:** Bars; `useRTH=0` can include premarket/AH.
- **Nova modules:** `backend/ibkr/bars.py`, chart path; **seed session highs once** so HOD is not invented from first L1 tick.
- **Pacing:** serialize via `historical_gate` — do not fan out concurrent hist calls.

### 5. `reqMktDepth` — "Level‑2 ladder"

- **Specialty:** Bid/ask depth by size (order book).
- **Limit:** **Max 3** concurrent symbols; ~10 rows/side on SMART.
- **Nova modules:** `backend/ibkr/depth/*`. Open symbol Stock View only — **never** feed discovery or HOD gates.

### 6. `reqTickByTickData(AllLast)` — "Time & Sales"

- **Specialty:** Every last print as it happens.
- **Nova modules:** `backend/ibkr/tape_stream.py` → `/ws/ibkr/tape/{symbol}`. Open symbol only — **never** feed discovery or HOD gates.
- Guard: no second tick-by-tick for same instrument within ~15s.

### Invariants (agent must not violate)

1. **Scanner = membership; prices = L1.** Never infer price/HOD from scanner rank or arrival order.
2. **discovery=ibkr → IBKR only** for prices (no silent Alpaca mix) — `single-market-data-feed.mdc`.
3. **L2 / T&S = open-symbol side branch** — never HOD admission or strategy gates.
4. Canonical architecture note (**this agent owns**): `knowledge/obsidian/03-Nova-Decisions/IBKR-Scanner-HOD-Architecture.md` — registered in `registry.json` `canonical_inputs` + `writable_paths`. Companion plan diagrams: `hod_gate_uml_cleanup_*.plan.md` (not durable; Obsidian wins on conflict).

### 2026-07-17 — HOD truth + mute/burst fix shipped

- **Cold-start false HOD:** `hod_momo_high.py` seeds from bar `max(h)` + L1 tick-6; `high_unseeded` blocks `requires_hod` until seeded. Never invent from first last.
- **Mute off:** `HOD_MOMO_COOLDOWN_SEC=0`; consolidation **10s**; UI burst gap 10s.
- **Quiet re-eval removed** from heartbeat (amplified fake HOD).
- **Master RVOL retired** (strategy-level RVOL only); soft bypass deleted.
- Env `HOD_RAW_MODE=1` skips strategy float/RVOL/price gates for observability.

---

### 2026-07-17 — Former Momo intentionally OFF



### 2026-07-17 — Schema v5 (CNF) — do not re-litigate

CNF-class Squeeze without HOD was **persisted config**, not a formula bug. Schema v5 migrate + live repair: Squeeze 10/11 `requires_hod=True`; re-enable strategies 2–12; Former stays off. Historical CNF rows in the parity window may linger until they age out — that is not a new false-positive.

---

## Root-cause ledger

Session-over-session tracking so future runs don't re-diagnose a solved bug or re-attempt a failed fix. Seeded from `CHANGELOG.md`/`PROBLEM_LOG.md` "HOD Momo" entries on 2026-07-16 — verify against those files directly if a bucket looks stale.

### Fixed (verified, do not re-litigate)

| Date | Bucket | Symptom | Fix | Evidence |
|------|--------|---------|-----|----------|
| 2026-07-16 | `spam_cooldown` (root cause, not the heartbeat/consolidation band-aids below) | Persisted `master.cooldown_sec = 0.0` in `backend/.cache/hod-momo-config.json` (debugging leftover) defeated the per-`(symbol, strategy)` cooldown entirely — same symbol+strategy re-fired every 20-36s instead of once per 60s, ~12-24 new alert rows/30s even on a quiet AH tape | Restored `cooldown_sec` to `HOD_MOMO_COOLDOWN_SEC` (60.0) live; `hod_momo_persist._load_configs_from_disk` now self-heals any persisted `cooldown_sec < 1.0` back to default on every config load (with a loud warning) | PROBLEM_LOG 2026-07-16 "RVOL 700x-11000x blowup + alert spam despite 'fixed' prior session"; before/after: alert growth 12-24 rows/30s → 0 new rows/60s |
| 2026-07-16 | `rvol_formula` (multi-day runners) | `avg_volume` for symbols tracked across multiple sessions (CJMB, LBGJ) was fetched once and never refreshed (`request_fundamentals()` only re-fires while `float_shares`/`fifty_two_week_high` are still unknown) — froze at a days-old yfinance reading while cumulative volume kept growing, so pace RVOL = volume/avg_volume exploded | `hod_momo_heartbeat._maybe_refresh_fundamentals` re-queues `mark_needs_fundamentals` for every active symbol every `HOD_MOMO_FUNDAMENTALS_REFRESH_SEC` (300s) so `avg_volume` tracks yfinance's live figure instead of freezing at the first-ever fetch | PROBLEM_LOG 2026-07-16 same entry. Live before/after via `/api/hod-momo/debug/symbol/{SYM}` on a cleanly-restarted process: **CJMB RVOL 7016.02 → 46.49** (avg_volume now 288,855, matches a fresh yfinance query), **LBGJ RVOL 1526.36 → 10.38** (avg_volume 308,767) — see caveat below on the exact post-fix decimal |
| 2026-07-16 | `rvol_formula` (same-day movers, silent feed mixing) | `hod_momo_enrichment.universe_enrichment_loop`'s `discovery=ibkr` branch read Alpaca IEX-feed daily-bar averages (`state.avg_volume_cache`) *before* falling back to yfinance — IEX undercounts consolidated volume for thin microcaps by 100x+ (ATPC cached 13,620.44 vs. yfinance 3,375,816.00 — 248x off) and, running every 30s, kept re-clobbering any correct value fix #2 above would have supplied | Extracted `ibkr_avg_volume()` (yfinance-only, never reads `avg_volume_cache`) and used it exclusively in the ibkr branch of `universe_enrichment_loop`, matching the existing correct `fundamentals_enrichment_loop` path and the single-market-data-feed rule | PROBLEM_LOG 2026-07-16 same entry; **ATPC avg_volume 13,620.44 → 3,375,816.00** (matches live yfinance exactly) |
| 2026-07-16 | `spam_cooldown` | LBGJ Former `passed=True` but only Low Float alert appeared (consolidation dropped strategies) | `flush_consolidated_loop` now groups by `strategy_id`, one alert per strategy | PROBLEM_LOG 2026-07-16 "Consolidation dropped Former Momo when Low Float also fired" |
| 2026-07-16 | `l1_capacity` | LBGJ `would_fire_now` PASS but no alerts — dropped from L1 by top-gainer/seed active-set churn | Reserved `session_focus` active slots, Former-list-first priority | PROBLEM_LOG 2026-07-16 "Former Momo would_fire PASS but never alerts (off active set)" |
| 2026-07-16 | `l1_capacity` (root: note_quote starvation) | HOD banner Integrity fail, coverage 15%, quote/eval p95 ~2000-4000s, CJMB `(1179 in 2157sec)` burst badge | `hod_momo_heartbeat` 1Hz refresh on quiet active symbols; UI burst-gap 15s in `collapseAlertsBySymbol`; mode-aware scanner integrity; `session_gate`/`parity_observe` tools built | PROBLEM_LOG 2026-07-16 "HOD Integrity fail: active quote/eval ages ~hours on quiet L1" |
| 2026-07-16 | infra (table SLA, not HOD-specific but shares root) | `stale · updated Ns ago` despite Connected — `reqTickersAsync` structurally can't meet <3s SLA | Bounded persistent `reqMktData` L1 for active tab + reserved HOD pool (`ibkr/scanner_l1.py`) | PROBLEM_LOG 2026-07-16 "Scanner stale despite Connected (IBKR snapshot SLA impossible)" |
| 2026-07-17 | `l1_capacity` / integrity flap (explore poison) | Integrity FAIL coverage 85–98% with FRE/CRD missing or hours-old ages; `l1_err subscribe failed`; observe REFUSED while ticks otherwise flowing | `note_l1_subscribe_failed` 300s cooldown from scanner_l1; purge quote/eval ages on demotion; coverage fail floor 90% (98%→warn); session_gate/observe HTTP timeout 30s | PROBLEM_LOG 2026-07-17 "HOD integrity FAIL from L1-failed explore symbols"; live gate PASS(warn) + observe --once after reload |
| 2026-07-17 | infra (lifespan / event loop) | :8000 listens but `/docs` times out — IB Gateway 4001 up | Yield HTTP before IBKR; hard `wait_for` on `connectAsync`; recreate `IB()` on fail; default `IBKR_CLIENT_ID` 1→17 | PROBLEM_LOG 2026-07-17 "API listens but never serves"; unit tests `test_ibkr_client_connect.py` — live confirmed after restart |
| 2026-07-17 | `l1_capacity` / infra (spawn abort) | Post-restart integrity FAIL coverage ~42%; zero `owner=hod/scanner` L1 subs; Squeeze names enrichment-only with `surge:None` | `fills_poll_loop` typo → `fill_poll_loop`; per-task resilient spawn; scanner_l1 first | PROBLEM_LOG 2026-07-17 "HOD L1 never started"; post-fix active p95~0.8s; SDOT session_high live |
| 2026-07-17 | `gate_mismatch` (Squeeze vs master RVOL) | **TRT** (and later **PN**) Squeeze blocked by master_rvol before eval; pace RVOL math correct | Soft-block master_rvol for surge-only (`min_rvol=0` + surge window) | Live: PN gate=`master_rvol(0.05<2)` but Squeeze strategies still listed (surge cooled ~3.5%) |
| 2026-07-17 | `universe_gap` (seed crowding) | Mega-gainers fill uncapped TOP_PERC_GAIN top-50 | Second seed `TOP_PERC_GAIN(belowPrice=20)` | Seeds ~171–177; helps PN-class when they rank in sub-$20 top-50 |
| 2026-07-17 | `universe_gap` / `l1_capacity` (PN seed head) | PN on gainer table rank~36 but empty snap — seed_slots took HOT_BY_VOLUME head; losers + 8 Former slots crowded mid-tier under-$20 | `seed_symbols_for_active` + discovery gainer-rank; belowPrice-first scan; omit loser_rows; FORMER_SLOTS 8→2 | Live: PN `volume_seed` price=$4.44; tests in test_hod_momo_universe / test_hod_active_quota |
| 2026-07-17 | `l1_capacity` (TRT sticky) | TRT empty snap after leaving gainers; never Nova-alerted so not in session_focus; slots=2 | `hod_momo_session_focus` sticky on master_rvol soft-block; slots=8; sticky→alerts→Former | Live: TRT `session_focus` $10.67 rvol=0.31; do not sticky on every Squeeze eval (flood) |
| 2026-07-17 | `l1_capacity` (TRT sticky flood) | Sticky file 15 soft-blocks; TRT #15; only 8 L1 slots → empty snap post-restart | Cap sticky=8; cooled-first rank vs mover caches before truncate | Live: TRT $10.66 rvol=0.30; sticky `["ETS","BGDE","TRT",…]` |



### Running Up — evidence summary (2026-07-20)

| Source | What it says |
|--------|----------------|

### Still open (as of 2026-07-23 — post external survey)

| Bucket | Evidence | Notes |
|--------|----------|-------|
| infra / false mute (**P0**) | Merged integrity FAIL from `scanner_ibkr_bridge` TimeoutError → `integrity_fail_suppress` ≫ fires while HOD L1 green | PROBLEM_LOG 2026-07-23; fix not shipped |
| `timing_definition` (PN/TRT Squeeze) | PN + TRT on L1; Squeeze blocked by cooled surge / soft path open | Wait for live surge — not universe/L1. |
| Former | Disabled by default (schema v4); session_focus slots=8 for sticky/alerts (Former ranked last) | No fix budget. |
| integrity: `hod_surge_after_seed` | Soft WARN (10 seeded surge=None) | Non-blocking cold-start risk. |
| `nova_only` CNF (stale window) | Pre-v5 / off-widget Float names; SDOT Float vs Squeeze mismatch | Expect age-out; do not re-litigate / auto-label spam. |



| Source | What it actually says |
|--------|----------------------|


### Tried and failed (do not repeat blind)

| Date | Approach | Why it failed |
|------|----------|---------------|
| 2026-07-17 | `remember_session_focus` on every `on_trade_update` | Flooded sticky with all active movers; TRT evicted from top-40 within seconds |
| 2026-07-17 | Sticky on any Squeeze strategy eval (`blocked_by != disabled`) | Same flood — every ticker evaluates Squeeze 10/11 (hod/surge blocks) |
| 2026-07-17 | Sticky on Squeeze `surge:` near-miss | Hot movers constantly surge-block and prepend; still evicts cooled TRT |
| 2026-07-17 | Sticky max=40 with only 8 session_focus slots | Soft-block list grew to 15; TRT at #15 empty snap after restart — cap must equal slots + cooled-first rank |

### Open discrepancy — verify before quoting exact post-fix RVOL decimals

The task that requested this refresh quoted **CJMB RVOL 7016.02→1.06** and **LBGJ RVOL 1526.36→0.01** as the live verification numbers. The actual `PROBLEM_LOG.md` / `CHANGELOG.md` entries and `.tmp/hod-momo-parity/classify_latest.md` (all written by the fixing session itself) consistently record **CJMB 7016.02→46.49** and **LBGJ 1526.36→10.38** — not 1.06/0.01. The ATPC avg_volume figures (13,620.44→3,375,816.00) match exactly across all sources. This memory uses the **46.49/10.38 figures** because they are corroborated by three independent written artifacts from the fixing session vs. a single paraphrase; if a future run finds fresher evidence for 1.06/0.01 (e.g. a later heartbeat cycle further improved the reading), update this note with the new evidence rather than silently overwriting the number.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.



### Completed



---

## Known traps



---

## Run log

Newest first. Keep entries short. Cap at ~30 entries — delete the oldest half if longer.

<!-- RUN_LOG_START -->





### 2026-07-23 — Investigation: external HOD survey + live mute root cause



### 2026-07-20 — Separate Running Up UI tab from HOD Momo



### 2026-07-20 — VCIG late Squeeze = HOD retest (fixed new-high grace)



### 2026-07-17 — Fix #2b TRT sticky flood (cooled-first + cap=8)

- **Scope:** TRT empty again after sticky shipped — hot soft-blocks starved cooled L1.
- **Trace:** sticky file 15 names, TRT last; DRTS had L1; movers showed TRT COOLED.
- **Fix:** `HOD_MOMO_SESSION_FOCUS_MAX=slots(8)`; `_rank_sticky` cooled-before-hot.
- **Verify:** TRT $10.66 rvol=0.30 sh=$10.66; Former off; gate PASS(warn); pytest 14. No commit.

### 2026-07-17 — Fix #2 TRT sticky L1 (session_focus soft-block)

- **Scope:** Keep TRT-class cooled Squeeze names on active L1 (empty snap churn).
- **Trace:** TRT off movers/universe; session_focus only today_alerts with 2 slots; never Nova-alerted.
- **Fix:** `hod_momo_session_focus` day sticky; remember on master_rvol soft-block only; slots=8; sticky→alerts→Former.
- **Tried/failed:** sticky-on-every-tick and every-Squeeze-eval flooded list (see Tried and failed).
- **Verify:** TRT active session_focus price=10.67 rvol=0.31; gate PASS(warn); pytest 8 passed. No commit.

### 2026-07-17 — CNF false positive closed (schema v5); PN/TRT seed+RVOL remain timing-only



### 2026-07-17 — Fix #1 PN universe_gap: under-$20 seed head + upside movers



### 2026-07-17 — Follow-up fix: TRT RVOL soft-block + sub-$20 seed (PN admitted)











### 2026-07-17 — CRITICAL: API listen-but-not-serve (lifespan IBKR hang)



### 2026-07-17 — URGENT tick #2: L1-fail explore poison (FRE) → integrity FAIL → fixed



### 2026-07-17 — RTH critical re-arm (user: Nova not matching / want continuous 1:1)



### 2026-07-17 — Post-fix refresh (separate worker landed cooldown/RVOL/enrichment fixes)



### 2026-07-16 — Live Integrity fail banner triage (coverage 98% + surge_none)

- **Scope:** Diagnose UI Integrity fail (`hod_active_set` coverage=98%, `hod_surge_after_seed`, uncovered list). Diagnosis only — no code change.
- **Result:** mixed — uncovered = `capacity_expected` (not a bug); coverage=98% hard-fail = **real brittle regression/noise** that suppresses alerts; surge_none = WARN when tape alive (empty historical seed / window mismatch).
- **Evidence:** session_gate exit FAIL with `active=40/40 … coverage=98%`; `/api/integrity` moments later status=warn cov=100% q/e p95~0.56s; 16s resample stable warn; debug `integrity_fail_suppress=265`; code cannot produce active>capacity (`_take` hard-cap) — screenshot `active=42/40` likely approx/misread.
- **Learning:** Do not chase uncovered=N. Coverage need-100% fails on a single unquoted newly-admitted active symbol (39/40→98%). Quote/eval age gates already exist — coverage hard-fail is redundant and flaps under explore rotation.
- **Files updated:** `hod-momo-memory.md`, `agent-hod-momo.canvas.tsx`.

### 2026-07-16 — Agent install + memory seed



<!-- RUN_LOG_END -->
