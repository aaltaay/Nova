/**
 * The one navigation rail (approved UX redesign, first slice).
 * Labels, tunables and the persisted-state contract for NavRail.
 */

export const NAV_RAIL_WIDTH_PX = 200;
export const NAV_RAIL_COLLAPSED_WIDTH_PX = 56;

/** Accessible name of the rail landmark. */
export const NAV_RAIL_ARIA_LABEL = 'Navigation';

export const NAV_RAIL_LABEL_DESK = 'Desk';
export const NAV_RAIL_LABEL_TRADER = 'Trader';
export const NAV_RAIL_LABEL_SCANNER = 'Scanner';
export const NAV_RAIL_LABEL_ACCOUNT = 'Account';
export const NAV_RAIL_LABEL_BOTS = 'Bots';
export const NAV_RAIL_LABEL_RECORDS = 'Records';
export const NAV_RAIL_LABEL_SETTINGS = 'Settings';

export const NAV_RAIL_TITLE_DESK = 'Desk -- the Scanner + Trader hybrid';
export const NAV_RAIL_TITLE_TRADER =
  'Open Trader for the selected symbol, or SPY if none is selected';
export const NAV_RAIL_TITLE_SCANNER = 'Scanner lists and signals';
export const NAV_RAIL_TITLE_ACCOUNT =
  'Account overview -- positions, orders, and trading habit reports';
export const NAV_RAIL_TITLE_BOTS = 'Bots -- strategy and bot autonomy';
export const NAV_RAIL_TITLE_RECORDS = 'Records -- Session Records';
export const NAV_RAIL_TITLE_SETTINGS = 'Open Settings';

export const NAV_RAIL_FOLD_TITLE = 'Fold the Scanner lists';
export const NAV_RAIL_UNFOLD_TITLE = 'Unfold the Scanner lists';
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
 * by guesswork (persisted-state.mdc).
 */
export const NAV_RAIL_STORAGE_KEY = 'nova.navRail.v1';
export const NAV_RAIL_SCHEMA_VERSION = 1;

/** CustomEvent name -- the rail asks the mounted dashboard to select a tab. */
export const NAV_RAIL_SELECT_TAB_EVENT = 'nova:nav-rail-select-tab';

/** Desk placeholder (the hybrid itself is the next slice). */
export const DESK_PAGE_TITLE = 'Desk';
export const DESK_PAGE_PLACEHOLDER =
  'Desk -- the Scanner + Trader hybrid lands in the next PR';

/** Records placeholder page. */
export const RECORDS_PAGE_TITLE = 'Records';
export const RECORDS_PAGE_SUBTITLE = "Today's Session Records";
export const RECORDS_PAGE_EMPTY = 'No Session Records today.';
export const RECORDS_PAGE_LOADING = 'Loading Session Records…';
export const RECORDS_PAGE_ERROR_PREFIX = 'Session Records unavailable:';
export const RECORDS_PAGE_RECORDING = 'Recording';
export const RECORDS_PAGE_OPEN_TRADER = 'Open in Trader';
export const RECORDS_PAGE_COL_SYMBOL = 'Symbol';
export const RECORDS_PAGE_COL_PRINTS = 'Prints';
export const RECORDS_PAGE_COL_SEGMENTS = 'Segments';
export const RECORDS_PAGE_COL_MISSING = 'Missing';
export const RECORDS_PAGE_COL_STATUS = 'Status';
