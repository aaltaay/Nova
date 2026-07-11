# Change log (agent-maintained)

This file is a running narrative of **what changed in this repo and why**, so future agent and human sessions can get oriented in minutes without digging through diffs.

- **Scope:** code behavior, module boundaries, public APIs, constants, tooling, rules, user-visible UI changes.
- **Out of scope:** pure typo fixes, formatting-only edits, local scratch files.

Bug fixes should **also** be logged in `PROBLEM_LOG.md` (symptom / cause / fix). This file answers "what does the codebase do now and why"; `PROBLEM_LOG.md` answers "what went wrong and how was it diagnosed."

## How agents update this file

1. **When:** After completing any task that changes logic, public behavior, a module boundary, constants, config, build, or rules. Skip pure cosmetics.
2. **Where:** Prepend a new `##` section **immediately below** the `<!-- ENTRIES_START -->` marker (newest entries at the top).
3. **Commit together:** The changelog entry ships in the **same commit** as the code it describes. Do not push code without an entry.
4. **Keep it short:** A few lines per field. No secrets, tokens, or personal data.

Entry template (copy and fill in):

```markdown
## YYYY-MM-DD — Short descriptive title

- **What:** 1–2 sentences on what changed (user-visible + internal).
- **Why:** Trigger for the change (user request, bug class, performance, cleanup).
- **Files touched:** Key files only, e.g. `backend/scanner.py`, `frontend/src/App.tsx`.
- **How it works now:** The mental model a future agent needs — the "oh, got it" paragraph.
- **Verified by:** How you confirmed it works (built + ran, test name, manual click path).
- **Follow-ups:** (optional) anything deferred.
- **Related:** (optional) commit SHA, PROBLEM_LOG entry date, issue link.
```

<!-- ENTRIES_START -->

## 2026-07-11 — Journal SQLite + metrics + go/no-go bar (Phase E)

- **What:** New `backend/journal/` package (`db.py`, `store.py`, `metrics.py`) persists every detected setup signal to a SQLite database (`signals` table) and provides a `trades` table + `record_trade()`/`get_closed_trades()` for Phase D to populate once paper execution exists. `metrics.py` computes win rate, avg win/loss, profit/loss ratio, and the plan's three-criteria live-money go/no-go bar (>=100 closed trades, >=2:1 P/L ratio, 100% rule adherence) — reporting `met: null` (pending, not failing) when there isn't enough data yet, rather than faking a result from zero trades. Exposed via `GET /api/journal/{signals,trades,metrics}`. New **Journal** sub-tab inside the Watchlist tab renders the go/no-go bar, a metrics grid, and a table of recently detected signals.
- **Why:** Phase E of the trading automation plan — the journal must exist and log signals *before* any order is ever placed, so Phase D's paper fills have somewhere to land from day one.
- **Files touched:** `backend/journal/{__init__,db,store,metrics}.py` (new), `backend/routes/journal.py` (new), `backend/strategy/setups_stream.py` (`_record_signal` now persists to the journal), `backend/main.py` (`init_db()` at startup, router registration), `backend/constants.py` (`JOURNAL_*`), `backend/tests/test_journal.py` (new), `frontend/src/strategy/{types,useJournal,JournalPanel,WatchlistTab}.ts(x)`, `frontend/src/constants.ts`, `frontend/src/index.css`.
- **How it works now:** `journal/db.py` resolves the DB file to `paths.cache_dir()/journal.db` (same convention as `cache.py`, not git-tracked) and opens a fresh connection per call rather than holding one open across the asyncio loop and FastAPI handlers. `setups_stream._record_signal()` calls `journal.store.record_signal()` right after broadcasting over `/ws/strategy`, wrapped in try/except so a journal write failure never breaks the live signal stream. `metrics.compute_metrics()` reads only `trades` with a non-null `pnl`; with zero trades every rate is `null` and the go/no-go bar shows NO-GO with the sample-size criterion failing and the other two pending. The "adherence" criterion folds in the plan's "max daily loss never breached" gate — a trade the executor marks `adherent=False` covers any risk-rule violation, including trading through a halt.
- **Verified by:** 8 new unit tests (isolated per-test SQLite file via a `tmp_path` fixture) + 98/98 full backend suite passing; live `GET /api/journal/{metrics,signals}` verified against the running server; headless-browser screenshot confirms the Journal sub-tab renders the NO-GO bar and empty-state metrics correctly.
- **Follow-ups:** Phase D (paper execution) will call `journal.store.record_trade()` after each bracket order closes, which is what turns the go/no-go bar from all-pending into real pass/fail.

## 2026-07-11 — Risk / discipline engine (Phase C)

- **What:** New `backend/strategy/risk.py` — a pure state machine tracking today's realized P&L, win/loss streaks, and position sizing, enforcing three walk-away guardrails (daily max loss, 3 losses in a row, giving back 50% of the day's peak profit). `validate_trade_plan()` checks a proposed trade's stop distance and profit/loss ratio. Exposed via `GET /api/strategy/risk` and `POST /api/strategy/risk/validate-trade`.
- **Why:** Phase C of the trading automation plan — the discipline layer that will gate Phase D (paper execution).
- **Files touched:** `backend/strategy/risk.py` (new), `backend/routes/strategy.py`, `backend/main.py` (session-reset background task), `backend/constants.py` (`RISK_*`), `backend/tests/test_risk.py` (new).
- **How it works now:** `RiskState` is a plain dataclass; a module-level singleton is mutated by `record_trade_result()` (not yet called by anything — Phase D/E will call it after each paper fill closes). Sizing looks at *current* daily P&L (not the historical peak), so a big win followed by a big loss correctly drops back to a cut quarter size. Halting is sticky for the rest of the day once tripped; only `reset_day()` (called automatically at 4 AM ET) clears it. This module places no orders and is not yet wired to any execution path.
- **Verified by:** 15 new unit tests + 90/90 full backend suite passing; live `GET /api/strategy/risk` verified against the running server.
- **Follow-ups:** Phase E (Journal + go/no-go bar) will read this endpoint in the UI; Phase D (paper execution) will call `record_trade_result()` after each fill.

## 2026-07-11 — Setup trigger engine: Bull Flag + ABCD + live signal stream (Phase B)

- **What:** Two new signal-only setup detectors — Bull Flag and ABCD — join Gap and Go behind a shared `evaluate_setups()` aggregator. Exposed on-demand (`GET /api/strategy/setups/{symbol}`) and live over a new `/ws/strategy` WebSocket fed by a background scan loop over the top-ranked watchlist symbols. New **Signals** sub-tab inside the Watchlist tab shows live triggers with entry/stop/target math.
- **Why:** Phase B of the full trading automation plan — mechanical setup detection layered on top of the Phase A watchlist.
- **Files touched:** `backend/strategy/{indicators,bull_flag,abcd,setups,setups_stream}.py` (new), `backend/routes/strategy.py`, `backend/main.py` (`/ws/strategy` route + lifespan task), `backend/constants.py` (`BULL_FLAG_*`, `ABCD_*`, `SETUPS_*`), `backend/tests/{test_indicators,test_bull_flag,test_abcd,test_setups}.py` (new), `frontend/src/strategy/{types,useSignalsStream,SignalsPanel,WatchlistTab}.ts(x)`, `frontend/src/constants.ts`.
- **How it works now:** `bull_flag.py`/`abcd.py` are pure functions over a candidate dict + a list of 1-min OHLCV bars — no fetching, no state, `would_execute` hard-coded `False`, matching `gap_and_go.py`'s existing contract exactly. `setups_stream.py` runs a 15s loop (`SETUPS_SCAN_INTERVAL_SEC`) that re-scores the top 15 watchlist symbols, fetches fresh bars via `bars.fetch_bars` in a thread executor, and broadcasts newly-eligible signals to `/ws/strategy` clients with a 2-minute per-symbol+setup cooldown so the same trigger doesn't spam every cycle.
- **Verified by:** 34 new unit tests + 75/75 full backend suite passing; live endpoint and WebSocket both tested against the running scanner with real bars; headless-browser screenshot confirms the Signals sub-tab connects and renders.
- **Follow-ups:** Phase C (risk engine) is next per the backbone doc.

## 2026-07-11 — Watchlist dashboard (Phase A of full trading automation plan)

- **What:** New composite-ranked watchlist on top of the existing Five Pillars scorer. `GET /api/strategy/watchlist` merges gapper + gainer caches, scores every symbol, and ranks all-pillars-pass candidates first with a weighted 0-100 composite score (change %, RVOL, float tightness, catalyst freshness) breaking ties. New **Watchlist** tab in the frontend shows a ranked table with per-pillar pass/fail chips.
- **Why:** First phase of the full "5 Pillars -> setups -> risk -> journal -> paper execution -> Level 2 learning" automation plan (see `Automation-Strategy-Backbone.md`).
- **Files touched:** `backend/strategy/watchlist.py` (new), `backend/routes/strategy.py`, `backend/constants.py` (`WATCHLIST_*`), `backend/tests/test_watchlist.py` (new), `frontend/src/strategy/{types,useWatchlist,WatchlistTab}.ts(x)` (new), `frontend/src/components/TabNav.tsx`, `frontend/src/App.tsx`, `frontend/src/constants.ts`, `frontend/src/index.css`.
- **How it works now:** `watchlist.py` is pure, signal-only scoring (no fetches, no orders) reused from `five_pillars.py`. The route dedupes gapper/gainer rows by symbol and caps output at `WATCHLIST_MAX_ROWS`. The frontend polls the endpoint every 3s (`WATCHLIST_POLL_INTERVAL_MS`) regardless of active tab so the tab badge count stays live; the tab itself is a plain table reusing existing `table-wrapper`/`symbol-btn`/`positive`/`na-muted` CSS classes plus 4 new pillar-chip classes.
- **Verified by:** 12 new unit tests + 41/41 full backend suite passing; live endpoint returned 30 ranked real candidates against the running scanner; headless-browser screenshot confirms the tab renders and updates the live count badge.
- **Follow-ups:** Phase B (Bull Flag / ABCD setup triggers + signal stream) is next per the backbone doc.

## 2026-07-11 — Grounded Q&A CLI (`ask.py`) over the course knowledge base

- **What:** New `tools/course_memory/ask.py`: retrieves from Pinecone (slides + official captions) and Obsidian, then has the model answer using ONLY the retrieved blocks, with numbered citations. Out-of-scope questions return `NOT_IN_KNOWLEDGE_BASE` instead of a guess.
- **Why:** User wants a single command that asks the database and answers solely from indexed course material.
- **Files touched:** `tools/course_memory/ask.py`, `tools/course_memory/constants.py` (ASK_* tunables), `knowledge/obsidian/00-System/How-Recall-Works.md`.
- **How it works now:** `py ask.py "question"` → router (reused from `recall.py`) → top-12 Pinecone chunks + top-4 Obsidian hits capped at 24k chars → chat completion at temperature 0 with a context-only system prompt → answer + citation list. `--show-sources` prints the retrieved text. `recall.py` remains the raw-retrieval tool.
- **Verified by:** Level 2 question answered with 16 citations from SS/BA slides + transcripts; crude-oil-futures control question correctly returned `NOT_IN_KNOWLEDGE_BASE`.
- **Related:** Same-day fidelity-test entry (guarantees the underlying data is caption-exact).

## 2026-07-11 — Fidelity tests: transcripts proven identical to raw captions

- **What:** Added `tools/course_memory/test_transcript_fidelity.py` (word-for-word comparison of every exported transcript against the raw Wistia caption JSON, plus timestamp validation and provenance checks) and `verify_pinecone_sources.py` (audits Pinecone vectors by `source` metadata). Deleted the last leftover sparse-notes file (`BA101_TIMESTAMPED_NOTES.md`), which the new provenance test caught.
- **Why:** User required proof the indexed transcripts contain no hallucinations or AI rewriting.
- **Files touched:** `tools/course_memory/test_transcript_fidelity.py`, `tools/course_memory/test_obsidian_recall.py`, `tools/course_memory/verify_pinecone_sources.py`, removed `downloads/warrior-trading-caption-notes/BA101_TIMESTAMPED_NOTES.md`.
- **How it works now:** Fidelity tests parametrize over every `warrior-trading-official-captions` MD file; the full transcript text must equal the concatenated raw caption cues and every timestamp must map to a real cue start. The Pinecone audit confirms only `warrior-trading-slides` and `warrior-trading-official-captions` sources exist and the stale `warrior-trading-caption-notes` source is fully purged.
- **Verified by:** 45/45 pytest passing (incl. `test_obsidian_recall.py`: vault holds no transcript/paraphrase bodies, recall admits only official-caption files); Pinecone audit reports 1,506 vectors, stale source purged, PASS.
- **Related:** Same-day entries below on official transcripts and purge.

## 2026-07-11 — Purge inaccurate caption notes; index official LMS transcripts only

- **What:** Added `py ingest.py --official-transcripts` which deletes stale `warrior-trading-caption-notes` vectors, then upserts only `warrior-trading-official-captions` Markdown from `downloads/warrior-trading-caption-notes/`. Obsidian recall now also keyword-searches those official transcript files on disk (Whisper files excluded). Documented the accuracy model in How-Recall-Works.
- **Why:** Sparse/paraphrase notes were inaccurate; user required the knowledge stores not learn non-video-aligned text.
- **Files touched:** `tools/course_memory/{ingest,constants,extract_markdown,pinecone_store,obsidian_store}.py`, `knowledge/obsidian/00-System/How-Recall-Works.md`.
- **How it works now:** Default transcript ingest is official LMS subtitle tracks only. Whisper gap transcripts stay local until `--include-whisper`. Slide PDFs unchanged.
- **Verified by:** Dry-run (18 files / 426 chunks / official source only); live purge+upsert 426 vectors; recall queries return `warrior-trading-official-captions`.
- **Follow-ups:** Optional opt-in Whisper indexing after manual spot-checks; do not claim absolute 100% ASR accuracy.
- **Related:** Real transcript export from same day.

## 2026-07-11 — Real video-aligned transcripts (official captions + Whisper)

- **What:** Replaced sparse title-only caption notes with real timestamped transcripts. For 18 LMS units with English captions, exported the official Wistia subtitle track. For 7 local BA101 MP4s that had no caption track, extracted audio with ffmpeg and transcribed via OpenAI Whisper.
- **Why:** Prior notes were paraphrased topic titles, not video-aligned speech. User asked for transcripts that match the videos without downloading more remote video.
- **Files touched:** `downloads/warrior-trading-caption-notes/` (local transcripts + `_export_official_transcripts.py`, `_whisper_local_videos.py`), Obsidian course index pointers under `knowledge/obsidian/01-Courses/`.
- **How it works now:** Official-caption units use the same text/timing as the LMS player. Gap units use local audio only (`_audio_cache/`). Full transcripts stay under gitignored `downloads/`; Obsidian holds path indexes only.
- **Verified by:** DE101 mentor-session MD now shows real spoken lines at matching timestamps; Whisper wrote 7 BA101 gap transcripts; frontend build + app already running.
- **Follow-ups:** Optional Pinecone re-ingest of transcript Markdown; Whisper remaining courses only if local videos exist.
- **Related:** Replaces the sparse-note approach from 2026-07-10.

## 2026-07-10 — Timestamped LMS notes in Obsidian and Pinecone

- **What:** Added source-aware Markdown ingestion and per-unit note export to the course-memory tooling, plus curated timestamped notes for captioned BA101, SS101, Live Trading Archive, and Platform Demo units. Inventoried all 12 enrolled LMS courses without downloading videos or storing full transcripts.
- **Why:** The user wanted caption-derived strategy material to complement the existing slide PDFs in both Obsidian and Pinecone.
- **Files touched:** `tools/course_memory/{constants,extract,extract_markdown,export_unit_notes,chunk,ingest,pinecone_store,recall}.py`, `tools/course_memory/test_extract_markdown.py`, `knowledge/obsidian/00-System/How-Recall-Works.md`, `knowledge/obsidian/01-Courses/`, `PROBLEM_LOG.md`.
- **How it works now:** `py ingest.py --content markdown` splits curated course notes by Markdown section, preserves course/source/unit/timestamp metadata, and upserts them into the existing course namespace. Recall output labels slide versus caption-note provenance and prints arbitrary Unicode safely on Windows.
- **Verified by:** Six pytest tests; 18 per-unit Markdown exports; Markdown dry run (4 files, 25 chunks); Pinecone upsert (25 vectors); successful Pinecone queries for VWAP and IPO/slippage notes; successful Obsidian query for simulator loss controls; frontend production build and browser launch.
- **Follow-ups:** Only 13 of 538 additional detected Wistia videos expose English captions. Add future notes incrementally when the LMS publishes more caption tracks or official handouts.
- **Related:** Updated the 2026-07-10 Windows `UnicodeEncodeError` entry in `PROBLEM_LOG.md`.

## 2026-07-10 — Five Pillars scoring + Gap and Go signal (Phase 1, signal-only)

- **What:** Added `backend/strategy/` with two pure-logic modules: `five_pillars.py` scores
  any candidate stock dict against the 5 Pillars (price, % change, relative volume, catalyst,
  float) and returns a ✅ checkmark only when all 5 pass; `gap_and_go.py` layers on the 9:30–10:00
  AM ET entry window and a pre-market-high breakout check, computing entry/stop/target from
  `constants.py` thresholds. Exposed read-only via three new `GET /api/strategy/*` endpoints
  (`backend/routes/strategy.py`). 22 new pytest unit tests run against mock data.
- **Why:** User asked to formalize the 5 Pillars as a pass/fail checklist with a checkmark,
  verify it with unit tests against mock data, and implement Gap and Go as the first automated
  setup — while guaranteeing no hidden automation (every automated capability must be legible
  to the user).
- **Files touched:** `backend/constants.py` (new `FIVE_PILLARS_*` / `GAP_AND_GO_*` constants),
  `backend/strategy/__init__.py`, `five_pillars.py`, `gap_and_go.py`, `backend/routes/strategy.py`,
  `backend/main.py` (router registration only), `backend/tests/test_five_pillars.py`,
  `test_gap_and_go.py`, `knowledge/obsidian/02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md`,
  `knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md` (decision log).
- **How it works now:** Both strategy modules are pure functions over plain dicts — no network
  calls, no state, no order-placing code path anywhere in either file. `GapAndGoSignal` hard-codes
  `would_execute = False`. The new routes are strictly `GET` (no `POST`/`PUT`/`DELETE`) and every
  response carries a `note` field stating it never places, modifies, or cancels orders. `routes/strategy.py`
  imports `main` lazily inside functions (same pattern as `hod_momo_enrichment.py`) to avoid a
  circular import with `main.py`, which registers the router. There is still no "Automate" button
  in the UI — this is backend signal logic only; the transparency principle (every automation
  control must state what it does/doesn't do, in plain language, next to the control) is now
  written into the backbone doc so it applies whenever that UI is built.
- **Verified by:** `py -3 -m pytest backend/tests/ -v` → 30/30 passed (22 new + 8 pre-existing
  IBKR safety tests unaffected). Confirmed `main.py` still imports cleanly with the new router
  registered (no circular-import regression).
- **Follow-ups:** No UI panel yet for these signals; Phase 2 (paper execution via IBKR) is not
  started — see backbone doc §5 for the phased plan and go/no-go bar before any order is placed.

## 2026-07-10 — Dual memory: Pinecone course RAG + Obsidian vault + recall router

- **What:** Added `tools/course_memory/` to ingest Warrior slide PDFs into Pinecone, plus an Obsidian vault at `knowledge/obsidian/` for curated Nova decisions. `recall.py` auto-routes questions to Obsidian, Pinecone, or both.
- **Why:** User wants accurate long-term recall of course material and a place for “what should Nova automate?” decisions without manually choosing a database.
- **Files touched:** `tools/course_memory/*`, `knowledge/obsidian/**`, `.env.example`, `.gitignore`.
- **How it works now:** PDFs → chunk/embed → Pinecone (`ingest.py`). Decisions live in Obsidian notes. Ask via `py recall.py "…"`. Router: Nova/build/decide → Obsidian first; course/setup/rules → Pinecone first; ambiguous → both. Trust order: Obsidian decisions > Pinecone citations > model guesses.
- **Verified by:** `ingest.py --dry-run` (1080 chunks from 34 1pp PDFs); `recall.py` Obsidian path after Unicode fix.
- **Follow-ups:** User adds `PINECONE_API_KEY` + `OPENAI_API_KEY`, runs full `ingest.py`, opens vault in Obsidian.

## 2026-07-10 — IBKR optional trading module (Level 2 depth + paper order execution)

- **What:** Added an opt-in Interactive Brokers trading module alongside the existing Alpaca-powered scanner. New "Trading" tab provides IBKR connection status, Level 2 order book (with L1 fallback while entitlement processes), an order ticket (market + limit, buy + sell), and a positions/account panel. All existing Alpaca tabs (Gappers, Movers, Afterhours, Catalysts, HOD Momo) are untouched.
- **Why:** User requested IBKR integration for Level 2 data and paper/live order execution. Alpaca has no L2; IBKR is the cheapest option (~$27.50/mo) with a 3-symbol simultaneous depth cap.
- **Files touched:** `backend/ibkr/` (new package: `client.py`, `depth.py`, `orders.py`, `account.py`), `backend/routes/` (new: `trading.py`, `__init__.py`), `backend/constants.py` (IBKR_* constants), `backend/requirements.txt` (`ib_async`), `backend/main.py` (router wire-in + lifespan hooks only), `frontend/src/ibkr/` (new module: all types, hooks, DepthLadder, OrderTicket, PositionsPanel, TradingTab), `frontend/src/components/TabNav.tsx` (new: tab bar extracted + Trading tab added), `frontend/src/App.tsx` (imports + new tab panel only), `frontend/src/constants.ts` (IBKR_* constants), `frontend/src/index.css` (IBKR styles + badge styles), `.env.example` (IBKR vars), `gemini.md` + `AGENTS.md` (Invariant #7 amendment), `backend/tests/test_ibkr_safety.py` (pytest coverage).
- **How it works now:** `IBKR_ENABLED` defaults `false` — Nova behaves exactly as before when the flag is absent or when IB Gateway isn't running. Setting `IBKR_ENABLED=true` in `.env` activates the client; it connects to IB Gateway paper port (4002) automatically and reconnects on drop. For live money, `IBKR_LIVE_TRADING_CONFIRMED=true` is also required (hard gate in `orders.py`). The depth subscription manager caps at 3 simultaneous symbols and falls back to L1 top-of-book if depth entitlement is not yet active. Nova does NOT launch Gateway — user runs it manually once per week (IBKR Mobile 2FA).
- **Verified by:** Frontend TypeScript build (`npm run build`), `pytest backend/tests/test_ibkr_safety.py` (all tests pass without a live Gateway), manual dev run confirming existing tabs render identically and Trading tab shows the disconnected guide when Gateway is not running.
- **Follow-ups:** Automated momentum strategy execution (needs user-provided symbol list + strategy rules), bracket/OCO order support.
- **Related:** gemini.md §11 maintenance-log entry 2026-07-10.

## 2026-07-10 — Windows Electron desktop + local API sidecar

- **What:** Added an Electron shell around the existing Vite/React UI and a local FastAPI sidecar (dev: `run_api.py` / packaged: PyInstaller `nova-api.exe`). Web UI on Vercel is unchanged.
- **Why:** User wants a full local stack (faster/stabler for a future trading machine) plus an installable Windows app, without rewriting the scanner UI.
- **Files touched:** `frontend/electron/*`, `frontend/package.json`, `frontend/vite.config.ts`, `frontend/src/main.tsx`, `frontend/src/constants.ts`, `backend/run_api.py`, `backend/paths.py`, `backend/nova_api.spec`, `backend/main.py`, `backend/cache.py`, `backend/constants.py`, `backend/hod_momo.py`, `README.md`.
- **How it works now:** `npm run electron:dev` starts Vite + Electron; Electron spawns the API on `127.0.0.1:8000`, waits for `/api/health`, then loads the UI. `npm run electron:pack` builds the sidecar, builds the renderer with `base: './'`, and produces an NSIS installer via electron-builder. Desktop data lives under `%APPDATA%\Nova` via `NOVA_ENV_PATH` / `NOVA_CACHE_DIR` / `NOVA_LOG_DIR`.
- **Verified by:** `npm run build` (web) OK; Electron launched against Vite and reused healthy API; packaged `nova-api.exe` returned `/api/health` connected; `electron-builder` produced `Nova-Setup-0.1.0.exe` (~156 MB).
- **Follow-ups:** App icon / code-signing; if `frontend/release` hits Windows EPERM during pack, build with `--config.directories.output` under `%TEMP%`.


## 2026-05-06 — Add nova.altaystudio.com domain to Vercel

- **What:** Assigned the custom domain `nova.altaystudio.com` to the frontend Vercel project (`stock-alert`).
- **Why:** To make the stock alert frontend accessible via a branded, production-ready domain.
- **Files touched:** None locally (Vercel configuration only).
- **How it works now:** Vercel will automatically route requests for `nova.altaystudio.com` to the latest production deployment of the frontend.
- **Verified by:** Vercel CLI domain addition success output.

## 2026-05-04 — Add frontend-specific Railway configuration

- **What:** Added `frontend/railway.toml` to explicitly configure the builder and healthcheck for the frontend service.
- **Why:** Railway's monorepo deployment was attempting to use the root `/railway.toml` (which uses a Python Dockerfile) for the frontend service, causing builds to fail. This file instructs Railway to use Nixpacks/Railpack for the frontend directory.
- **Files touched:** `frontend/railway.toml`
- **How it works now:** The frontend service will use this specific configuration file when the "Config as code" path in Railway is pointed to `/frontend/railway.toml`.
- **Verified by:** Merged PR #1 generated by Railway AI.
## 2026-05-04 — Fix invalid GitHub Actions workflow and clean up pycache

- **What:** Fixed a parsing error in `.github/workflows/deploy.yml` that prevented CI checks from running. Removed `__pycache__` directories from Git tracking.
- **Why:** GitHub Actions does not allow accessing repository secrets in job-level conditionals. This caused the entire CI check suite to fail immediately, which in turn blocked Railway from deploying the frontend. Python bytecode files were also accidentally committed.
- **Files touched:** `.github/workflows/deploy.yml`, `backend/__pycache__/`
- **How it works now:** The deployment step now runs and checks if `$RAILWAY_TOKEN` is set using bash. If it is omitted, the step skips gracefully without failing the job, allowing Railway's native deploy to proceed.
- **Verified by:** Pushed the commit and verified the CI check suite executes.
- **Related:** PROBLEM_LOG 2026-05-04
## 2026-04-28 — HOD Momo RVOL fallback to yfinance for IEX feed

- **What:** The HOD Momo scanner now uses `yfinance` to compute RVOL when running on the IEX free tier. A 5-minute warmup grace period has been added to allow strategies to fire without RVOL while fundamentals load in the background. The UI now displays a "YF" badge next to yfinance-sourced RVOLs and a banner explaining the IEX data source.
- **Why:** The scanner was failing to trigger any alerts because Alpaca's IEX feed historical bars are mostly empty, causing the average volume to be zero. Since RVOL was always null on IEX, the `master_rvol:unknown` gate blocked all alerts.
- **Files touched:** `backend/constants.py` (warmup grace and batch size), `backend/main.py` (`_fetch_fundamentals` extracts volumes), `backend/hod_momo.py` (`rvol_source` tracking and warmup bypass), `backend/hod_momo_enrichment.py` (feed-level switch to calculate RVOL), `frontend/src/hod_momo/types.ts` (`rvol_source`), `frontend/src/hod_momo/HodMomoTab.tsx` (YF badge and IEX banner), `frontend/src/App.tsx`, `frontend/src/index.css`.
- **How it works now:** In `hod_momo_enrichment.py`, if the active feed is `iex`, the pipeline bypasses Alpaca bars and proactively queues the ticker for `yfinance` fundamentals. `_fetch_fundamentals` grabs `average_volume` and `current_volume` from yfinance's `.info`, and the enrichment loop calculates RVOL from those two values. The symbol's snapshot is tagged with `rvol_source="yfinance"`. On the UI, this badge clarifies the origin of the data.
- **Verified by:** Verified `/api/hod-momo/debug/snaps` returns `rvol_source: "yfinance"` and populated RVOL fields.
- **Related:** PROBLEM_LOG same date.

## 2026-04-28 — Configurable data feed (IEX/SIP) with auto-fallback

- **What:** The Alpaca data feed is now selectable from the UI Settings panel (IEX or SIP), shown as a badge in the header, and persisted to `.env`. If SIP is selected but the user's plan doesn't support it, the system automatically falls back to IEX on 403/409 errors — with a visible "⚠ fallback" indicator in the header so the user knows.
- **Why:** The backend was hardcoded to default to `sip`, which requires a paid Alpaca subscription. Free-tier accounts got 403s on REST and 409s on WebSocket, resulting in empty gapper lists with no explanation. This was the root cause of the "no gappers" issue on 2026-04-28.
- **Files touched:** `backend/constants.py` (new `DATA_FEED_DEFAULT`, `DATA_FEED_OPTIONS`), `backend/main.py` (feed tracking, fallback logic, config endpoints, health/gappers responses), `backend/bars.py` (use `DATA_FEED_DEFAULT`), `frontend/src/constants.ts` (feed labels), `frontend/src/App.tsx` (settings dropdown, header badge, fallback hint), `frontend/src/index.css` (feed badge + select styles), `.env` (add `ALPACA_DATA_FEED=iex`).
- **How it works now:** `_active_feed` tracks the runtime feed (initialized from env → `DATA_FEED_DEFAULT`). On SIP rejection (403 REST or 409 WS), `_try_fallback_to_iex()` switches to IEX once per session and the caller retries. The feed badge in the header shows `IEX` (blue) or `SIP` (purple). Settings panel has a dropdown to change it. The `/api/health` and `/api/gappers` responses include `data_feed` and `feed_fell_back` fields.
- **Verified by:** `npm run build` clean, `py -3 -c "import py_compile; py_compile.compile('main.py')"` clean.
- **Related:** PROBLEM_LOG same date.

## 2026-04-23 — Skip `railway up` deploy job when `RAILWAY_TOKEN` is unset

- **What:** The **Deploy to Railway** job’s `if` now requires `secrets.RAILWAY_TOKEN != ''`. Header comments mark the token as optional when using Railway-only Git deploys.
- **Why:** An empty or placeholder secret still made the job run and fail; operators who only use Railway’s dashboard deploy don’t need `railway up` from GitHub at all. A bad/expired token still fails until the user replaces it at https://railway.com/account/tokens .
- **Files touched:** `.github/workflows/deploy.yml`.

## 2026-04-23 — Fix backend CI when pytest collects zero tests (exit 5)

- **What:** The `Run tests` step in `.github/workflows/deploy.yml` wraps pytest in `set +e` / `set -e` so exit code **5** (“no tests collected”) is handled before `errexit` kills the step.
- **Why:** Default Actions `bash` uses `-e`; `pytest` returning 5 made the step fail immediately, so the “treat 5 as OK” branch never ran and **Backend tests** failed even with no tests.
- **Files touched:** `.github/workflows/deploy.yml`.

## 2026-04-23 — Manual `workflow_dispatch` for CI / Deploy

- **What:** Added `workflow_dispatch` to `.github/workflows/deploy.yml`.
- **Why:** Operators may see the workflow listed with zero runs; they can start it from the Actions UI without an empty commit.
- **Files touched:** `.github/workflows/deploy.yml`.

## 2026-04-23 — GitHub Actions vs Railway `prebuild` (fix CI blocking Railway)

- **What:** `check-railway-api-base.mjs` treats a build as “Railway” only when `RAILWAY_PROJECT_ID` is set **and** `GITHUB_ACTIONS` is unset. The `frontend-build` job uses a bash default for `VITE_API_BASE_URL` when the Actions variable is empty.
- **Why:** Frontend deploys on Railway were **SKIPPED** (“CI check suite failed”) while **Wait for CI** was on. Copying `RAILWAY_PROJECT_ID` into GitHub made `prebuild` think the GitHub runner was Railway and require `VITE_API_BASE_URL` there.
- **Files touched:** `frontend/scripts/check-railway-api-base.mjs`, `.github/workflows/deploy.yml`.

## 2026-04-23 — Tab bar scroll so HOD Momo stays reachable

- **What:** `.tab-bar` now uses horizontal `overflow-x: auto` with `flex-wrap: nowrap`; `.tab` uses `flex-shrink: 0`.
- **Why:** `.main-col` has `overflow: hidden`, so on typical viewports the fifth tab (**HOD Momo**) was clipped with no way to scroll to it — production looked like the feature was missing.
- **Files touched:** `frontend/src/index.css`.

## 2026-04-23 — Wrap scanner tabs in `.tab-bar-scroll` (fix HOD Momo still hidden)

- **What:** Tab buttons live inside `.tab-bar-scroll` (`flex: 1; min-width: 0; overflow-x: auto`); “updated … ago” is a sibling `.tab-bar-meta` (`flex-shrink: 0`). Removed the old `.tab-spacer` flex filler between tabs and the timestamp.
- **Why:** A single flex row with `flex: 1` spacer between the last tab and the timestamp prevented the scroll region from shrinking, so **HOD Momo** stayed clipped even after adding `overflow-x: auto` on the outer `.tab-bar`.
- **Files touched:** `frontend/src/App.tsx`, `frontend/src/index.css`.

## 2026-04-23 — Inject API base into `index.html` for Railway static hosts

- **What:** `vite.config.ts` adds a `<meta name="nova-api-base" content="…">` at build time from `VITE_API_BASE_URL` / `NOVA_API_BASE` (same `process.env` Railway uses for `vite build`). `main.tsx` reads that meta first. `/config.json` is only trusted when the response looks like JSON (avoids accepting SPA fallback HTML that returned HTTP 200).
- **Why:** On Railway, `/config.json` was missing from the deploy artifact; the static server returned `index.html` with status 200, JSON parse failed, and the app fell back to `localhost` — “Backend unreachable” despite a correct `VITE_API_BASE_URL` variable.
- **Files touched:** `frontend/vite.config.ts`, `frontend/src/main.tsx`.
- **Verified by:** `npm run build` with and without `VITE_API_BASE_URL`; with env set, `dist/index.html` contains the meta tag and `dist/config.json` is written.

## 2026-04-23 — `/api/health` no longer stuck on `loading` without Alpaca keys

- **What:** On startup, if `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` are missing, the backend now sets cached health to `status: "error"` with an explanatory message and logs a warning, instead of leaving the default `loading` forever (which happened because `_ping_health` was never called).
- **Why:** Railway operators often omit broker keys at first; `/api/health` then looked like a hung request and was confused with “wrong host” or localhost routing.
- **Files touched:** `backend/main.py`.
- **Verified by:** Code path review; local uvicorn would log the warning when env vars are absent.
- **Related:** `PROBLEM_LOG.md` same date.

## 2026-04-23 — API root JSON + F12 API diagnostics

- **What:** FastAPI now serves `GET /` with a small JSON payload pointing to `/api/health` and `/docs` so opening the backend host in a browser is not mistaken for a broken deploy. The frontend logs structured errors on scanner fetch failure (`API_URL`, `API_BASE_URL`, hint to try `/api/health`). Optional verbose traces via `?apiDebug=1` or `localStorage.setItem('novaApiDebug','1')` plus `/config.json` resolution logging in `main.tsx`. Added `frontend/src/debug.ts`.
- **Why:** Operators saw `{"detail":"Not Found"}` at `/` and assumed the backend was down; that response was FastAPI’s default empty root. Separately, debugging “unreachable” needed clearer console and Network-tab guidance.
- **Files touched:** `backend/main.py`, `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/debug.ts`.
- **Verified by:** `npm run build` in `frontend/`; local `curl` to `/` after deploy is optional.
- **Related:** Same-day entries on Railway API base.

## 2026-04-23 — Runtime API base via `config.json` and bootstrap

- **What:** `main.tsx` now resolves the backend URL before loading `App`: use inlined `VITE_API_BASE_URL` when present, otherwise `fetch('/config.json')`. A `postbuild` script writes `dist/config.json` from `VITE_API_BASE_URL` or `NOVA_API_BASE` so production can reach the API even when Vite did not bake the variable into the bundle. `constants.ts` reads `window.__NOVA_API_BASE__` set during that bootstrap. HoD MoMo debug fetches use `API_BASE_URL` + `/api` paths instead of a hardcoded localhost.
- **Why:** The deployed Railway bundle still contained only `http://localhost:8000` while the dashboard variable was set—some builds were not inlining `VITE_*` into JS. Serving `config.json` from the same static origin avoids relying on that substitution alone.
- **Files touched:** `frontend/src/main.tsx`, `frontend/src/constants.ts`, `frontend/scripts/write-dist-api-config.mjs`, `frontend/scripts/check-railway-api-base.mjs`, `frontend/package.json`, `frontend/src/hod_momo/HodMomoDebugPanel.tsx`, `frontend/.env.example`.
- **How it works now:** Production: bootstrap loads `/config.json` when needed, sets `window.__NOVA_API_BASE__`, then the app module graph loads. Local `npm run dev` unchanged (no config file). Railway builds still require `VITE_API_BASE_URL` or `NOVA_API_BASE` so `postbuild` can emit `config.json`.
- **Verified by:** `npm run build` without env (no `config.json`); with `VITE_API_BASE_URL=https://stockalert-production.up.railway.app`, `dist/config.json` contains that URL.
- **Related:** Same-day PROBLEM_LOG entry.

## 2026-04-23 — Railway frontend builds must set `VITE_API_BASE_URL`

- **What:** Added `frontend/scripts/check-railway-api-base.mjs` and an npm `prebuild` hook so builds on Railway fail fast if `VITE_API_BASE_URL` is missing (otherwise Vite embeds `http://localhost:8000` and production shows “backend unreachable”). GitHub Actions workflow now runs on `master` as well as `main`, and the Railway deploy job runs on pushes to either branch.
- **Why:** Deployed frontend JS still pointed at localhost because the env var is only read at **build** time; adding it in the dashboard without a **redeploy** left an old bundle. “Wait for CI” on Railway also never saw a passing workflow when the repo only used `master`.
- **Files touched:** `frontend/scripts/check-railway-api-base.mjs`, `frontend/package.json`, `.github/workflows/deploy.yml`.
- **How it works now:** Local `npm run build` is unchanged. On Railway (`RAILWAY_PROJECT_ID` set), `prebuild` requires `VITE_API_BASE_URL` before `vite build`. After setting the variable, trigger a new Frontend deployment so the bundle is rebuilt.
- **Verified by:** `npm run build` in `frontend/` succeeds locally; same with `RAILWAY_PROJECT_ID=1` set and `VITE_API_BASE_URL=https://example.com` the prebuild passes (manual check).
- **Related:** `PROBLEM_LOG.md` same date.

## 2026-04-17 — Add agent-maintained CHANGELOG.md and `change-log` rule

- **What:** Introduced `CHANGELOG.md` at the repo root and a new always-on rule `.cursor/rules/change-log.mdc` that requires agents to prepend a human-readable summary after every non-trivial task. Sits alongside the existing `problem-log.mdc` / `commit-after-tasks.mdc` policies.
- **Why:** Reading raw diffs or `git log` is too slow when re-entering the project. The user wants a single "swipe through and understand" file, especially the *"how it works now"* narrative that commits and bug logs don't capture.
- **Files touched:** `CHANGELOG.md` (new), `.cursor/rules/change-log.mdc` (new).
- **How it works now:** Three agent-maintained docs cover different questions: `CHANGELOG.md` = "what does this codebase do now and why" (newest-first, prepend on every task), `PROBLEM_LOG.md` = "what bug happened and how was it fixed" (newest-first, prepend on resolutions), `.cursor/rules/*.mdc` = persistent policies. Task completion is not done until the changelog entry exists and ships in the same commit as the code.
- **Verified by:** Built and ran the app via `Run Stock Alert.bat` (uvicorn on `:8000`, Vite on `:5173`) — no code paths changed, doc-only change.
- **Follow-ups:** `progress.md` and `findings.md` (Phase-0 leftovers, last touched 2026-04-13) overlap with this file and should probably be archived or deleted in a future task.
- **Related:** Mirrors the newest-first `<!-- ENTRIES_START -->` convention in `PROBLEM_LOG.md`.
