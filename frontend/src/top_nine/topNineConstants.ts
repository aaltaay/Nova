/**
 * The Top 9 pop-up (operator ask, 2026-10-26): a 3x3 grid of compact 1-minute charts for the first
 * nine rows of Gappers, Gainers or After Hours, with an obvious mark when a stock changes rank.
 * Schema: architecture/schema/scanner.md, "The Top 9 pop-up".
 */
import type { RankListId } from '../stock_view';

export const TOP_NINE_SIZE = 9;

export type TopNineList = Extract<RankListId, 'gappers' | 'gainers' | 'afterhours'>;

export const TOP_NINE_LISTS: readonly { list: TopNineList; label: string }[] = [
  { list: 'gappers', label: 'Gappers' },
  { list: 'gainers', label: 'Gainers' },
  { list: 'afterhours', label: 'After Hours' },
];

export function isTopNineList(value: unknown): value is TopNineList {
  return TOP_NINE_LISTS.some((l) => l.list === value);
}

export const TOP_NINE_DEFAULT_LIST: TopNineList = 'gainers';

/** `?view=top9` loads the pop-up's own page (main.tsx), not the desk. */
export const TOP_NINE_QUERY_VIEW = 'top9';
/** One pop-up: a second click focuses it (and switches its list) instead of opening another. */
export const TOP_NINE_WINDOW_NAME = 'nova-top-nine';
export const TOP_NINE_WINDOW_FEATURES = 'popup=yes,width=1600,height=960';

/** deskSharedPoll share the desk window publishes the boards on. */
export const TOP_NINE_SHARE = 'top-nine';
/** The pop-up's heartbeat (ms epoch): the desk publishes only while a pop-up is open. */
export const TOP_NINE_VIEWER_KEY = 'nova.topNine.viewer';
export const TOP_NINE_VIEWER_HEARTBEAT_MS = 2_000;
export const TOP_NINE_VIEWER_STALE_MS = 6_000;
/** The desk checks the boards this often and sends them when they changed (or the heartbeat is due). */
export const TOP_NINE_PUBLISH_MS = 1_000;
export const TOP_NINE_PUBLISH_HEARTBEAT_MS = 4_000;
/** No board from the desk for this long: the pop-up says the desk is not answering. */
export const TOP_NINE_DESK_SILENT_MS = 10_000;

/** prefStore keys: the list on screen (a grid button sets it too), the switch sound, and the stocks
 * muted for the day (right-click a tile). */
export const TOP_NINE_LIST_KEY = 'nova.topNine.list';
export const TOP_NINE_SOUND_KEY = 'nova.topNine.sound';
export const TOP_NINE_MUTED_KEY = 'nova.topNine.muted';

/** A switch is marked in full (border, pill, timer bar) this long, then a soft tint on the rank. */
export const TOP_NINE_MARK_FULL_MS = 30_000;
export const TOP_NINE_MARK_SOFT_MS = 150_000;
/** Switches kept per list for the bottom line. */
export const TOP_NINE_LOG_MAX = 30;

/** The chart: the last 90 one-minute candles, refreshed like the Trader's 1-minute pane. */
export const TOP_NINE_TIMEFRAME = '1Min';
export const TOP_NINE_CHART_MINUTES = 90;

/** A switch chimes, then the next switch inside this long stays quiet (operator ask, 2026-10-27:
 * "once every 30 seconds"). A halt is not held back by it. */
export const TOP_NINE_CHIME_COOLDOWN_MS = 30_000;
/** The switch chime: two rising notes, loud enough to hear over the desk (the old 0.05 tick was not). */
export const TOP_NINE_CHIME_NOTES_HZ: readonly number[] = [880, 1_320];
export const TOP_NINE_CHIME_NOTE_SEC = 0.12;
export const TOP_NINE_CHIME_GAIN = 0.2;
/** A stock on screen halted: three short lower beeps, unlike the chime. */
export const TOP_NINE_HALT_NOTES_HZ: readonly number[] = [740, 740, 740];
export const TOP_NINE_HALT_NOTE_SEC = 0.09;
export const TOP_NINE_HALT_GAP_SEC = 0.07;
export const TOP_NINE_HALT_GAIN = 0.22;

/** The LULD band on a tile: the Trader's 1-minute band, read from memory (ADR 047), every 3 s per tile. */
export const TOP_NINE_LULD_PATH = (symbol: string) => `/api/luld/${encodeURIComponent(symbol)}/trail`;
export const TOP_NINE_LULD_POLL_MS = 3_000;

/** No answer to a double-click from a desk window in this long: say so. */
export const TOP_NINE_OPEN_WAIT_MS = 600;

export const TOP_NINE_TITLE = 'Top 9';
export const TOP_NINE_OPEN_TITLE = (label: string) =>
  `Open the Top 9 of ${label}: nine 1-minute charts in a window of its own, marked when a stock changes rank.`;
export const TOP_NINE_TILE_TITLE = (symbol: string) => `Double-click to open ${symbol} in the Trader.`;
export const TOP_NINE_NO_DESK =
  'No Nova desk window answered. Open Nova, then double-click again.';
export const TOP_NINE_DESK_SILENT = 'Waiting for the Nova desk window to send its lists…';
export const TOP_NINE_AFTER_HOURS_EMPTY = 'No After Hours rows yet. The list fills from 4:01 PM ET.';
export const TOP_NINE_LIST_EMPTY = (label: string) => `No rows on ${label} right now.`;
export const TOP_NINE_SOUND_LABEL = 'Sound on switch';
export const TOP_NINE_SOUND_TITLE =
  'A chime when a stock on screen moves up or comes in, at most once every 30 s, and three beeps when one halts. '
  + 'Right-click a tile to mute that stock. The header mute silences it too.';
export const TOP_NINE_MUTE_LABEL = (symbol: string) => `Mute ${symbol}`;
export const TOP_NINE_UNMUTE_LABEL = (symbol: string) => `Unmute ${symbol}`;
export const TOP_NINE_MUTE_HINT = 'No chime or halt beeps from it today. Its marks still show.';
export const TOP_NINE_UNMUTE_HINT = 'Its switches and halts sound again.';
export const TOP_NINE_MUTED_TITLE = (symbol: string) => `${symbol} is muted for today. Right-click to unmute.`;
export const TOP_NINE_ON_TOP_LABEL = 'Keep on top';
export const TOP_NINE_ON_TOP_TITLE = 'Keep this window above the others.';
export const TOP_NINE_ON_TOP_WHY = 'Only the Nova desktop app can keep a window on top.';
export const TOP_NINE_LEGEND = {
  up: 'moved up',
  down: 'moved down',
  new: 'new in top 9',
  hold: 'marks stay 30 s',
} as const;
export const TOP_NINE_LOG_LABEL = 'Switches';
export const TOP_NINE_LOG_EMPTY = 'No switches yet.';
export const TOP_NINE_HALTED = 'HALTED';
export const TOP_NINE_NO_BARS = 'No 1-minute bars yet.';
export const TOP_NINE_LULD_NO_TAPE = 'LULD — no tape line held';
export const TOP_NINE_LULD_NONE = 'LULD —';
