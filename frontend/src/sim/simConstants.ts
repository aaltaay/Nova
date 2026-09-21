/** SIM session + historical replay tunables (mirror backend/constants_sim.py). */
export const SIM_SESSION_OPEN_LABEL = '04:00';
export const SIM_SESSION_CLOSE_LABEL = '20:00';
export const SIM_SESSION_MINUTES = 16 * 60;
/** Historical job list and quote/tape snapshot refresh. */
export const SIM_HISTORY_POLL_MS = 1000;
export const SIM_ET_TIME_ZONE = 'America/New_York';
/** Time & Sales badge while historical replay feeds the tape. */
export const SIM_REPLAY_TAPE_STATUS = 'REPLAY';
export const SIM_REPLAY_TAPE_EMPTY = 'No prints yet at this replay time';
export const SIM_REPLAY_TAPE_NO_TRADES = 'Completed candles only -- download trades for Time & Sales';
/** Level 2 header chip in replay (replaces live halt / shortability chips). */
export const SIM_REPLAY_L2_CHIP_LABEL = 'Replay';
export const SIM_REPLAY_L2_CHIP_VALUE = 'No L2 recorded';
export const SIM_REPLAY_L2_CHIP_TITLE =
  'An IBKR historical download carries trades only, and no local depth recording covers this moment. Live halt and borrow state are hidden because they describe today, not this session.';
/** Same chip once a locally recorded book covers the playhead second (#309). */
export const SIM_REPLAY_L2_RECORDED_VALUE = 'Recorded L2';
export const SIM_REPLAY_L2_RECORDED_TITLE =
  'Level 2 recorded locally for this session, replayed at the playhead. Live halt and borrow state are hidden because they describe today, not this session.';
/** Said inside the ladder, because the rail hides .ibkr-depth-fallback-badge. */
export const SIM_REPLAY_L2_EMPTY_NOTE = 'Level 2 was not recorded for this moment';

/** Requests are bounded; slow polls never overlap. */
export const SIM_REQUEST_TIMEOUT_MS = 15_000;
export const SIM_HISTORY_IDLE_POLL_MS = 5_000;
export const SIM_CAPTURE_POLL_MS = 15_000;
export const SIM_SCRUB_KEYBOARD_MS = 120;
/** Mirrors backend historical acquisition pacing, not an ETA prediction. */
export const SIM_HISTORY_PAGE_INTERVAL_SEC = 11;
export const SIM_HISTORY_LARGE_WINDOW_MINUTES = 240;
export const SIM_HISTORY_SYMBOL_PATTERN = /^[A-Z0-9][A-Z0-9. -]{0,19}$/;

/**
 * Sim tab truth. A Sim pane that cannot show replay data says why, and says it
 * where the operator already looks (under the SIM PRACTICE strip), because the
 * charts keep painting archived bars and "some panels are blank" is not an
 * answer anyone should have to infer.
 */
export const SIM_TAB_NO_REPLAY_TITLE = 'No replay loaded';
export const SIM_TAB_NO_REPLAY_BODY =
  'This desk has no tape, quote or Level 2 until you load one. Use Historical replay '
  + 'or pick a recording in the Sim session bar above. The charts below are archived '
  + 'bars clipped to the sim clock, not replay data.';
export const SIM_TAB_OTHER_SYMBOL_TITLE = 'Not the replayed symbol';
export const simTabOtherSymbolBody = (tab: string, replaySymbol: string): string =>
  `${replaySymbol} is the loaded replay, so ${tab} has no tape, quote or Level 2 here `
  + `and will not fill. The charts below are archived ${tab} bars, not replay data.`;
export const simTabGoToReplayLabel = (replaySymbol: string): string => `Go to ${replaySymbol}`;
export const SIM_TAB_REPLAY_FAILED_TITLE = 'Replay failed to load';
