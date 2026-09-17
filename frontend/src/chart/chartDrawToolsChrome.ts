/** Maximize overlay vs cluster-menu stacking, and when tools go flat. */

export type ChartDrawToolsLayout = 'cluster' | 'flat';

/**
 * `.chart-portal-host--maximized` is `position: fixed; inset: 0; z-index: 10000`.
 * A body-portaled menu below that number opens behind the overlay.
 */
export const CHART_PORTAL_MAXIMIZE_Z_INDEX = 10000;

/**
 * Cluster menu stacking. Must beat the maximize host (10000) and sit with
 * the chart context menu band (10050).
 */
export const CHART_DRAW_TOOLS_MENU_Z_INDEX = 10060;

/** Maximized / fullscreen toolbars have room -- show every line tool. */
export function chartDrawToolsLayout(maximized: boolean): ChartDrawToolsLayout {
  return maximized ? 'flat' : 'cluster';
}

/**
 * Cluster menus must render inside the visible overlay:
 * Fullscreen API hides anything outside `document.fullscreenElement`,
 * and the quote-panel maximize host is a `z-index: 10000` layer.
 */
export function chartDrawToolsMenuPortalTarget(): HTMLElement {
  const fullscreen = document.fullscreenElement;
  if (fullscreen instanceof HTMLElement) return fullscreen;
  const maximizedHost = document.querySelector('.chart-portal-host--maximized');
  if (maximizedHost instanceof HTMLElement) return maximizedHost;
  return document.body;
}
