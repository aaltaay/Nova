/**
 * The quote panel's Five Pillars strip for any symbol (operator ask,
 * 2026-09-23): ranked among the Contenders or not, graded by the backend
 * (GET /api/strategy/watchlist/{symbol}).
 */
export const WATCHLIST_STRIP_POLL_MS = 5_000;
export const WATCHLIST_STRIP_GRADING = 'Grading the Five Pillars…';
/** Where the grade came from: the ranked list, a board's own row, or the live quote. */
export const WATCHLIST_STRIP_SOURCES: Record<string, string> = {
  watchlist: 'Ranked among the Contenders',
  gappers: 'Not a Contender · graded from its Gappers row',
  gainers: 'Not a Contender · graded from its Gainers row',
  losers: 'Not a Contender · graded from its Losers row',
  afterhours: 'Not a Contender · graded from its After Hours row',
  large_cap: 'Not a Contender · graded from its Large Cap row',
  quote: 'Not on a board · graded from its live quote',
};
export const watchlistStripRank = (rank: number): string => `#${rank} of the Contenders`;

/**
 * A Sim replay desk (operator report, 2026-10-12): the grade is the replayed day's own board row at the
 * playhead, named with its moment, board and place -- never today's Contenders rank. A rebuilt day's
 * `market` board is its Gainers (ADR 023 amendment 2026-10-06).
 */
const REPLAY_BOARD_LABELS: Record<string, string> = {
  gappers: 'Gappers', gainers: 'Gainers', market: 'Gainers', losers: 'Losers', afterhours: 'After Hours',
  large_cap: 'Large Cap',
};
const REPLAY_SOURCE_WORDS: Record<string, string> = { recorded: 'recorded', reconstructed: 'rebuilt' };
const REPLAY_GAP_WORDS: Record<string, string> = {
  not_running: 'Nova was not running', feed_down: 'the IBKR feed was down', not_recorded: 'not recorded',
  outside_session: 'outside the 04:00-20:00 session',
};
export const replayPillarsSource = (moment: string, board: string | null, source: string | null,
  rank: number | null): string => {
  const word = source ? REPLAY_SOURCE_WORDS[source] ?? source : '';
  const name = board ? REPLAY_BOARD_LABELS[board] ?? board : 'board';
  return `${moment} · graded from its ${word ? `${word} ` : ''}${name} row${rank != null ? ` (#${rank})` : ''}`;
};
export const replayPillarsAbsent = (symbol: string, moment: string, absent: string): string =>
  absent === 'not_on_board'
    ? `${symbol} is not on the ${moment} board: nothing of that day to grade. Today's pillars are not shown on a replay.`
    : `No board at ${moment} (${REPLAY_GAP_WORDS[absent] ?? absent}): nothing of that day to grade.`;

export function symbolPillarsPath(symbol: string): string {
  return `/strategy/watchlist/${encodeURIComponent(symbol)}`;
}
