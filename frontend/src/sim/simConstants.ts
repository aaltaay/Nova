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
  'Historical Level 2 is not recorded. Live halt and borrow state are hidden because they describe today, not this session.';
