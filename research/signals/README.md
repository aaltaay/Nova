# The signal table

The Trader's Signals panel at the end of every minute of every in-play stock-day since 2016, by the desk's own
rules, so an agent can mix signals in one query and every agent gets the same answer. Contract:
`architecture/schema/agent-desk.md` ("The Trader's signals on past days, and mixing them"); reads:
`docs/market-data.md` and the `signal_*` tools of the `nova-data` MCP server.

| File | Owns |
|---|---|
| `build_signals.py` | the build: plan, workers, the manifest, `--stage tape`, `--status` |
| `inputs.py` | one session's inputs, read once: the universe, minute bars, relative volume, history, catalysts, boards, halts, SEC shares, HOD Momo |
| `evaluate.py` | one stock-day's signals minute by minute, by the panel's own rules |
| `lanes.py` | the setup scanner's lanes over the day's bars (`EyesReplay`, built-in templates) |
| `tape.py` | the tape stage: the flow score from Massive trades sided on the NBBO |

The files themselves belong to `research/market_reads/signals_store.py`; the list of signals to
`research/market_reads/signal_registry.py`.

```text
py -3 research/signals/build_signals.py --workers 10            # every session not built yet, newest first
py -3 research/signals/build_signals.py --stage tape --start 2026-01-01 --workers 4
py -3 research/signals/build_signals.py --status
```

A session reads only the relative-volume table and the stores up to that day, so sessions build in parallel. A new
day needs the relative-volume table's day first (`research/rvol/build_rvol.py`). `<root>/STOP` stops a build after
the days in hand. About 0.7 s per in-play stock-day for the minute stage and about 1 s for the tape stage.
