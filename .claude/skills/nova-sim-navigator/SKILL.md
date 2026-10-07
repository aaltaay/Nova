---
name: nova-sim-navigator
description: "Use when the operator asks to find stocks or charts on past days (small caps that ran or faded, a high of day +N%, gappers, a float under N, shapes like ascending / descending, the percentage of those) or to show / open / pull up a stock-day in Nova's Sim, jump the playhead (to the high, back 5 minutes, pause, play), or what the desk is showing. Drives Nova's private /api/agent endpoints (ADR 050) through tools/nova_agent.py; never places orders."
---

# Nova Sim navigator (ADR 050)

The operator types a request; you understand it, search Nova's day movers index, list the matches, and on
"show me" put the real desk on that stock-day in the Sim, paused, through Nova's private agent endpoints.
Nova holds no meaning for words: **you** turn words into numbers, and the operator's confirmed wording is kept
in Nova's dictionary so the next agent reads them the same way.

Always use the CLI (it reads the desk's API key itself -- never read or print `.env`):

```text
py -3 tools/nova_agent.py status                       # index reach, the desk listening, the rules
py -3 tools/nova_agent.py dict                         # the dictionary: read it before acting
py -3 tools/nova_agent.py find --high-min 300 --price-max 20 [--from 2025-01-01] [--float-max 10000000]
py -3 tools/nova_agent.py find --set close_pos_min=0.67 --set giveback_max=0.3 --set high_after=09:30
py -3 tools/nova_agent.py row 2026-09-25 MSGY          # one stock-day as the index holds it
py -3 tools/nova_agent.py show MSGY 2026-09-25 [--at run|drop|high|low|open|premarket|09:45]
py -3 tools/nova_agent.py move --to high | --by -5 | --pause | --play
py -3 tools/nova_agent.py desk                         # what is on screen now
```

Add `--json` for the raw answer. Every search argument and field is in AGENTS.md section 3, "Agents find
stock-days and show them in the Sim". Percentages are percent points (300 = +300%).

## The flow

1. **Read the dictionary** (`dict`, or `dict match <words>`). An entry is the operator's own words, what they
   mean and the exact call. Use it as written.
2. **No entry fits?** Turn the words into the search's numbers. Plain facts need no question ("ran 300%" =
   `high_min=300`; "small cap" = a prior close of $20 or less until the operator says otherwise). A word with no
   agreed number -- "ascending", "fader", "low float", "big volume" -- you propose numbers for, run, and **say the
   numbers with the result** ("I read ascending as closed +20% or more, in the top third of its range: ...").
   Ask when you cannot propose anything sensible. Do not invent setups: shapes the bot already trades are the
   bot strategies' own rules (first pullback, bull flag, flat top, red to green, gap and go).
3. **List the matches**: date, symbol, prior close, the high and when it printed, high %, close %, the summary
   percentages, and anything flagged (`split: suspect / likely_split`, `replayable: false` = no tick data to
   replay, `float: unknown`). Say how far the index reaches (`coverage`) when it matters.
4. **Show** what the operator picks (`show SYMBOL DATE`). Default `--at run` parks 5 minutes before the run
   began; name another moment when they ask ("at the high", "at 9:45"). The command follows the desk step by
   step and ends `done` with where the playhead is. Opening a day the first time takes seconds to minutes (the
   import reads that day's files); say so while it loads.
5. **Move** inside the day on request (`move`). A move outside the loaded window loads a new one.
6. **Save the wording.** When the operator asked for something that is clearly a command and confirmed the
   numbers (or tuned them), add a dictionary entry: write a JSON file and `dict add FILE.json`:
   `{"id": "ascending", "phrases": ["ascending chart", "went up all day"], "means": "...",
   "call": {"method": "GET", "path": "/api/agent/movers", "params": {"close_min": 20, "close_pos_min": 0.67}},
   "added_by": "claude"}`. Tell the operator it is saved and how to change it.

## Rules

- **Nothing here places, stages or cancels an order, or arms the desk.** Never route around that.
- **AGENT_AT_STAKE**: the show or move would switch the desk to the Sim from Paper / Live with something open
  there (a position, an order, the Bot on, Nova's trades, the desk armed), or load a new window over a Sim
  practice position. List every item to the operator and **only after their OK in the chat** pass `--confirm`.
  Never confirm on your own.
- **AGENT_NO_DESK**: Nova's desk (its main window) is not open; ask the operator to open it.
- **AGENT_NOT_ON_FILE**: that day has no trades file on disk yet (the downloader fills older years over time).
- **Float is proven or unknown** (the operator's rule): a stock passes `float_max` only on the float Nova
  recorded that day or SEC shares outstanding under the limit (the count is as of its own date: shares issued
  since are not in it -- say the date). Everything else is `float: unknown`; offer `--set float_unknown=include`
  to list them. Never use today's float for a past day.
- **Splits**: a likely split (a huge overnight jump on no more shares than the day before) is left out by default
  (`splits=include` brings it back); a `suspect` is listed -- mention it.
- The index is built by `py -3 research/movers/build_movers.py` (newest days first, resumable). If `status` says
  days are missing or behind and the operator needs them, run it (it takes several seconds a day on the busy E:
  drive; `--avoid-session` stops before the market opens).
