/** Labels + layout tunables for the Trader chart right-click menu (WID-030). */

export const CHART_CONTEXT_MENU_LABEL = 'Chart actions';
export const CHART_CONTEXT_MENU_CREATE_ORDER = 'Create New Order';
export const CHART_CONTEXT_MENU_BUY = 'Buy';
export const CHART_CONTEXT_MENU_SELL = 'Sell';
export const CHART_CONTEXT_MENU_CLOSE_POSITION = 'Close Position';
export const CHART_CONTEXT_MENU_DRAWINGS = 'Drawings';
export const CHART_CONTEXT_MENU_RESET = 'Reset Chart';
export const CHART_CONTEXT_MENU_SNAPSHOT = 'Snapshot';

/**
 * Shown under the order rows. Nova stages orders on the trade ticket instead of
 * firing them from the chart, and the menu must say so rather than imply a
 * one-click fill (Webull's menu does place immediately -- Nova's does not).
 */
export const CHART_CONTEXT_MENU_ORDER_HINT =
  'Opens the trade ticket — Place to submit.';

/** Right-clicks that land on these never open the chart menu (tag owns its own). */
export const CHART_CONTEXT_MENU_IGNORE_SELECTOR =
  '.chart-position-tag, .chart-context-menu, .chart-toolbar, button';

export const CHART_CONTEXT_MENU_WIDTH_PX = 236;
export const CHART_CONTEXT_MENU_EDGE_PAD_PX = 8;
/** Estimate used before the menu measures itself, so the first paint is on-screen. */
export const CHART_CONTEXT_MENU_EST_HEIGHT_PX = 260;
export const CHART_CONTEXT_SUBMENU_WIDTH_PX = 190;
