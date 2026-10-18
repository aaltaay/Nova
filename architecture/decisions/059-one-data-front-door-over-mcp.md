# ADR 059 -- One data front door, served to agents over MCP

**Status:** Accepted · **Date:** 2026-10-18
**Decided by:** the operator, 2026-10-18, in a session measuring historical float for small-cap runners. In order:
- "do we not have a standarized way for agents to access data from massive? ... we may have hundreds of agents
  wanting to access it."
- "we may need a standard way MCP to allow agents to access data in standarized form with endpoints so agents are
  able to find the correct data."
- "ok if this agent skipped it how do we prevent this?" -- then "Start building the full front door + MCP now",
  "Everything in one PR".

## Context

`tools/market_data.py` and `research/market_reads` (PRs #871, #876) are the front door for trades, quotes, bars,
the day movers index, past-day boards and splits, and the `nova-market-data` skill says never to write another
reader. In one session an agent still wrote three, and each went wrong in a way the front door exists to stop:

- It filtered the movers store with `high_pct >= 10`; the store keeps fractions, so it measured +1000% days (68
  stock-days instead of 374,420).
- It told the operator Nova had no quarterly financials; ten years of Massive statements sat in the reference dump.
- Three of its full scans of the 1 GB movers store stalled each other on the drive the trading desk also reads.

The skill was in its list and it did not read it -- and even if it had, the front door had no reader for the
reference dump or SEC's bulk files, and its movers search stops at 500 rows. A skill is advice an agent must
choose to open; nothing listed the data in front of it, and nothing stopped a raw read.

## Decision

1. **One library, every dataset.** `research/market_reads` gains `reference.py` (Massive financial statements,
   float, IPOs, ticker details, FINRA short interest), `sec.py` (SEC XBRL share facts and the filing list),
   `scan.py` (bulk movers rows, no cap), `catalog.py` (what each dataset is) and `slots.py` (heavy-read limits).
   `tools/market_data.py` is its command line.
2. **As-of is the library's job, never the caller's.** A statement or SEC fact counts from its filing date; a FINRA
   settlement from its publish lag; an SEC outstanding count is put on the asked day's share basis through the
   splits in between. Data with no history (Massive's float, ticker details) says `latest_only` and is never
   offered as a past day's.
3. **Units are stated once.** Percent points in and out of every movers read; the catalog names each dataset's
   units and as-of rule.
4. **Served over MCP.** `tools/nova_data_mcp.py` (official SDK, stdio) exposes the reads as tools, registered for
   Cursor (`.cursor/mcp.json`) and Claude Code (`.mcp.json`), so they sit in every agent's tool list with their
   arguments described; `data_catalog` comes first. Read-only on the data: a tool writes only a table an agent asks
   for by a new `output_name` under `--output-root`; inline answers stop at 200 rows. Heavy modules load on the
   main thread before stdio starts (a Windows pipe read blocked numpy's import from a worker thread).
5. **Shared limits.** Heavy reads (bulk scans, index builds, MCP stock-day reads) take one of
   `NOVA_MARKET_READ_SLOTS` (default 2) OS lock files, across every process on the PC.
6. **A tripwire.** `tools/data_access_hook.py` runs as a Cursor `beforeShellExecution` hook and a Claude Code
   `PreToolUse` hook on Bash: a command, inline code or an ad-hoc script outside the repo that names a raw store is
   denied with the front door's directions. Repo code passes (it is reviewed and gated); a command may state
   `# raw-data-ok: <reason>`. It fails open; it is a tripwire, not a wall. File reads are not hooked: a Python start
   on every read measured ~370 ms, and the stores are gzip and SQLite, which a read tool cannot use.
7. **One persisted file:** `<NOVA_MARKET_DATA_DIR>/store/reference_index.sqlite3`, owner `reference.py`, rebuilt per
   dataset when a source file's size or time changes, `user_version` 1, another version refused.

## Consequences

- The float study can ask "shares outstanding for X as known on day D" in one call, and every agent gets the same
  answer by the same rule.
- Not here yet: insider holdings (SEC Form 3/4/5 data sets are not downloaded), lockup terms (no SEC dataset), and a
  shape-features index for questions like "charts stair-stepping up"; each plugs into this library and server as a
  new reader and tool.
- The hook adds a Python start (~370 ms) to shell commands that match its filter (data words or a `.py`).
- `nova_chart_mcp.py` stays the chart exporter; this server is data.
