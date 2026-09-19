# Sim playback clock

The default session is 04:00–20:00 America/New_York (960 minutes). Explicit
historical session windows override those bounds; all slider labels use the API
opening and closing timestamps.

The process-local owner is `backend/sim/session_clock.py`. Only the Sim feed
consults its paused state; IBKR paper/live clocks and broker connections do not.

`POST /api/sim/clock` accepts one clock action: existing
`{minute_from_open: integer}` / `{follow_wall: true}`, `{paused: boolean}`, or
`{second_from_open: number}` (finite; otherwise 422).
The response adds `paused: boolean` to the existing clock envelope.
Pause/play requests are rejected when Sim is off.

- Pause captures the exact current Sim timestamp. Time remains fixed, including
  across midnight. Synthetic and captured feed ticks skip generation, matching
  working fills and fan-out while paused.
- Play resumes from that timestamp at normal speed, without catching up to wall
  time or emitting the elapsed pause interval. Repeated pause/play requests are
  idempotent.
- Scrubbing while paused updates the frozen position and rebuilds its snapshot;
  it stays paused. Explicit replay ticker changes retain that paused state.
  Leaving historical replay also keeps the playhead's Eastern time of day,
  moved onto the SIM1 session date; reloading the same historical window keeps
  the playhead.
- Follow wall clock explicitly clears pause and returns to the existing wall
  clamp. Process restart/test reset clears pause. Pause is not persisted.
- One Sim-header button changes between Pause and Play icons with accessible
  action labels. Failed requests show an inline error, never a false paused UI.
- Clock controls preserve Trader tab selection (ADR 011 section 7b).

Verify fixed-clock pause/resume and scrub semantics, both feed branches, API
Sim-only validation, and the single-button UI in unit and browser tests.

## Chart knowledge boundary (D-052)

All SIM chart responses use the session clock, including real tickers without
a selected capture. Under ADR 012 the archived IBKR store remains the source,
but intraday replay reads are restricted to the clock's Eastern session date
and apply the time cutoff before the row limit. A real ticker without bars on
that date shows an empty pane rather than a fully painted earlier session.
Daily and longer history may still show earlier completed periods as context.
Replay never substitutes unrestricted present-day history for missing past data.

Completed intraday OHLCV is visible only at interval end. Captured prints may
build the current candle using only events at or before the playhead. Missing
prints mean completed-bar playback, not an invented price path or volume ramp.
Daily, weekly and monthly history excludes the current calendar period (UTC
date labels interpreted as exchange session dates); no final current-period
OHLCV is shown. Synthetic SIM1 remains explicitly synthetic practice.

Replay coverage adds `replay: true` and `replay_mode` (`trades`,
`completed_bars`, or `synthetic`) to the existing coverage object. The frontend
polls active replay charts each second, clears them on seek/mode change,
rejects stale responses, and blocks live tape/IBKR bar patches from overwriting
replay-owned candles. Indicators receive the same bounded bars.

Historical trade acquisition, quote/tape symbol reconciliation, and current
daily/weekly/monthly partial aggregation remain tracked in D-052; this chart
boundary does not claim those datasets or features exist.

The browser replay chart under `frontend/e2e/fixtures/` is a development
fixture. Vite serves its TSX module. Its normal browser URL uses a small local
sample clock and bars so opening the page needs no broker, credentials, or
Playwright route interception. Playwright can opt into external API interception
with `?external-api=1`. Opening its HTML as `file://` shows the Vite URL and
does not try to import TSX directly.
