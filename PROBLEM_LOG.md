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
