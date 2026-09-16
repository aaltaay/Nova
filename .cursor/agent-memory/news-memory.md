# News memory (living)

Living knowledge for the Nova `news` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/news.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-18T06:20:43Z
source_revision: cdf87d5
result: install
metrics: {}
blockers: []
dashboard_freshness: clean
```

Machine-readable block only. Update after material runs. Do not duplicate mutable truth that lives in canonical domain sources.

---

## How to continue improving

> Use the news subagent to work the news pipeline

Or:

> Improve the news agent — work the next backlog item in `.cursor/agent-memory/news-memory.md`.

Durable facts get **promoted into `news.md`**. Run history and open ideas stay **here**.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] Draft dedicated news-continuity.mdc when first material news change lands.
- [ ] Inventory existing news pytest coverage (-k news) and fill gaps.

### Completed

- [x] 2026-09-16 -- Junk movers/listicle filter (`news.junk`) so listicles do not flame or drive impact (#155).
- [x] 2026-07-18 — Agent scaffolded via `tools/create_nova_agent.py`.

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### 2026-09-16 -- Junk listicle filter

- **Scope:** News column + flame + news_impact (#155).
- **Result:** `news.junk` excludes movers listicles at ingest, impact, and News strip. Company-specific headlines still flame.
- **Learning:** Scanner NEWS flame is timestamp-only (`newest_headline_at`); junk must be dropped in `_check_news`, not only in the UI chip.
- **Files updated:** `backend/news/junk.py`, ingest + impact call sites, `frontend/src/utils/newsJunk.ts`.

### 2026-07-18 — Agent install

- **Scope:** Meta — scaffold news via agent contract system.
- **Result:** install
- **Learning:** Follow docs/agent-operations.md remaining human steps.
- **Files updated:** `news.md`, `news-memory.md`, registry entry.

<!-- RUN_LOG_END -->
