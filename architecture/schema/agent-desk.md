# Data schema: Agent desk and the day movers index

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/agent_desk/, backend/day_movers/, research/movers/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Agents find stock-days and show them in the Sim (ADR 050, operator ask 2026-10-06)

"Go to a small-cap stock that increased, where the high of the day was 300% ... punch it in on the simulator so I
could see it", then "this is just going to be for agents for now ... like some secret endpoints that they can
manipulate and show me." Owners `backend/day_movers/` (the index), `backend/agent_desk/` (the routes, commands,
dictionary), `research/movers/` (the builder), `frontend/src/agent_desk/` (the desk side), `tools/nova_agent.py`
and `.claude/skills/nova-sim-navigator/`. Nothing here places, stages or cancels an order, or arms the desk.

- **The index.** `<NOVA_MARKET_DATA_DIR>/movers/day_movers.sqlite3` (`PRAGMA user_version = 1`; an unknown
  version refuses), written only by `research/movers/` through `day_movers.store`:
  - `sessions (session_date PK, prev_date, tickers, rows, minute_bars, builder, built_ts, note)` -- one per
    session built: `tickers` the day bars that session, `minute_bars` 1 when the minute file was read.
  - `movers`, primary key (session_date, symbol): `kind, prev_date, prev_close, prev_volume, split_factor,
    split_listed, split_suspect, open, high, low, close, volume, pm_high, pm_low, pm_volume, ah_high, ah_low,
    ah_volume, day_high, day_high_ts, day_low, day_low_ts, dollar_volume, first_ts, last_ts, high_pct, low_pct,
    close_pct, gap_pct, up10_ts, up20_ts, up50_ts, up100_ts, up300_ts, down10_ts, down20_ts, down50_ts`.
    - `kind`: the Massive reference type (`CS`, `ADRC`, `WARRANT`, ...; null when the reference has none).
    - `prev_close`: the official close of `prev_date`, the session before in the files, times `split_factor` for
      a split Massive lists or `confirm_splits.py` proved executing in between (`split_listed` 1); null when the
      stock did not trade that session, never an older close. `prev_volume` is that session's volume on today's
      share basis.
    - `open` / `high` / `low` / `close` / `volume`: the day bar -- regular hours, the official close.
    - `pm_*` 04:00-09:30 ET, `ah_*` 16:00-20:00 and `day_high` / `day_low` 04:00-20:00 come from the minute bars,
      with the start of the first minute that printed each (`*_ts`, epoch seconds); `dollar_volume` is the
      minutes' close x volume; `first_ts` / `last_ts` the first and last minute that printed.
    - `*_pct` are fractions against `prev_close` (`gap_pct` from the 09:30 open; null without a prior close);
      `upN_ts` / `downN_ts` the first minute whose high reached +N% (whose low reached -N%).
    - `split_suspect` 1 when the open is 1.8x or more (0.7x or less) the prior close and no split is listed.
    - A row is kept when the high is +10% or the low -10%, the close or the gap is 5% either way, or a split
      suspect; without a prior close, when the day's high is 20% over its low.
  - `sec_shares (symbol, cik, as_of, filed, shares, form)`: shares outstanding a filing reported as of `as_of`,
    from SEC's companyfacts (`research/movers/export_sec_shares.py`; several share classes keep the largest).
  - `splits (symbol, execution_date, split_from, split_to)`: the split list the builder adjusted prices by.
- **Routes** (`/api/agent`, loopback clients only; every write needs `X-Nova-Api-Key` even on loopback;
  percentages on this wire are percent points):
  - `GET /api/agent` -> `{schema_version: 1, endpoints: [{method, path, does}], index: {ok, error, path,
    sessions, first, last, files_last, behind, missing, rows}, dictionary: {entries, error}, desk: {listening,
    last_poll_ts, window_id}, rules: string[]}` (`behind`: minute-file days newer than the newest session built;
    `missing`: minute-file days not built; both null when the folder cannot be listed).
  - `GET /api/agent/movers` -> `{schema_version: 1, query, units: "percent", count, rows[], summary, excluded,
    coverage, notes[]}`. Query: `from`, `to`, `symbol`, `kinds` (default `common`: `CS`, `ADRC`, and a ticker of
    1-4 letters the reference has no type for), `price_min` / `price_max` (the prior close), `high_min` /
    `high_max`, `low_min` / `low_max`, `close_min` / `close_max`, `gap_min` / `gap_max` (percent), `close_pos_min`
    / `close_pos_max` (0 = closed at the day's low, 1 = at its high), `giveback_min` / `giveback_max` (the share
    of the run over the prior close given back by the close, 0-1), `high_after` / `high_before` (`HH:MM` ET),
    `volume_min`, `dollar_volume_min`, `float_max` (shares), `float_unknown` (`exclude` | `include` | `only`),
    `replayable` (only days whose trades file is on disk), `splits` (`exclude_likely` default | `include` |
    `only_suspects`), `sort` (`newest` | `oldest` | `high` | `low` | `close` | `gap` | `volume` |
    `dollar_volume`), `limit` (default 25, at most 500). A row is `{date, symbol, kind, prev_close, open, high,
    low, close, volume, dollar_volume, day_high, day_high_et, day_low, day_low_et, pm_high, ah_high, high_pct,
    low_pct, close_pct, gap_pct, close_pos, giveback, first_et: {up10, up20, up50, up100, up300, down10, down20,
    down50}, replayable, split: null | "listed" | "suspect" | "likely_split", float: {shares, source:
    "recorded" | "enrichment" | "sec_shares_outstanding" | null, as_of, proof: "pass" | "fail" | "unknown"} |
    null}` (`float` only when `float_max` is asked). A split suspect is a `likely_split` when it traded no more
    shares than `prev_volume`, and no split at all (`null`, a real overnight move) when it traded 3x or more
    (#772). `summary` covers every match, not only the rows returned: `{matched,
    closed_above_prior_close, closed_above_open, closed_top_third, closed_bottom_third, median_high_pct,
    median_close_pct, median_giveback}` (shares of `matched`, in percent). A search matching more than
    `AGENT_MOVERS_MAX_SCAN` stock-days answers `too_broad: true` with the count only. `GET
    /api/agent/movers/{date}/{symbol}` -> `{schema_version, row, coverage}` (`AGENT_NOT_IN_INDEX` 404).
    Refusals: `AGENT_INVALID` 400 with `field`, `AGENT_INDEX_UNAVAILABLE` 503 (not built, or unreadable).
  - `POST /api/agent/show {symbol, date, at?: "run" | "drop" | "high" | "low" | "open" | "premarket" | "HH:MM",
    confirm?: boolean}` -> 202 `{command}`. A run or a drop parks five minutes before its first +20% (else +10%)
    mark; a mark the stock already stood at within five minutes of its first print is where it opened, so the
    next mark it reached later (+50%, +100%, +300%) is taken, else the day's high (low). The window loaded is
    135 minutes from the quarter hour 30 minutes before the park (so the charts show what came before), with 60-
    and 30-minute windows to fall back on when the Sim's print or quote cap refuses it. Refusals are `{detail: {reason, error, ...}}`: `AGENT_INVALID` 400 (also a day not over yet),
    `AGENT_NOT_ON_FILE` 404 (no trades file for that day), `AGENT_NO_DESK` 409 (no main desk window listening),
    `AGENT_AT_STAKE` 409 with `at_stake: {venue, safe, items: [{kind, venue, symbol, text}], unknown: [{kind,
    error}]}`. A new show replaces one not finished (`cancelled`).
  - `POST /api/agent/move {to?: "high" | "low" | "run" | "drop" | "open" | "premarket" | "HH:MM", by_min?: number,
    paused?: boolean, confirm?: boolean}` -> 202 `{command}`; `AGENT_NOTHING_LOADED` 409 unless the Sim holds a
    window. A target outside the loaded window loads one around it (`AGENT_AT_STAKE` as a show's).
  - `GET /api/agent/commands/{id}?wait=` -> `{command}`, waiting up to `wait` seconds (at most 30) for a change;
    `GET /api/agent/commands` the newest; `POST /api/agent/commands/{id}/cancel`. A **command** is `{id, kind:
    "show" | "move", status: "queued" | "running" | "done" | "failed" | "expired" | "cancelled", created_ts,
    updated_ts, args, plan, step, steps: [{step, ts, text}], result, error, claimed_by}`. A show's `plan` is
    `{symbol, date, at, anchor_et, park_et, park_ts, park_words, window, fallback_windows, switch_venue,
    in_index}` and a move's `{symbol, date, paused, target_ts, target_et, target_words, loaded_start_ts, window,
    fallback_windows}` (`park_words` / `target_words`: where it lands, in words), a window `{start, end, start_ts,
    end_ts}` (ET `HH:MM` and epoch seconds). A command no desk window takes within `AGENT_COMMAND_CLAIM_SEC`
    (15 s) expires. One a window took and never reported on within `AGENT_COMMAND_FIRST_REPORT_SEC` (10 s) goes
    back in the queue -- a reloaded or closed window's poll can still be waiting on the server -- at most three
    times, and the desk's poll gives a command back at once when its request is gone; one the desk stops
    reporting on for `AGENT_COMMAND_LEASE_SEC` (90 s), or still running after `AGENT_COMMAND_STALE_SEC`, fails.
  - `GET /api/agent/desk` -> `{schema_version: 1, venue, live_edge, sim: {session_date, playhead_et, paused,
    loaded: {source, symbol, date, start, end} | null} | null, focus: {page, symbol, window_id} | null,
    listening, at_stake}`.
  - `GET /api/agent/dictionary` -> `{schema_version: 1, error, entries[]}`; `POST /api/agent/dictionary {entry}`
    adds or replaces an operator entry by `id`; `DELETE /api/agent/dictionary/{id}`.
  - The desk's side (keyed, the long poll too): `GET /api/agent/desk/next?wait=&window_id=` (the main window's
    long poll, `{command | null}`, the command now `running` and its) and `POST /api/agent/desk/commands/{id}
    {status: "running" | "done" | "failed", step, text, result?, error?}` -> `{command}` (a command already
    cancelled or expired answers as it is, and the desk stops).
- **The dictionary** (operator: "If I'm obviously asking for a command ... I want it to be added to our
  dictionary"): `<cache_dir>/agent-dictionary.json` = `{schema_version: 1, entries: [{id, phrases: string[],
  means, call: {method, path, params?, body?}, then?, notes?, added_by, added_at, updated_at}]}`, written through
  a temp file and a rename. Seed entries live in code (`seed: true` on the wire); an operator entry with a seed's
  id replaces it. An unknown version or an unreadable file reads as the seeds with the error stated, and writes
  are refused `AGENT_DICTIONARY_UNREADABLE`. Nova defines no shape words: an agent turns words into the numbers
  above, asks when they have no agreed meaning, and saves what the operator confirms.
- **At stake** (operator: switch "when nothing is at stake"; owner `agent_desk/safety.py`): on the venue the
  desk would leave, a position or a working order (Paper's ledger, Live's IBKR cache), the Bot on, an open bot
  or Nova trade, a Nova stock mode or approval, or the desk armed; and, when the show or move loads another Sim
  window (which starts the Sim's scratch account over), the Sim account's positions and working orders. A check
  that cannot be read is at stake too. `confirm` is sent only after the operator agreed in the chat.
- **The desk side.** Only the main window (never a Trader pop-out, the sample desk or the demo) long-polls for
  commands. It runs them with the desk's own steps -- venue, Sim day, Trader tab, the Massive window, the wait
  for its import, the playhead (paused) -- reports each step, and shows a notice of what it is doing. A window
  refused for the print or quote cap is retried with the plan's narrower windows.
- **Float** (operator: proven, else unknown; owner `day_movers/floats.py`): `float_max` passes on the float
  Nova knew that day (the desk's enrichment snapshot in `archive.db`, 2026-07-28 on) at or under the limit, or
  on `sec_shares` at or under the limit -- a float cannot exceed the shares outstanding: the newest count filed
  by the session, as of a day on or before it and at most `DAY_MOVERS_SEC_SHARES_MAX_AGE_DAYS` (120) before it,
  put on the session's basis through the splits listed in between. Shares issued after the count are not in
  it, and the answer carries its `as_of`, `filed` and `age_days`. A snapshot over the limit fails; anything
  else is unknown, never today's float.

