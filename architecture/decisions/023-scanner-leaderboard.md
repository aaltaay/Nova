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

## Amendment 2026-09-24 -- each mover's catalyst in playback (#498)

**Context.** Sim playback of a past day showed the board but not why its movers
moved: the Scanner's News column had only `has_news` (an article existed), and
the catalyst verdict (ADR 024) was live-only. The backfilled history that can
answer lives in the research store (`catalysts.sqlite3`), which the backend
never reads.

**Decision.**

1. **One store for playback.** The leaderboard store goes to schema 2 with two
   tables written only by `research/catalysts/export_leaderboard.py`:
   `catalyst_checks` (per symbol-day: the window and the sources that looked)
   and `catalyst_items` (every item naming the symbol in the window, labelled by
   `catalysts/classify.py`). A version-1 store migrates in place by creating the
   two tables -- the rows / coverage history (tens of GB on the desk) is never
   rewritten; unknown versions still refuse. The export replaces a symbol-day
   whole, one session day per transaction, so the live recorder keeps writing.
2. **Items, not a verdict row.** Storing labelled items, not one verdict per
   day, lets a board read judge the news *as known at the playhead*: only items
   published after the prior session's close and at or before `at`, through
   `classify.verdict_from_labels` -- the same ranking and wire shape as the live
   desk. Unknown stays `null` (not exported, or no source looked and nothing
   published yet); `none_found` only when a source looked.
3. **The Scanner reads it as it reads a live row.** A played-back row carries
   `catalyst` when a verdict is on file; the News column ages it from the
   playhead, not the wall clock. The Catalysts tab (the live on-roster headline
   list) points at the News column on a day with catalysts on file and says
   none are on file otherwise.

**Consequences.** Coverage is the research targets' (the pillar universe and
the rebuilt board's top-10 movers): other symbols on a recorded board read
`null`. A verdict names the rules version that labelled its items; a rules bump
needs the export re-run on the desk. Halts for pending news come from this
store's own halt log, so a T1 halt the log never saw is not reported.

**Rejected.** *The backend reads the research store read-only*: a second store
on the playback path, and the research store's schema would become a backend
contract. *One verdict row per symbol-day* (the issue's first sketch): judged at
one cutoff, it can hide the best item until it is published but cannot say what
was known before it (an earlier dilution notice, a routine item, "none found"),
and a later cutoff's verdict would leak into an earlier playhead. *Article
text in the leaderboard store* so the backend reclassifies with current rules:
several times the size for what a re-export already gives.
