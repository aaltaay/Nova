# The relative-volume table (#1100)

Every minute bar of every common stock since 2016 with its relative-volume baselines, and one row per stock-day,
so a question over every stock and every day ("when volume runs 10x hot at 6-7 AM, what happens next?") reads the
table in seconds instead of re-reading the 46 GB of minute files each time.

| File | Job |
|---|---|
| `build_rvol.py` | reads the minute and day files a session at a time (oldest first), writes the table, keeps it current |
| `rvol_state.py` | what carries from one session to the next: each symbol's last sessions, epochs, one session's rows |
| `../market_reads/rvol_store.py` | owner of the files: paths, `schema_version`, manifest, atomic writes, the rules |
| `../market_reads/rvol.py`, `rvol_outcomes.py` | the reads: every stock-day at a clock time, triggers, outcomes |

```text
py -3 research/rvol/build_rvol.py              # every session not built yet (the first run: about an hour)
py -3 research/rvol/build_rvol.py --status
py -3 research/rvol/build_rvol.py --rebuild-from 2024-03-01
```

Rules, schema and the three measures: `architecture/schema/agent-desk.md` ("Relative volume across every stock, and
what came next"); the guide and its traps: `docs/market-data.md`. Size, measured 2026-10-20: about 29 MB a session in
2026 (1.26 million bars), about 49 GB for 2016-2026; 1.6-2.0 s a session, below-normal priority, 1-2 GB of memory.
`<root>/STOP` stops a build after the session in hand.
