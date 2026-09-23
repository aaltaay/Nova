# ADR 023 -- The scanner leaderboard: one row per symbol per minute, recorded and rebuilt

**Status:** Accepted · **Date:** 2026-09-22
**Builds on:** [[008-persistent-ibkr-scanner-rosters]] · [[022-setup-scanner-tape-gate]] · [[010-ib-loop-isolation]] · [[017-single-replay-surface]] · [[019-practice-fills-on-replayed-sessions]] · [[020-three-venues-one-feed]]

## Context

The chosen small-cap setup is the first pullback on "the most obvious stock in
the market right now", 07:00-10:00 ET (`Bot-Trading-Plan.md` section 2f). Nova
could not answer "which stock led at 07:42?":

- `cache_snapshots.save_*_snapshot` keeps one board per list per day and
  overwrites it all day, so a past day has only its final board -- which holds
  the day's eventual winners, i.e. hindsight.
- Halts lived only in memory (`ibkr/halt_status.py`).
- Session Record is manual and capped at three symbols, so the leader that set
  up rarely has Level 2 on file.
- On Sim, scrubbing back moved the chart, Level 2 and tape to the past while
  the Scanner stayed on today: two clocks on one desk.

## Decision

1. **One row format** (AGENTS.md section 3, "Scanner leaderboard") shared by
   boards the desk recorded and boards rebuilt from minute flat files. A row is
   the board *as it stood at* its `minute_ts`; every unknown is `null`.
2. **Owner `backend/leaderboard/`**, store `leaderboard.sqlite3` with
   `PRAGMA user_version`, under `NOVA_LEADERBOARD_DIR` / `F:\Nova\leaderboard` /
   the operator cache -- a new directory, so the capture root and the historical
   downloads are never re-rooted. Invalidation: rows are immutable history; a
   reconstruction rebuild replaces its own `(date, source)` rows only.
3. **Always recording.** A minute loop on the HTTP loop snapshots every board
   through `scanner_surface.surface_rows` and enqueues; a worker thread writes
   (ADR 010). Each minute also writes a heartbeat so a quiet minute is told
   apart from a gap. Gaps are shown with their reason and never filled or
   carried forward -- the same "resume, then say so" rule as Session Record.
4. **A halt log** from IBKR tick 49 transitions and Nasdaq Trade Halt RSS rows.
   Playback shows a halt only from the log.
5. **One pure ranking function** (`leaderboard/ranking.py`) for playback's
   leaders, the S5 offline universe and live auto-record.
6. **Auto-record** 07:00-10:00 ET records the top leaders through the existing
   Session Record path on free Level 2 lines only, and yields its
   lowest-ranked line when the operator opens Level 2 elsewhere.
7. **One desk, one clock.** On Sim off the live edge the Scanner board and the
   HOD Momo strip follow the playhead; `POST /api/sim/clock {session_date}`
   moves Sim to a past day with nothing loaded. Live and Paper stay on now.

## Consequences

- A recorded day and a reconstructed day of the same date can disagree about
  the leader: the desk only saw IBKR's 50-row lists, a rebuild sees the whole
  market. Each row carries `source`, and `rvol_basis` keeps the two RVOLs apart.
- Reconstructed floats are mostly `null`: the flat files carry no float as of a
  date, and today's shares-outstanding snapshot would be hindsight. Nova's own
  enrichment snapshots fill float from 2026-07-28 on.
- Storage grows by roughly 20-35 MB per recorded day on F:.
- Minute granularity: a board change inside a minute is not kept. Tick detail
  is the symbol's replay (Session Record or historical download).

## Rejected

- **Keep saving whole boards every 15 s** (first plan): richer, but a second
  format beside the rebuilt one and awkward to query for S5.
- **Show the day's final board when no journal exists**: hindsight.
- **Carry the last board across a restart**: passes an old board off as a newer
  moment.
- **Auto-record on all three lines, 07:00-10:00**: takes Level 2 away from the
  operator during the hours they trade by hand.
