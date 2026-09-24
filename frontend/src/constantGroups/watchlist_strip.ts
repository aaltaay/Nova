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

export function symbolPillarsPath(symbol: string): string {
  return `/strategy/watchlist/${encodeURIComponent(symbol)}`;
}
