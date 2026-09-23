/**
 * Scanner leaderboard playback (ADR 023) -- feature-local constants
 * (AGENTS.md section 6.1): paths, tunables and every word the desk says about
 * a board it shows at the Sim playhead.
 *
 * One desk, one clock: on the Sim venue off the live edge the Scanner board
 * and the HOD Momo strip show the board / alerts AT the playhead. Nothing here
 * ever shows a board from after the playhead, carries one across a gap, or
 * turns an unknown into a number.
 */

/** Routes (AGENTS.md section 3, "Scanner leaderboard"). */
export const LEADERBOARD_DAYS_PATH = '/api/leaderboard/days';
export const leaderboardBoardPath = (date: string, at: number): string =>
  `/api/leaderboard/${encodeURIComponent(date)}?at=${Math.floor(at)}`;
export const leaderboardCoveragePath = (date: string): string =>
  `/api/leaderboard/${encodeURIComponent(date)}/coverage`;
export const hodMomoHistoryPath = (date: string, until: number): string =>
  `/api/hod-momo/history/${encodeURIComponent(date)}?until=${Math.floor(until)}`;

/**
 * Mirrors backend LEADERBOARD_RECORD_SETTLE_SEC: a recorded board stamped at
 * minute m was taken within this many seconds after m, so the playhead sees it
 * only from m + settle. The desk keys its one-a-minute fetch on the same
 * shifted minute, so it never asks twice inside one board minute.
 */
export const LEADERBOARD_RECORD_SETTLE_SEC = 1;
/** What a failed read says when the server gave no reason. */
export const LEADERBOARD_REQUEST_FAILED = 'Scanner board request failed';
export const LEADERBOARD_DAYS_REQUEST_FAILED = 'Scanner board day list request failed';
export const LEADERBOARD_COVERAGE_REQUEST_FAILED = 'Scanner board coverage request failed';
export const HOD_HISTORY_REQUEST_FAILED = 'HOD alert history request failed';
/** A failed board / alert read retries this often while the playhead stays in its minute. */
export const LEADERBOARD_PLAYBACK_RETRY_MS = 5_000;
/** Today's coverage grows while the recorder runs: the lane re-reads it this often (never a past day). */
export const LEADERBOARD_COVERAGE_TODAY_REFRESH_MS = 60_000;

/** Board lists the Scanner shows; a reconstructed day's one `market` board is shown under Gainers. */
export const LEADERBOARD_BOARD_MARKET = 'market';
export const LEADERBOARD_SOURCE_RECORDED = 'recorded';
export const LEADERBOARD_SOURCE_RECONSTRUCTED = 'reconstructed';
export const LEADERBOARD_SOURCE_WORD: Record<string, string> = {
  recorded: 'recorded',
  reconstructed: 'rebuilt',
};
export const LEADERBOARD_SOURCE_TITLE: Record<string, string> = {
  recorded: 'The board Nova showed at this minute, as recorded.',
  reconstructed: 'A board rebuilt from minute bars that had closed by this minute -- the whole market, not the desk\'s IBKR lists.',
};

/** Board header while playback is active: `Sim · 2026-09-21 07:42 ET · recorded`. */
export const LEADERBOARD_LABEL_LEAD = 'Sim';
export const LEADERBOARD_LABEL_LOADING = 'loading';
export const LEADERBOARD_LABEL_TITLE =
  'The Scanner follows the Sim playhead: the board as it stood at this minute. Follow wall clock returns to live.';
export const leaderboardLabel = (date: string, clock: string, word: string): string =>
  `${LEADERBOARD_LABEL_LEAD} · ${date} ${clock} ET${word ? ` · ${word}` : ''}`;

/** Why there is no board at the playhead (gap `reason`), in the operator's words. */
export const LEADERBOARD_GAP_OUTSIDE_SESSION = 'Outside the 04:00-20:00 session';
export const LEADERBOARD_GAP_DAY_NOT_RECORDED = 'No board recorded for this day';
export const leaderboardGapText = (reason: string, range: string): string => {
  switch (reason) {
    case 'not_running':
      return `No board: Nova not running${range ? ` ${range}` : ''}`;
    case 'feed_down':
      return `No board: IBKR feed down${range ? ` ${range}` : ''}`;
    case 'not_recorded':
      return range ? `No board recorded ${range}` : LEADERBOARD_GAP_DAY_NOT_RECORDED;
    case 'outside_session':
      return LEADERBOARD_GAP_OUTSIDE_SESSION;
    default:
      return `No board${range ? ` ${range}` : ''}`;
  }
};
/** How the run before a `not_running` gap ended (`gap.stop`). */
export const LEADERBOARD_GAP_STOP_WORD: Record<string, string> = {
  shutdown: 'Nova was closed',
  unexpected: 'Nova stopped unexpectedly',
};

/** Per-list absences while playback is active. */
export const leaderboardLoadingText = (clock: string): string => `Loading the board at ${clock} ET…`;
export const leaderboardErrorText = (clock: string, error: string): string =>
  `Could not load the board at ${clock} ET: ${error}`;
export const LEADERBOARD_NOT_REBUILT =
  'Not rebuilt for this day -- a rebuilt day has one whole-market board, shown under Gainers.';
export const leaderboardListNotRecorded = (label: string, clock: string): string =>
  `No ${label} list recorded at ${clock} ET`;
export const leaderboardListUnavailable = (label: string, clock: string, state: string): string =>
  `The ${label} list was ${state === 'feed_down' ? 'down with the IBKR feed' : 'unavailable'} at ${clock} ET`;
export const leaderboardListEmpty = (label: string, clock: string): string =>
  `No ${label} on the board at ${clock} ET`;
/** Catalysts are live-only: nothing records them per minute. */
export const LEADERBOARD_CATALYSTS_NOT_RECORDED =
  'Catalysts are live-only -- not recorded per minute, so Sim playback has none to show.';

/** Row marks on a played-back board. */
export const LEADERBOARD_HALTED_LABEL = 'HALTED';
export const LEADERBOARD_HALTED_TITLE = 'Halted at this minute, from the halt log (IBKR tick 49 / Nasdaq halts).';
export const LEADERBOARD_NEWS_UNKNOWN_TITLE = 'News at this minute was not recorded.';

/** The thin lane under the Sim band: where the Scanner board was recorded / rebuilt that day. */
export const leaderboardLaneTitle = (word: string, ranges: string): string =>
  ranges ? `Scanner board ${word} ${ranges} ET` : `No Scanner board ${word} this day`;
export const leaderboardLaneGapsTitle = (gaps: string): string => `No board: ${gaps}`;
export const LEADERBOARD_LANE_GAP_WORD: Record<string, string> = {
  not_running: 'Nova not running',
  feed_down: 'IBKR feed down',
  not_recorded: 'not recorded',
  outside_session: 'outside the session',
};

/** The Sim strip's Day picker (between the transport and the band). */
export const SIM_DAY_PICKER_LABEL = 'Day';
export const SIM_DAY_PICKER_TITLE =
  'Move Sim to a day with a Scanner board -- recorded by Nova or rebuilt -- parked at 07:00 ET with nothing loaded.';
export const SIM_DAY_PICKER_TODAY = 'Today';
export const SIM_DAY_PICKER_RECORDED = 'rec';
export const SIM_DAY_PICKER_REBUILT = 'rebuilt';
export const SIM_DAY_PICKER_FAILED = 'Could not move Sim to that day';

/** The Day calendar: what each day has on file, each from its own source. */
export const SIM_DAY_CAL_RECORDED = 'Scanner board recorded by Nova';
export const SIM_DAY_CAL_SESSIONS = 'Your Session Records';
export const SIM_DAY_CAL_REBUILT = 'Scanner board rebuilt from minute bars';
export const SIM_DAY_CAL_NOTHING = 'Nothing on file';
export const SIM_DAY_CAL_CLOSED = 'Exchange closed -- cannot be opened in Sim';
export const simDayCalSessions = (symbols: string[]): string => `${SIM_DAY_CAL_SESSIONS}: ${symbols.join(', ')}`;
export const SIM_DAY_CAL_TODAY = 'Today (live edge)';
export const SIM_DAY_CAL_PREV = 'Previous month';
export const SIM_DAY_CAL_NEXT = 'Next month';
export const SIM_DAY_CAL_YEAR = 'Year';
export const SIM_DAY_CAL_WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'] as const;
/** The calendar's box, for placing it inside the window (matches simDayCalendar.css). */
export const SIM_DAY_CAL_WIDTH_PX = 248;
export const SIM_DAY_CAL_HEIGHT_PX = 300;

/** The leaderboard recorder runs whenever Nova does; only a write failure speaks (one toast). */
export const LEADERBOARD_RECORDER_FAILED_TITLE = 'Scanner board recording failed';
export const leaderboardRecorderFailedBody = (error: string | null): string =>
  `${error ?? 'The recorder reported a failure without a reason.'} Playback has a gap from here until it recovers.`;
export const LEADERBOARD_RECORDER_DISMISS = 'Dismiss';

/** HOD Momo strip while it follows the Sim playhead. */
export const HOD_REPLAY_FEED_TITLE = 'Alerts raised by the Sim playhead, from that day\'s alert history.';
export const hodReplayFeedLabel = (clock: string): string => `replay ${clock}`;
export const hodReplayLoading = (clock: string): string => `Loading alerts raised by ${clock} ET…`;
export const hodReplayEmpty = (date: string, clock: string): string => `No alerts raised by ${clock} ET on ${date}`;
export const hodReplayError = (error: string): string => `Alert history did not load: ${error}`;
export const HOD_REPLAY_CLEAR_TITLE = 'Past alerts are history -- nothing to clear while Sim replays.';

/** REC chip card: a recording auto-record started (07:00-10:00 ET leaders). */
export const AUTO_RECORD_CHIP_LINE = 'auto -- recorded by auto-record (07:00-10:00 ET leaders); stops on its own';
