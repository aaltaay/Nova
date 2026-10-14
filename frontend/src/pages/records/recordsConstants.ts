/**
 * Records › Market data words (operator ask 2026-10-14: "i need a way to turn
 * off the recording and i feel like this entire screen need better ux").
 * Every word on the page lives here; a stop says who did it.
 */
import type { AutoRecordMode } from '../../ibkr/types';
import type { EndedTone } from './recordsModel';

export const recordsSavedTo = (root: string): string => `Saved to ${root}`;

/* ── Recording now ── */
export const RECORDS_NOW_TITLE = 'Recording now';
export const RECORDS_NOT_RECORDING_TITLE = 'Not recording';
export const recordsSlotsInUse = (used: number, max: number): string => `${used} of ${max} recording slots in use`;
export const RECORDS_STOP_ALL = 'Hold to stop all';
export const RECORDS_STOP_ALL_LABEL = 'Hold to stop every recording';
export const RECORDS_STOP = 'Hold to stop';
export const RECORDS_STOP_SHORT = 'Stop';
export const RECORDS_OPEN_TRADER = 'Open in Trader';
export const RECORDS_TAG_AUTO = 'auto';
export const RECORDS_TAG_YOU = 'you';
export const RECORDS_STARTED_BY_YOU = 'You started it';
export const RECORDS_AUTO_RECORD = 'Auto-record';
export const recordsSegmentLine = (args: {
  elapsed: string; since: string | null; resumedAt: string | null; resumedWhy: string | null; prints: number; l2: number;
}): string => {
  const since = args.since ? ` · since ${args.since}` : '';
  const resumed = args.resumedAt ? `, resumed ${args.resumedAt}${args.resumedWhy ? ` ${args.resumedWhy}` : ''}` : '';
  return `${args.elapsed} this segment${since}${resumed} · ${args.prints.toLocaleString()} prints · ${args.l2.toLocaleString()} book updates`;
};
/** Why the segment before this one ended, after "resumed 14:36". */
export const RECORDS_RESUMED_AFTER: Record<string, string> = {
  restart: 'after a Nova restart',
  failure: 'after it stopped on its own',
};
export const RECORDS_FREE_SLOT = 'free slot';
export const RECORDS_FREE_AUTO_ON =
  'Auto-record may use it while its window is open. Your own Record and your Level 2 always come first: it gives a line back the moment you need one.';
export const RECORDS_FREE_AUTO_OFF = 'Auto-record is off, so only a Record you start uses it.';
export const RECORDS_STOP_FAILED = 'Stop did not go through:';
export const RECORDS_NOTHING_AUTO_ON =
  'Nothing is recording. Auto-record starts one on a free line when a setup arms in its window; you can record any symbol yourself.';
export const recordsNothingAutoOff = (mode: AutoRecordMode, until: string | null): string =>
  mode === 'off_today'
    ? `Auto-record is off for today and starts nothing. It comes back on at ${until ?? '04:00 ET'}.`
    : 'Auto-record is off and starts nothing until you turn it on.';
export const RECORDS_TURN_AUTO_ON = 'Turn auto-record on now';
export const RECORDS_RECORD_A_SYMBOL = 'Record a symbol…';
export const RECORDS_RECORD_SYMBOL_PLACEHOLDER = 'Symbol';
export const RECORDS_RECORD_START = 'Record';
export const RECORDS_RECORD_CANCEL = 'Cancel';
export const RECORDS_RECORD_FAILED = 'Record did not start:';
export const RECORDS_RECORD_BUSY = 'Starting the recording -- this unlocks when Nova answers.';
export const RECORDS_RECORD_NEEDS_SYMBOL = 'Type the symbol to record first.';

/* ── Auto-record ── */
export const RECORDS_AUTO_TITLE = 'Auto-record';
export const RECORDS_AUTO_SUB = 'starts recordings on its own';
export const RECORDS_AUTO_MODES: { mode: AutoRecordMode; label: string }[] = [
  { mode: 'on', label: 'On' },
  { mode: 'off_today', label: 'Off for today' },
  { mode: 'off', label: 'Off' },
];
export const RECORDS_AUTO_SWITCH_LABEL = 'Auto-record';
export const RECORDS_AUTO_BUSY = 'Saving the switch -- this unlocks when Nova answers.';
export const RECORDS_AUTO_UNAVAILABLE =
  'Nova did not say how auto-record is set (a backend older than this switch, or no status yet).';
export const RECORDS_AUTO_ENV = 'NOVA_AUTO_RECORD=0 in .env keeps auto-record off. Remove that line and restart Nova to use this switch.';
export const RECORDS_AUTO_FAILED = 'The switch did not change:';
export const RECORDS_AUTO_OPEN_NOW = 'Open now:';
export const recordsOpenWindows = (labels: string, until: string): string => ` ${labels}, until ${until} ET.`;
export const recordsHolding = (symbols: string): string => ` It is holding ${symbols}.`;
export const RECORDS_HOLDING_NONE = ' It holds no line now.';
export const recordsOpensAt = (at: string): string => `Closed now. It opens at ${at} ET.`;
export const RECORDS_CLOSED_TODAY = 'Closed for today. It opens again on the next trading day.';
export const RECORDS_AUTO_OFF_TODAY = (until: string): string => `Off for today. It starts nothing until ${until}.`;
export const RECORDS_AUTO_OFF = 'Off. It starts nothing until you turn it on.';
export const recordsTurningOffStops = (symbols: string): string =>
  `Turning it off stops ${symbols} now. A recording you started yourself keeps going.`;
export const RECORDS_TURNING_OFF_NOTHING = 'Turning it off starts nothing new. A recording you started yourself is never touched.';
export const RECORDS_AUTO_FINE_TODAY = 'Off for today';
export const RECORDS_AUTO_FINE_TODAY_TAIL = ' comes back on at 04:00 ET tomorrow. ';
export const RECORDS_AUTO_FINE_OFF = 'Off';
export const RECORDS_AUTO_FINE_OFF_TAIL = ' stays off, through restarts, until you turn it on.';
export const RECORDS_LEADERS_LABEL = 'Top gainers';
export const RECORDS_NOW = 'now';
export const recordsWindowTitle = (label: string, start: string, end: string, open: boolean): string =>
  `${label}: ${start}-${end} ET${open ? ' (open now)' : ''}`;
export const recordsSwitchError = (error: string): string => `${error}.`;

/* ── The day's table ── */
export const RECORDS_TODAY = 'today';
export const RECORDS_FILTER_PLACEHOLDER = 'Filter symbols';
export const RECORDS_FILTERS: { id: 'all' | 'recording' | 'gaps' | 'cut' | 'you'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'recording', label: 'Recording' },
  { id: 'gaps', label: 'With gaps' },
  { id: 'cut', label: 'Cut by a restart' },
  { id: 'you', label: 'Stopped by you' },
];
export const RECORDS_LEGEND_RECORDED = 'recorded';
export const RECORDS_LEGEND_LIVE = 'recording now';
export const RECORDS_LEGEND_MISSING = 'gap (data missing)';
export const RECORDS_LEGEND_PLANNED = 'stopped on purpose';
export const RECORDS_LEGEND_MARKET = '09:30–16:00';
export const RECORDS_COL_SYMBOL = 'Symbol';
export const RECORDS_COL_RECORDED = 'Recorded';
export const RECORDS_COL_PRINTS = 'Prints';
export const RECORDS_COL_BOOK = 'Book updates';
export const RECORDS_COL_GAPS = 'Gaps';
export const RECORDS_COL_ENDED = 'Ended';
export const RECORDS_COL_SIZE = 'Size';
export const RECORDS_ENDED_DEFAULT_SORT = '▼ newest';
export const RECORDS_COVERAGE_LABEL = 'When it recorded, ET';
export const RECORDS_GAPS_NONE = 'none';
export const recordsGapTitle = (from: string, to: string, why: string): string => `${from}-${to} ET ${why}`;
/** A gap's cause, after its times. */
export const RECORDS_GAP_WHY: Record<string, string> = {
  operator: 'stopped by you',
  auto: 'stopped by auto-record',
  restart: 'missing: a Nova restart',
  failure: 'missing: it stopped on its own',
  rotation: 'missing: rolled to a new day',
};
export const RECORDS_GAP_WHY_UNKNOWN = 'missing';
export const recordsEndedAt = (at: string): string => `Ended ${at} ET`;
export const RECORDS_NO_MATCH = 'No record matches this filter.';
export const RECORDS_EARLIER_DAYS = 'Earlier days';
export const recordsDayGaps = (n: number): string => `${n} ${n === 1 ? 'symbol' : 'symbols'}`;
export const recordsDaySymbols = (n: number): string => `${n} ${n === 1 ? 'symbol' : 'symbols'}`;
export const recordsDayCut = (n: number): string => `${n} cut by a restart`;
export const recordsShowDay = (n: number): string => `Show ${n}`;
export const RECORDS_HIDE_DAY = 'Hide';
export const recordsShowMoreDays = (n: number): string => `Show ${n} more ${n === 1 ? 'day' : 'days'}`;
export const RECORDS_DAYS_PAGE = 6;
export const RECORDS_REPLAY = 'Replay in Sim';
export const RECORDS_REPLAY_TITLE = 'Load this Session Record into the Sim replay and open it in Trader';
export const RECORDS_REPLAY_BUSY = 'Loading a Session Record into Sim -- wait for it to finish';

/* ── Who ended it ── */
export const RECORDS_ENDED_LIVE = 'Recording';
/** A live recording's earlier segment ended this way, so this one resumed. */
export const RECORDS_ENDED_RESUMED: Record<string, string> = {
  restart: 'resumed after a restart',
  failure: 'resumed after it stopped on its own',
};
export const RECORDS_ENDED_STATUS: Record<string, { words: string; tone: EndedTone }> = {
  interrupted: { words: 'Cut by a Nova restart', tone: 'warn' },
  failed: { words: 'Failed', tone: 'bad' },
};
export const RECORDS_ENDED_STOPPED: Record<string, { words: string; tone: EndedTone }> = {
  operator: { words: 'Stopped by you', tone: 'muted' },
  auto: { words: 'Stopped by auto-record', tone: 'muted' },
  failure: { words: 'Stopped on its own', tone: 'bad' },
  restart: { words: 'Cut by a Nova restart', tone: 'warn' },
  rotation: { words: 'Rolled to a new day', tone: 'muted' },
};
/** Stops somebody chose: the gap after them is not missing data. Mirrors backend CAPTURE_PLANNED_STOPS. */
export const RECORDS_PLANNED_STOP_REASONS: ReadonlySet<string> = new Set(['operator', 'auto']);
