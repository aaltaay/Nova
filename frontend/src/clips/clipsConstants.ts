/**
 * Share clips (ADR 039): the desk's words and numbers. The electron side's
 * numbers (the caps, the 30 minutes, the last 5 min) come on the view; these
 * are the desk's own.
 */

/** How often a window re-reports its Trader tab when nothing changed (the main process keeps 30 min of them). */
export const CLIP_TAB_REPORT_MS = 2_000;
/** A toast stays this long unless pointed at. */
export const CLIP_TOAST_TTL_MS = 12_000;
/** X's limit for a free account's video (the export dialog's hint). */
export const CLIP_X_FREE_LIMIT_SEC = 140;
/** The export dialog's timeline shows the clip with this much either side. */
export const CLIP_TIMELINE_PAD_SEC = 120;
/**
 * The data-testid each reported panel carries inside a Trader tab (clipPlan.mjs
 * CLIP_PANELS); a panel of several parts lists them, and the report takes the
 * box around them all. A blur is only as good as its selector:
 * `clipPanels.test.ts` fails when one names an element no component renders.
 * The quote is the rail's price head and stats; the ticket is the rail's whole
 * trade card (the quick bar, POS, the ticket, its cost and BP after); the
 * orders dock holds its footer's position line.
 */
export const CLIP_PANEL_SELECTORS = {
  charts: '[data-testid="chart-grid"]',
  level2: '[data-testid="stock-view-l2-col"]',
  tape: '[data-testid="stock-view-tape-col"]',
  quote: '[data-testid="stock-view-quote-head"], [data-testid="stock-view-quote-stats"]',
  plan: '[data-testid="stock-read-plan"]',
  ticket: '[data-testid="stock-view-open-card"]',
  orders: '[data-testid="stock-view-open-orders-dock"]',
} as const;
export type ClipPanelId = keyof typeof CLIP_PANEL_SELECTORS;
export const CLIP_PANEL_LABELS: Record<ClipPanelId, string> = {
  charts: 'Charts',
  level2: 'Level 2',
  tape: 'Time & Sales',
  quote: 'Quote',
  plan: 'Plan',
  ticket: 'Order ticket',
  orders: 'Positions & orders',
};
/** Panels that carry the operator's size or money, offered for blur by default order. */
export const CLIP_PRIVATE_PANELS: ClipPanelId[] = ['plan', 'ticket', 'orders'];

export const CLIP_ROLE = 'CLIP';
export const CLIP_BUTTON_LABEL = 'Record';
export const CLIP_BUTTON_TITLE = 'Record this symbol: market data (Level 2 + Time & Sales) or a video clip of this tab';
export const CLIP_MENU_TITLE = 'Record';
export const CLIP_MENU_KEYS = 'Keys: Nova Actions › Start / stop clip';
export const CLIP_MD_TITLE = 'Market data';
export const CLIP_MD_DESC = 'Level 2 and Time & Sales to disk, so the session replays in Sim.';
export const CLIP_VIDEO_TITLE = 'Video clip';
export const CLIP_VIDEO_DESC = 'A cut from the screen recording that already runs: starting it starts nothing, so it costs nothing while you trade.';
export const CLIP_START = 'Start';
export const CLIP_STOP = 'Stop';
export const CLIP_START_CLIP = 'Start clip';
export const CLIP_STOP_CLIP = 'Stop clip';
export const CLIP_START_BOTH = 'Start both';
export const CLIP_START_BOTH_HINT = 'market data and a video clip, each with its own stop';
export const CLIP_SAVE_LAST = 'Save the last 5 min';
export const CLIP_SAVE_LAST_HINT = 'a clip that ends now; trim it later';
export const CLIP_HQ = 'High quality';
export const CLIP_HQ_HINT_OFF = '30 fps capture of this window';
export const CLIP_PICTURE_LINE = 'header left out · change it when you export';
export const CLIP_RECORDS_LINK = 'Records › Video clips';
export const CLIP_NEED_DESKTOP = 'Video clips need the desktop app: a browser tab cannot see the screen. Market data still records from here.';
export const CLIP_NEED_DESKTOP_WHY = 'Video clips need the desktop app';
export const CLIP_HQ_FULL_WHY = 'Both high-quality captures are in use: stop one, or record this clip as a cut.';
export const CLIP_MD_FULL_WHY = 'All 3 Level 2 lines are recording: stop one to record this tape. A video clip needs no line.';
export const CLIP_BUSY_WHY = 'Working on it…';

export const CLIP_TOAST_REGION = 'Clips';
export const CLIP_TOAST_SAVED = 'Clip saved';
export const CLIP_TOAST_LAST = 'Clip made from the last 5 minutes';
export const CLIP_TOAST_EXPORTED = 'Clip exported';
export const CLIP_TOAST_EXPORT_FAILED = 'Export failed';
export const CLIP_EXPORT_ACTION = 'Export…';
export const CLIP_LATER = 'Later';
export const CLIP_SHOW_IN_FOLDER = 'Show in folder';
export const CLIP_PLAY = 'Play';
export const CLIP_EXPORT_AGAIN = 'Export again';
export const CLIP_DELETE = 'Delete';
export const CLIP_CANCEL = 'Cancel';
export const CLIP_RETRY = 'Retry';
export const CLIP_OPEN_TRADER = 'Open in Trader';

export const CLIP_EXPORT_TITLE = 'Export clip';
export const CLIP_EXPORT_PICTURE = 'Picture';
export const CLIP_EXPORT_IN_PICTURE = 'In the picture';
export const CLIP_EXPORT_CHART_POSITION = 'The charts draw your position line (size and P&L) while you hold the stock, and no blur here covers it.';
export const CLIP_EXPORT_OUTPUT = 'Output';
export const CLIP_EXPORT_TRIM = 'Trim';
export const CLIP_EXPORT_TRIM_HINT = 'drag the white handles; the start can move before the clip wherever the tab shows green (Nova keeps 30 min of where each tab was)';
export const CLIP_EXPORT_BUTTON = 'Export MP4';
export const CLIP_EXPORT_NOTE = 'Exports in the background; Records › Video clips shows its progress. Nova never posts it: sharing the file is up to you.';
export const CLIP_PICTURE_OPTIONS = {
  trader_tab: { label: "the Trader tab", hint: 'charts, Level 2, Time & Sales, the plan; the header is left out', warn: null },
  panels: { label: 'Panels I pick', hint: 'the box around the ones you tick', warn: null },
  window: { label: 'The whole Nova window', hint: null, warn: "shows the header: account id, Day's P&L, TAV" },
  monitor: { label: 'The whole monitor', hint: null, warn: 'everything on that screen, other apps too' },
} as const;
export type ClipPicture = keyof typeof CLIP_PICTURE_OPTIONS;

export const CLIP_RECORDS_TAB_SESSIONS = 'Session Records';
export const CLIP_RECORDS_TAB_CLIPS = 'Video clips';
export const CLIP_RECORDS_EMPTY = 'No video clips yet. Press the red ● on a Trader tab, or right-click a ticker › Record.';
export const CLIP_RECORDS_KEPT = 'Deleting a clip deletes its file only: the screen recording it came from is kept.';
