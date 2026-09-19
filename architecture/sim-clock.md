# Sim playback clock

The process-local owner is `backend/sim/session_clock.py`. Only the Sim feed
consults its paused state; IBKR paper/live clocks and broker connections do not.

`POST /api/sim/clock` accepts one clock action: existing
`{minute_from_open: integer}` / `{follow_wall: true}`, or `{paused: boolean}`.
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
- Follow wall clock explicitly clears pause and returns to the existing wall
  clamp. Process restart/test reset clears pause. Pause is not persisted.
- One Sim-header button changes between Pause and Play icons with accessible
  action labels. Failed requests show an inline error, never a false paused UI.
- Clock controls preserve Trader tab selection (ADR 011 section 7b).

Verify fixed-clock pause/resume and scrub semantics, both feed branches, API
Sim-only validation, and the single-button UI in unit and browser tests.
