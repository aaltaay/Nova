/**
 * The one navigation rail (approved UX redesign, first slice).
 * Labels, tunables and the persisted-state contract for NavRail.
 */

export const NAV_RAIL_WIDTH_PX = 200;
export const NAV_RAIL_COLLAPSED_WIDTH_PX = 56;

/** Accessible name of the rail landmark. */
export const NAV_RAIL_ARIA_LABEL = 'Navigation';

export const NAV_RAIL_LABEL_MARKET = 'Market';
export const NAV_RAIL_LABEL_TRADER = 'Trader';
export const NAV_RAIL_LABEL_SCANNER = 'Scanner';
export const NAV_RAIL_LABEL_ACCOUNT = 'Account';
export const NAV_RAIL_LABEL_BOTS = 'Bots';
export const NAV_RAIL_LABEL_RECORDS = 'Records';
export const NAV_RAIL_LABEL_CRYPTOS = 'Cryptos';
export const NAV_RAIL_LABEL_FOLLOWED = 'Following';
export const NAV_RAIL_LABEL_SETTINGS = 'Settings';

export const NAV_RAIL_TITLE_MARKET =
  'Market -- the day at a glance: futures, sectors, breadth and the small-cap climate';
export const NAV_RAIL_TITLE_TRADER =
  'Open Trader for the selected symbol, or SPY if none is selected';
export const NAV_RAIL_TITLE_SCANNER = 'Scanner lists and signals';
export const NAV_RAIL_TITLE_ACCOUNT =
  'Account overview -- positions, orders, and trading habit reports';
export const NAV_RAIL_TITLE_BOTS = 'Bots -- strategy and bot autonomy';
export const NAV_RAIL_TITLE_RECORDS = 'Records -- Session Records';
export const NAV_RAIL_TITLE_CRYPTOS = 'Cryptos -- the 24/7 crypto market, and the stocks it moves';
export const NAV_RAIL_TITLE_FOLLOWED =
  'Following -- the traders your feed follows: what they hold now, their entries and exits, priced with IBKR';
export const NAV_RAIL_TITLE_SETTINGS = 'Open Settings';

export const NAV_RAIL_COLLAPSE_TITLE = 'Collapse to icons';
export const NAV_RAIL_EXPAND_TITLE = 'Expand the rail';

/** Scanner tree group headings, in rail order. */
export const NAV_RAIL_GROUP_LABELS = {
  lists: 'Lists',
  signals: 'Signals',
  mine: 'Mine',
} as const;

/** Mirrors backend CAPTURE_MAX_CONCURRENT -- IBKR allows three depth lines. */
export const NAV_RAIL_RECORDING_MAX = 3;

/** Tooltip on the Records badge dot: "2 of 3 recording". */
export const navRailRecordingTitle = (count: number, max: number): string =>
  `${count} of ${max} recording`;

/**
 * Persisted rail chrome (collapse + Scanner fold). Owner: components/navRailPersist.ts.
 * Invalidation: schema bump -- an unknown schema_version is ignored, never migrated
 * by guesswork (persisted-state.mdc). v2 makes `collapsed` tri-state (null = the
 * operator has not chosen, so the rail follows the view -- labels on every view
 * today); v1 is migrated by a known rule, see readNavRailPrefs.
 */
export const NAV_RAIL_STORAGE_KEY = 'nova.navRail.v1';
export const NAV_RAIL_SCHEMA_VERSION = 2;
export const NAV_RAIL_SCHEMA_VERSION_LEGACY = 1;

/** CustomEvent name -- the rail asks the mounted dashboard to select a tab. */
export const NAV_RAIL_SELECT_TAB_EVENT = 'nova:nav-rail-select-tab';

/** Records page (the rest of its words: pages/records/recordsConstants.ts). */
export const RECORDS_PAGE_TITLE = 'Records';
export const RECORDS_PAGE_EMPTY = 'No Session Records yet.';
export const RECORDS_PAGE_LOADING = 'Loading Session Records…';
export const RECORDS_PAGE_ERROR_PREFIX = 'Session Records unavailable:';
export const RECORDS_PAGE_REPLAY_FAILED = 'Replay did not load:';

// ── QA batch: Scanner / HOD / desk honesty (2026-09-22) ────────────────────
/** HOD Momo / Running Up focus the alert strip; the board keeps its list (QA V6). */
export const NAV_RAIL_STRIP_FOCUS_TITLE = 'shows in the alert strip above the board';
/** The HOD / Running Up counts are symbols, beside a strip that counts alerts (QA V31). */
export function navRailAlertSymbolsTitle(count: number): string {
  return `${count} symbol${count === 1 ? '' : 's'} alerted today`;
}
