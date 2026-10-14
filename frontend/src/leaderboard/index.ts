/** Public leaderboard API -- cross-feature imports of what is new go through this barrel (ADR 005). */

// A rebuilt day's Gappers by the second over the minute board (ADR 023 amendment 2026-10-13).
export { bySecondNotice, withGappersBySecond } from './gappersBySecond';
export { useGappersBySecond } from './useGappersBySecond';
export { LEADERBOARD_SECONDS_TITLE } from './leaderboardConstants';
