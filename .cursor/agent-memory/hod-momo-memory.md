# HOD Momo Parity Specialist memory (living)

Living knowledge for the Nova `hod-momo` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/hod-momo.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-17T17:45:00Z
source_revision: local-uncommitted
result: PASS (warn) — TRT sticky cooled-first live
metrics:
  warrior_rows: 40
  nova_rows: 93
  both: 0
  warrior_only: 10
  nova_only: 37
  strategy_mismatch_symbols: 0
blockers: []
dashboard_freshness: clean
notes: "TRT sticky L1 price=10.66 rvol=0.30 after cooled-first+cap8. Sticky file now <=8. Former off. Squeeze warrior_only = timing/surge cooled."
```
Machine-readable block only. Update after material runs. Do not duplicate mutable truth that lives in canonical domain sources (`.tmp/hod-momo-parity/*`, `PROBLEM_LOG.md`, `CHANGELOG.md`).

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
4. Canonical architecture note: `knowledge/obsidian/03-Nova-Decisions/IBKR-Scanner-HOD-Architecture.md` + plan `hod_gate_uml_cleanup_*.plan.md`.

### 2026-07-17 — HOD truth + mute/burst fix shipped

- **Cold-start false HOD:** `hod_momo_high.py` seeds from bar `max(h)` + L1 tick-6; `high_unseeded` blocks `requires_hod` until seeded. Never invent from first last.
- **Mute off:** `HOD_MOMO_COOLDOWN_SEC=0`; consolidation **10s**; UI burst gap 10s.
- **Quiet re-eval removed** from heartbeat (amplified fake HOD).
- **Master RVOL retired** (strategy-level RVOL only); soft bypass deleted.
- Env `HOD_RAW_MODE=1` skips strategy float/RVOL/price gates for observability.

---

### 2026-07-17 — Former Momo intentionally OFF

User disabled Former Momo Stock (strategy 1) by default (schema v4). **Do not spend fix budget on Former warrior_only rows.** List still auto-remembers from other fires for a future fill path; re-enable only when user asks. Focus Squeeze → Float → Running Up.

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
| 2026-07-16 | `l1_capacity` + gate | Integrity p95 ~2.1s false-fail; Former Momo list empty vs Warrior; `/alerts` full-day 9k dump stalled observer | Heartbeat 0.5s/0.75s stale; Former Momo auto-remember + session bootstrap; `would_fire_now` aligned to real gates; `?limit=` on `/alerts` | PROBLEM_LOG 2026-07-16 "Integrity p95 ~2.1s false-fail + Former Momo empty vs Warrior" |
| 2026-07-16 | `l1_capacity` (root: note_quote starvation) | HOD banner Integrity fail, coverage 15%, quote/eval p95 ~2000-4000s, CJMB `(1179 in 2157sec)` burst badge | `hod_momo_heartbeat` 1Hz refresh on quiet active symbols; UI burst-gap 15s in `collapseAlertsBySymbol`; mode-aware scanner integrity; `session_gate`/`parity_observe` tools built | PROBLEM_LOG 2026-07-16 "HOD Integrity fail: active quote/eval ages ~hours on quiet L1" |
| 2026-07-16 | infra (table SLA, not HOD-specific but shares root) | `stale · updated Ns ago` despite Connected — `reqTickersAsync` structurally can't meet <3s SLA | Bounded persistent `reqMktData` L1 for active tab + reserved HOD pool (`ibkr/scanner_l1.py`) | PROBLEM_LOG 2026-07-16 "Scanner stale despite Connected (IBKR snapshot SLA impossible)" |
| 2026-07-14 | `universe_gap` + `rvol_formula` + gate | Nova watch set ≠ Warrior tape; RVOL was raw daily/avg not Warrior "Daily Rate" pace RVOL; master gate required +3%/5min on every strategy (blocked Medium Float grinds); Former Momo empty-list treated every symbol as former | IBKR HOT_BY_VOLUME/TOP_VOLUME_RATE/MOST_ACTIVE seeds; `market.pace_relative_volume`; master surge default 0 + schema v2; Former Momo requires non-empty list | PROBLEM_LOG 2026-07-14 "HOD Momo ≠ Warrior Day Trade Dash (wrong universe / RVOL / gates)" |
| 2026-07-17 | `l1_capacity` / integrity flap (explore poison) | Integrity FAIL coverage 85–98% with FRE/CRD missing or hours-old ages; `l1_err subscribe failed`; observe REFUSED while ticks otherwise flowing | `note_l1_subscribe_failed` 300s cooldown from scanner_l1; purge quote/eval ages on demotion; coverage fail floor 90% (98%→warn); session_gate/observe HTTP timeout 30s | PROBLEM_LOG 2026-07-17 "HOD integrity FAIL from L1-failed explore symbols"; live gate PASS(warn) + observe --once after reload |
| 2026-07-17 | infra (lifespan / event loop) | :8000 listens but `/docs` times out — IB Gateway 4001 up | Yield HTTP before IBKR; hard `wait_for` on `connectAsync`; recreate `IB()` on fail; default `IBKR_CLIENT_ID` 1→17 | PROBLEM_LOG 2026-07-17 "API listens but never serves"; unit tests `test_ibkr_client_connect.py` — live confirmed after restart |
| 2026-07-17 | `l1_capacity` / infra (spawn abort) | Post-restart integrity FAIL coverage ~42%; zero `owner=hod/scanner` L1 subs; Squeeze names enrichment-only with `surge:None` | `fills_poll_loop` typo → `fill_poll_loop`; per-task resilient spawn; scanner_l1 first | PROBLEM_LOG 2026-07-17 "HOD L1 never started"; post-fix active p95~0.8s; SDOT session_high live |
| 2026-07-17 | `gate_mismatch` (Squeeze vs master RVOL) | **TRT** (and later **PN**) Squeeze blocked by master_rvol before eval; pace RVOL math correct | Soft-block master_rvol for surge-only (`min_rvol=0` + surge window) | Live: PN gate=`master_rvol(0.05<2)` but Squeeze strategies still listed (surge cooled ~3.5%) |
| 2026-07-17 | `universe_gap` (seed crowding) | Mega-gainers fill uncapped TOP_PERC_GAIN top-50 | Second seed `TOP_PERC_GAIN(belowPrice=20)` | Seeds ~171–177; helps PN-class when they rank in sub-$20 top-50 |
| 2026-07-17 | `universe_gap` / `l1_capacity` (PN seed head) | PN on gainer table rank~36 but empty snap — seed_slots took HOT_BY_VOLUME head; losers + 8 Former slots crowded mid-tier under-$20 | `seed_symbols_for_active` + discovery gainer-rank; belowPrice-first scan; omit loser_rows; FORMER_SLOTS 8→2 | Live: PN `volume_seed` price=$4.44; tests in test_hod_momo_universe / test_hod_active_quota |
| 2026-07-17 | `l1_capacity` (TRT sticky) | TRT empty snap after leaving gainers; never Nova-alerted so not in session_focus; slots=2 | `hod_momo_session_focus` sticky on master_rvol soft-block; slots=8; sticky→alerts→Former | Live: TRT `session_focus` $10.67 rvol=0.31; do not sticky on every Squeeze eval (flood) |
| 2026-07-17 | `l1_capacity` (TRT sticky flood) | Sticky file 15 soft-blocks; TRT #15; only 8 L1 slots → empty snap post-restart | Cap sticky=8; cooled-first rank vs mover caches before truncate | Live: TRT $10.66 rvol=0.30; sticky `["ETS","BGDE","TRT",…]` |

| 2026-07-17 | `gate_mismatch` (CNF nova_only / Squeeze without HOD) | User: CNF never on Warrior HOD but Nova Squeeze 5%/10% fired. Live config had **only** strategies 10/11 enabled (Float/Running Up/52wk accidentally mass-disabled) and Squeeze `requires_hod=False`, so surge-alone fired without Warrior Small-Cap HOD Momentum semantics | Schema v5 (`HOD_MOMO_CONFIG_SCHEMA_VERSION=5`): migrate forces Squeeze 10/11 `requires_hod=True`; re-enables non-Former strategies; live API repair + `test_schema_v5_squeeze_requires_hod_and_reenables` | Live config verified 2026-07-17T17:21Z: 10/11 `requires_hod=True`; 2–12 `enabled=True`; Former off. **Do not re-diagnose CNF as rvol_formula / universe_gap.** |

### Still open (as of 2026-07-17T17:45Z — Warrior ts=1784308360)

| Bucket | Evidence | Notes |
|--------|----------|-------|
| `timing_definition` (SDOT Squeeze) | Cool surge/hod; Warrior peak ~$31 vs Nova session_high ~$27.6 | Document only unless Warrior re-fires. |
| `timing_definition` (PN/TRT Squeeze) | PN + TRT on L1; Squeeze blocked by cooled surge / soft path open | Wait for live surge — not universe/L1. |
| `capacity_expected` (BTMD) | Off Warrior widget; empty Nova snap; never in IBKR top-50 at +3.8% | Do not chase until it reappears/re-ranks. |
| Former | Disabled by default (schema v4); session_focus slots=8 for sticky/alerts (Former ranked last) | No fix budget. |
| integrity: `hod_surge_buffer` / `hod_surge_after_seed` | Soft WARN | Non-blocking cold-start risk. |
| `nova_only` CNF (stale window) | Still in parity window post-v5 | Expect age-out; do not re-litigate. |

| `nova_only` (sample) | CNF (pre-v5 stale) + off-widget Float names; SDOT Float vs Squeeze mismatch | Do not auto-label spam; CNF root cause closed. |

### Former Momo — evidence summary (for parent → user; do NOT invent Warrior formula)

| Source | What it actually says |
|--------|----------------------|
| Warrior UI (research snapshot) | Strategy **label** `"Former Momo Stock"` appears as a row strategy in Day Trade Dash HOD Momentum (same widget as Squeeze / Low|Medium Float). No published numeric formula in the widget. |
| BA101 Ch.12 Scanning 101 (`downloads/warrior-trading-caption-notes/BA101/chapter-12-scanning-101.md`) | Describes HOD Momentum as: new high-of-day + five pillars + recent % surge; Running Up omits HOD. Color guide mentions Former Momo as a **green strategy color band** ("All of the former Momo scanners are that same shade of green") — **label/UI grouping only**, not a closed-form equation. |
| Warrior agent memory | Same: BA101 five-pillar + surge for HOD; Former Momo appears in AH snapshots as a strategy name. No formula scraped. |
| Nova implementation (`backend/hod_momo_former.py`) | **Approximation, not a Warrior formula port:** explicit `former_momo_list` on strategy #1. Empty list → never fire. When any *other* strategy fires, `remember_former_momo(symbol)` appends the ticker; `bootstrap_former_momo_from_alerts()` heals from today's non-Former alerts. Gate = on list + normal HOD/RVOL strategy defaults (`min_rvol: 2.0`). Reserved `session_focus` L1 slots prefer Former-list order. |
| Hard rule | Never copy Warrior Former rows into `former_momo_list` / `on_trade_update`. |


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

- [x] **CRITICAL:** API listen-but-not-serve — lifespan/IBKR connect hang — fixed 2026-07-17 (deferred bootstrap + connect wall + clientId 17); parent must restart uvicorn.
- [x] **CRITICAL:** lifespan spawn typo `fills_poll_loop` aborted `scanner_l1` — fixed 2026-07-17 (`fill_poll_loop` + resilient spawn).
- [x] Live Warrior RTH snapshot refreshed (AMPG/BTMD/RAM/RFIL/SDOT/TRT) — classified 2026-07-17T17:10Z.
- [x] Live Warrior refresh ts=1784308360 (PESI/PN/VELO new) — Squeeze classified 2026-07-17T17:14Z.
- [x] **TRT master_rvol** — formula OK; Squeeze soft-bypass shipped 2026-07-17.
- [x] Sub-$20 TOP_PERC_GAIN seed pass (belowPrice=20).
- [x] **PN empty snap** — under-$20 gainer seed head + upside-only movers + former_slots=2 (2026-07-17T17:22Z live volume_seed $4.44).
- [x] **CNF nova_only false positive** — schema v5 Squeeze `requires_hod=True` + re-enable 2–12 (parent shipped; memory 2026-07-17T17:21Z).
- [x] **TRT sticky L1** — session_focus soft-block sticky; live $10.67 (2026-07-17T17:30Z).
- [x] **TRT sticky flood** — cooled-first + cap=8; live $10.66 (2026-07-17T17:45Z).
- [ ] SDOT Squeeze: mid-move admission + surge trough — only if Warrior re-fires.
- [ ] If BTMD-class miss while ranked outside IBKR top-50, consider HOT_BY_PRICE (capacity_expected until then).
- [x] L1-fail explore poison + coverage 98% hard-fail — fixed 2026-07-17 (cooldown + age purge + 90% floor).
- [ ] Independently re-verify the exact post-fix RVOL decimals for CJMB/LBGJ against a live `/debug/symbol` pull — resolve the 46.49/10.38 vs 1.06/0.01 discrepancy.
- [ ] Verify `test_hod_momo_persist.py` asserts the cooldown_sec floor-guard before adding a duplicate spam-rate test.

### Completed

- [x] 2026-07-17 — CNF false positive closed as schema v5 `gate_mismatch` (Squeeze without HOD + mass-disabled floats); PN seed + TRT soft-block already closed — remaining PN/TRT warrior_only = `timing_definition`.
- [x] 2026-07-17 — RTH feed re-diagnosis: overnight integrity FAIL → recovered PASS(warn); classified JSPR universe_gap + Squeeze timing + LBGJ RVOL gate with live `/debug/symbol`; documented Former Momo evidence (BA101 label-only vs Nova remember-list); re-armed observe loop `--interval 30`.
- [x] 2026-07-16 — Agent scaffolded via `tools/create_nova_agent.py`; root-cause ledger seeded from CHANGELOG.md/PROBLEM_LOG.md HOD Momo history so this agent starts with real context.
- [x] 2026-07-16 — First real run: `hod_momo_session_gate.py --profile integrity_only` — FAIL on coverage=98% flap; seconds later `/api/integrity` WARN only (`hod_surge_after_seed` 7). See run log.
- [x] 2026-07-17 — Separate worker fixed the 3 root causes behind live RVOL blowup + alert spam (cooldown_sec=0.0 persisted, stale avg_volume for multi-day runners, Alpaca-IEX avg_volume fallback for same-day movers); refreshed parity snapshot from the persistent observe loop confirms `nova_only` dropped from 41 to 0 across 14 stable ticks.

---

## Known traps

- **Do not trust CHANGELOG "Verified by" lines as still-true.** This domain has had repeated claims of fixes ("HOD Integrity fail" fixed 2026-07-16, then a new integrity-adjacent bug found the same day) — the user explicitly said the live app still shows broken data despite prior fix claims. Always re-verify with a fresh command before reporting a bucket as closed.
- **`nova_only` spam ≠ automatically a bug** — some `nova_only` rows may be legitimate Nova finds that Warrior's widget simply isn't showing (different universe breadth). Only escalate a bucket as `spam_cooldown` when the *rate* (same symbol+strategy firing repeatedly within the parity window) looks wrong, not just because Nova's row count is higher.
- **Parity observer refuses to arm on integrity FAIL (exit 2) by design** — this is not a tool bug; it means fix the feed first (`tools/hod_momo_parity_observe.py` calls `hod_momo_session_gate.py --profile integrity_only` before diffing).
- **`coverage=98%` Integrity fail ≠ L1 dead.** 39/40 active symbols OK rounds to 98%; usually one newly-admitted active symbol before first `note_quote`. Quote/eval p95 can be green while coverage hard-fails. Uncovered count is capacity design (watch ≫ 40), not a miss list to chase.
- **Check id is `hod_surge_after_seed`** (not "after_reset"). Empty historical bar fetch still marks the symbol seeded → inflates `surge_none_after_seed_count`.
- **After-hours snapshots undercount** — Warrior's HOD Momentum widget during AH shows a thinner symbol set (BIYA/LBGJ/JSPR pattern recurring across warrior-memory run log) than RTH; do not generalize AH parity numbers to RTH claims.
- **`.tmp/hod-momo-parity/` is gitignored and ephemeral** — never treat it as the source of truth across sessions; always fold durable findings into this memory file + `PROBLEM_LOG.md`/`CHANGELOG.md`.
- **Multiple `uvicorn --reload` cycles can leave a zombie process holding the real IBKR `clientId`** (per `classify_latest.md` operational note) — WatchFiles can log "Reloading..." without the worker PID actually changing, so a newer `--reload` spawn fails to connect to IBKR (`Error 326: client id already in use`) while the zombie keeps answering HTTP. Before trusting "the API on port 8000" for live verification, confirm exactly one python/uvicorn process is bound to that port and its log shows a clean IBKR `Connected`/`Logged on` with no `Error 326`.
- **Overnight L1 death can look like "Nova alerts broken" while HTTP still answers** — integrity FAIL with quote/eval max ages climbing for hours + `scanner_table_reprice` stale; observer correctly refuses (nova=0). Do not redesign gates from that window. Re-check `/api/integrity` live; if recovered, parity numbers after recovery are the ones that count.
- **Stale `warrior_latest.json` invalidates continuous 1:1** — if Warrior ts is from prior session/AH while Nova is RTH, warrior_only and nova_only mix timing artifacts with real gaps. Always check Warrior `ts` before escalating buckets.
- **yfinance's own `averageVolume` field drifts within minutes on extreme-volume days** — a fresh ATPC fetch returned a value 248x higher than one taken ~11 minutes earlier from the same function. `HOD_MOMO_FUNDAMENTALS_REFRESH_SEC` (300s) bounds staleness, it does not guarantee RVOL is never momentarily off inside a single refresh window on the most explosive names.
- **Accidental mass-disable + Squeeze `requires_hod=False` looks like a formula bug** — if only strategies 10/11 are enabled (or Squeeze fires without HOD), check persisted `hod-momo-config.json` / schema version before chasing RVOL/universe. Schema v5 self-heals; do not re-litigate CNF.

---

## Run log

Newest first. Keep entries short. Cap at ~30 entries — delete the oldest half if longer.

<!-- RUN_LOG_START -->

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

- **Scope:** Parent fixed CNF; update ledger; confirm PN/TRT still-open status. No new code. No commit.
- **Gate:** PASS (warn) — `hod_surge_buffer` cold-start WARN.
- **CNF:** `gate_mismatch` — only Squeeze 10/11 enabled + `requires_hod=False`. Warrior HOD Momentum requires new HOD. Schema v5 live verified (10/11 hod=True; 2–12 on; Former off). Stale CNF may remain in nova_only window until age-out.
- **PN:** seed closed — live $4.44 at HOD, soft master_rvol, Squeeze surge cooled → `timing_definition`.
- **TRT:** soft-block closed earlier; empty snap now → churn/`timing_definition` (not RVOL formula).
- **Parity:** warrior=40 nova=93 both=0 warrior_only=10 nova_only=37.
- **Memory:** Fixed ledger + Known trap + backlog; dashboard refresh-required.

### 2026-07-17 — Fix #1 PN universe_gap: under-$20 seed head + upside movers

- **Scope:** Authorized surgical fix for PN empty snap (Squeeze universe_gap).
- **Trace:** PN in gainer cache rank~36 @ ~$4.40; watch/discovery yes; active no — HOT_BY_VOLUME seed head + top_loser mover slots + former_slots=8.
- **Fix:** `seed_symbols_for_active`/`discovery_for_active`; belowPrice-first `scan_hod_momentum_seeds`; omit loser_rows; FORMER_SLOTS 2.
- **Verify:** PN active `volume_seed` price=$4.44; gate PASS(warn); observe warrior=40 nova=93 both=0 warrior_only=10; pytest 25 passed.
- **No commit.** Next: TRT L1 sticky.

### 2026-07-17 — Follow-up fix: TRT RVOL soft-block + sub-$20 seed (PN admitted)

- **Scope:** BTMD seed/L1; TRT RVOL diagnose/fix; SDOT document-only. Warrior age ~6min (<10m).
- **Gate:** PASS (warn).
- **TRT:** pace RVOL 0.32 = vol/(avg×elapsed) correct (yf avg 1.58M). Not formula bug — master floor blocked surge-only Squeeze. Soft-block shipped; live Squeeze strategies evaluate.
- **PN:** Was empty-snap universe_gap; now price=$4.40 in gainers, gate soft master_rvol(0.05), Squeeze blocked only by cooled surge~3.5%.
- **BTMD:** Off widget; still capacity_expected (never in IBKR top-50 at +3.8%).
- **SDOT:** timing cooled — no code change.
- **Files:** filters/trade/admin, discovery, constants_ibkr, tests, CHANGELOG, PROBLEM_LOG, memory.

### 2026-07-17 — Warrior refresh ts=1784308360; Squeeze classify (PN/SDOT/TRT)

- **Scope:** integrity PASS/warn; classify warrior_only focusing Squeeze; Former deprioritized; no commit.
- **Gate:** PASS (warn) — `hod_surge_after_seed=3`; active q/e p95~0.57s; IBKR connected.
- **Parity:** warrior=40 nova=53 both=0 warrior_only=10 nova_only=27 strategy_mismatch=SDOT.
- **Squeeze:** SDOT→`timing_definition` (at HOD surge 3.3%/4.6%; Warrior peak ~$31 vs Nova HOD $27.55); PN→`universe_gap` (empty snap; new vs BTMD); TRT→`gate_mismatch`/`rvol_formula` (master_rvol 0.32).
- **Former:** AMPG/PESI/RAM/RFIL/VELO — deprioritized (no fix budget).
- **BTMD:** off Warrior widget; still empty Nova — seed work continues via PN.
- **Fix:** diagnosis only. Memory + dashboard updated.

### 2026-07-17 — Live Warrior snap + Squeeze triage; spawn typo killed L1

- **Scope:** integrity + observe vs fresh warrior_latest (SDOT/BTMD/TRT/AMPG/RAM/RFIL); prioritize Squeeze; fix clear root cause.
- **Gate:** PASS (warn) after fix; during broken spawn: FAIL coverage ~42%.
- **Parity:** warrior=40 nova=13 both=0 warrior_only=7 nova_only=13 (post-fix tick).
- **Classified:** SDOT Squeeze→`timing_definition` (hod cooled; L1 OK); BTMD Squeeze→`universe_gap`; TRT Squeeze→`gate_mismatch`/`rvol_formula` (master_rvol 0.32); AMPG/RAM/RFIL Former→deprioritized/empty snap.
- **Fix applied:** `fills_poll_loop`→`fill_poll_loop` + per-task spawn; scanner_l1 first. Evidence: before=0 hod/scanner L1 subs + no bootstrap complete; after=bootstrap complete + IBKR ticks subscribed + active p95~0.8s.
- **Files:** `app_lifespan.py`, `test_app_lifespan_spawn.py`, CHANGELOG, PROBLEM_LOG, memory, dashboard.
- **Handoff:** none required for feed; next Squeeze recall = BTMD seed + TRT RVOL evidence.

### 2026-07-17 — CRITICAL: API listen-but-not-serve (lifespan IBKR hang)

- **Scope:** Diagnose :8000 accept TCP but `/docs` timeout; Gateway 4001 listening; fix surgically.
- **Result:** BLOCKED for parity — code fix applied; live serve unconfirmed until parent restarts uvicorn.
- **Root cause:** `app_lifespan` awaited Alpaca ping + IBKR startup on the same loop before `yield`. Hung `connectAsync` (Error 326 / clientId=1 zombie pattern) prevented Starlette from finishing startup.
- **Fix applied:** Deferred bootstrap after yield; `asyncio.wait_for` around connect (`IBKR_CONNECT_TIMEOUT_SEC=8`); recreate `IB()` on fail; default `IBKR_CLIENT_ID` 17. Tests: `test_ibkr_client_connect.py`. CHANGELOG + PROBLEM_LOG prepended (no commit).
- **Handoff:** parent restart uvicorn (kill zombie on 8000 first); then `curl /docs` + `session_gate`; warrior needs human Sign in.
- **Files:** `app_lifespan.py`, `ibkr/client.py`, `constants_ibkr.py`, tests, memory, CHANGELOG, PROBLEM_LOG.

### 2026-07-17 — URGENT tick #2: L1-fail explore poison (FRE) → integrity FAIL → fixed

- **Scope:** Diagnose re-FAIL (coverage ~85–98%, FRE missing, quote ages hours); surgical fix; restore gate + observe.
- **Result:** PASS (warn) — `session_gate` exit 0; `observe --once` warrior=40 nova=82 both=1 warrior_only=7 nova_only=29. Observe loop re-armed `--interval 30`.
- **Root cause:** FRE (discovery explore) failed IBKR L1 subscribe (`l1_hod=39`); coverage hard-required 100%; demoted symbols retained stale `_last_quote_ts` → hours-old max age when re-admitted without L1. Not Error 326 (single uvicorn worker; IBKR connected).
- **Fix applied:** `note_l1_subscribe_failed` cooldown; purge ages on demotion; coverage fail floor 90%; tool timeouts 30s. Tests green. PROBLEM_LOG + CHANGELOG prepended (no commit — parent must ask).
- **Classified (unchanged vs prior):** JSPR→`universe_gap`; BIYA/LBGJ Squeeze→`timing_definition`; LBGJ Low Float→`gate_mismatch` (rvol&lt;5); Former deprioritized. Warrior snapshot still AH-stale.
- **Files updated:** `hod_momo_active.py`, `hod_momo_integrity_hod.py`, `constants_hod_momo.py`, `scanner_l1.py`, tools timeouts, tests, memory, CHANGELOG, PROBLEM_LOG, dashboard.

### 2026-07-17 — RTH critical re-arm (user: Nova not matching / want continuous 1:1)

- **Scope:** Diagnose overnight integrity FAIL / nova=0; re-arm gate+observer; classify warrior_only with priority on Squeeze/Float/JSPR; document Former Momo evidence. No code change (feed recovered without patch).
- **Result:** PASS (warn) — integrity recovered (coverage 100%, qmax &lt;1s, IBKR connected). Parity `--once`: warrior=40 nova=53 both=1 warrior_only=7 nova_only=21. Observe loop restarted (`--interval 30`) — first tick warrior=40 nova=61 both=1 warrior_only=7 nova_only=23.
- **Classified:** JSPR→`universe_gap` (no snap, not in discovery); BIYA Squeeze→`timing_definition` (`hod price&lt;hod`); LBGJ Squeeze→`timing_definition` (`surge:None`); LBGJ Low Float→`gate_mismatch` (`rvol 2.64&lt;5`); LBGJ/BIYA Former deprioritized; nova_only held pending Warrior refresh.
- **Former Momo:** BA101 only labels color/strategy name; Nova uses remember-list approximation — no published Warrior closed-source formula found.
- **Blocker for continuous 1:1:** `warrior_latest.json` still AH 2026-07-16T23:07Z — handoff `warrior`.
- **Files updated:** `hod-momo-memory.md`, `agent-hod-momo.canvas.tsx`.

### 2026-07-17 — Post-fix refresh (separate worker landed cooldown/RVOL/enrichment fixes)

- **Scope:** Refresh memory + dashboard after a separate worker fixed 3 root causes behind live RVOL blowup + alert spam. No code touched by this agent; read-only classification + ledger/dashboard update.
- **Result:** PASS (warn) — `nova_only` 41→0 across 14 consecutive observe-loop ticks (`warrior=40 nova=2 both=2 warrior_only=6 nova_only=0`); `session_gate --profile integrity_only` PASS (warn, `hod_surge_after_seed` only).
- **Evidence:** Persistent `tools/hod_momo_parity_observe.py --interval 30` loop's `.tmp/hod-momo-parity/observe_loop_stdout.log` (14 ticks, all identical counts); own independent `py -3 tools/hod_momo_parity_observe.py --once` run at 2026-07-17T00:32:02Z reproduced the exact same `warrior=40 nova=2 both=2 warrior_only=6 nova_only=0` (15th consistent data point); `PROBLEM_LOG.md`/`CHANGELOG.md` 2026-07-16 "RVOL 700x-11000x blowup + alert spam despite 'fixed' prior session"; `.tmp/hod-momo-parity/classify_latest.md` (other worker's own root-cause + before/after table).
- **Learning:** Moved 3 root causes (cooldown_sec=0.0 persisted, stale avg_volume for multi-day runners, Alpaca-IEX avg_volume fallback for same-day movers) from "still open" to "fixed" with corroborated before/after evidence. Found and flagged a numeric discrepancy: this session's task prompt quoted CJMB/LBGJ post-fix RVOL as 1.06/0.01, but every written artifact from the fixing session (PROBLEM_LOG, CHANGELOG, classify_latest.md) says 46.49/10.38 — used the corroborated repo numbers and logged the discrepancy rather than silently trusting the prompt's paraphrase. `nova=2` (vs. 400 before) is a genuinely quiet post-fix tape per the fixing session's own note (extended-hours liquidity dried up post-20:00 ET), not a broken feed — cross-checked against 14 stable ticks, not a single sample.
- **Files updated:** `hod-momo-memory.md`, `agent-hod-momo.canvas.tsx`.

### 2026-07-16 — Live Integrity fail banner triage (coverage 98% + surge_none)

- **Scope:** Diagnose UI Integrity fail (`hod_active_set` coverage=98%, `hod_surge_after_seed`, uncovered list). Diagnosis only — no code change.
- **Result:** mixed — uncovered = `capacity_expected` (not a bug); coverage=98% hard-fail = **real brittle regression/noise** that suppresses alerts; surge_none = WARN when tape alive (empty historical seed / window mismatch).
- **Evidence:** session_gate exit FAIL with `active=40/40 … coverage=98%`; `/api/integrity` moments later status=warn cov=100% q/e p95~0.56s; 16s resample stable warn; debug `integrity_fail_suppress=265`; code cannot produce active>capacity (`_take` hard-cap) — screenshot `active=42/40` likely approx/misread.
- **Learning:** Do not chase uncovered=N. Coverage need-100% fails on a single unquoted newly-admitted active symbol (39/40→98%). Quote/eval age gates already exist — coverage hard-fail is redundant and flaps under explore rotation.
- **Files updated:** `hod-momo-memory.md`, `agent-hod-momo.canvas.tsx`.

### 2026-07-16 — Agent install + memory seed

- **Scope:** Meta — scaffold `hod-momo` via agent contract system; seed memory from existing CHANGELOG.md/PROBLEM_LOG.md HOD Momo entries and `.tmp/hod-momo-parity/diff_latest.json` (captured 2026-07-16T23:31:51Z) so the agent starts with real context instead of empty.
- **Result:** install
- **Evidence:** `diff_latest.json` counts warrior=40 nova=400 both=3 warrior_only=5 nova_only=41; 5 CHANGELOG/PROBLEM_LOG root causes already fixed this session (consolidation span, session_focus L1, heartbeat SLO, Former Momo bootstrap, scanner_l1 streaming); RTH remeasure and JSPR universe gap explicitly still open per CHANGELOG follow-ups.
- **Learning:** This domain has a pattern of "fixed" claims that the user still finds broken live — treat every prior fix as needing fresh re-verification, not as closed.
- **Files updated:** `hod-momo.md`, `hod-momo-memory.md`, registry entry, `agent-hod-momo.canvas.tsx`.

<!-- RUN_LOG_END -->
