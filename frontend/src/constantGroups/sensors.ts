/** L2 Brain Sensor Board -- observation UI only. No orders. */
export const SENSORS_NAV_ID = 'sensors';
export const SENSORS_NAV_LABEL = 'Sensors';
export const SENSORS_BOARD_TITLE = 'L2 Brain sensors';
export const SENSORS_BOARD_HINT =
  'Read-only smoke board. Each chip is an independent GET. Sensors never Place.';
export const SENSORS_SYMBOL_LABEL = 'Symbol';
export const SENSORS_REFRESH_LABEL = 'Refresh';
export const SENSORS_EMPTY_CATALOG = 'Sensor catalog is empty -- API returned no rows.';
export const SENSORS_LOAD_ERROR = 'Sensor board failed to load.';
export const SENSORS_NO_VALUE = 'No reading yet';
export const SENSORS_POLL_MS = 4000;
export const SENSORS_DEFAULT_LIQUID = 'AAPL';
export const SENSORS_LIVE = 'live';
export const SENSORS_STUB = 'stub';
export const SENSORS_COMPUTED_STUB = 'computed_stub';
export const SENSORS_ACCOUNT_HINT =
  'L2 Brain Sensor Board is Settings > Sensors -- read-only GET smoke tests.';

// ── QA pass two (2026-09-22): Scanner / header / layout batch ────────────
/** W16: a bar-derived reading whose newest 1-minute bar is older than this is stale. */
export const SENSORS_BARS_STALE_SEC = 30 * 60;
export const SENSORS_STALE = 'stale';
export const SENSORS_STALE_TITLE_PREFIX = '1-minute bars end';
export const SENSORS_STALE_TITLE_SUFFIX = 'ET -- open a chart for this symbol to refresh them';

