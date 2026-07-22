/**
 * localStorage helpers for Stock View Positions / Orders / Nova OS dock.
 */
import {
  ORDERS_TODAY_FILTER_DEFAULT,
  ORDERS_TODAY_FILTER_STORAGE_KEY,
  STOCK_VIEW_DOCK_SURFACE_DEFAULT,
  STOCK_VIEW_DOCK_SURFACE_KEY,
  STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
  STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED,
  STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY,
  STOCK_VIEW_ORDERS_TAB_KEY,
  type OrdersTodayFilterId,
  type StockViewDockSurface,
} from '../constants';

export function readCollapsed(): boolean {
  try {
    const raw = localStorage.getItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY);
    if (raw === '1') return true;
    if (raw === '0') return false;
  } catch {
    /* private mode */
  }
  return STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED;
}

export function writeCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(
      STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
      collapsed ? '1' : '0',
    );
  } catch {
    /* ignore */
  }
}

export function readSampleHidden(): boolean {
  try {
    return localStorage.getItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY) === '1';
  } catch {
    return false;
  }
}

function migrateLegacyTab(raw: string | null): OrdersTodayFilterId | null {
  if (raw === 'open') return 'working';
  if (raw === 'closed') return 'all';
  return null;
}

export function readFilter(): OrdersTodayFilterId {
  try {
    const raw = localStorage.getItem(ORDERS_TODAY_FILTER_STORAGE_KEY);
    if (
      raw === 'working' ||
      raw === 'filled' ||
      raw === 'canceled' ||
      raw === 'partial_filled' ||
      raw === 'all'
    ) {
      return raw;
    }
    const legacy = migrateLegacyTab(localStorage.getItem(STOCK_VIEW_ORDERS_TAB_KEY));
    if (legacy) return legacy;
  } catch {
    /* ignore */
  }
  return ORDERS_TODAY_FILTER_DEFAULT;
}

export function writeFilter(filter: OrdersTodayFilterId): void {
  try {
    localStorage.setItem(ORDERS_TODAY_FILTER_STORAGE_KEY, filter);
  } catch {
    /* ignore */
  }
}

export function readSurface(): StockViewDockSurface {
  try {
    const raw = localStorage.getItem(STOCK_VIEW_DOCK_SURFACE_KEY);
    if (raw === 'positions' || raw === 'orders' || raw === 'nova_os') return raw;
  } catch {
    /* ignore */
  }
  return STOCK_VIEW_DOCK_SURFACE_DEFAULT;
}

export function writeSurface(surface: StockViewDockSurface): void {
  try {
    localStorage.setItem(STOCK_VIEW_DOCK_SURFACE_KEY, surface);
  } catch {
    /* ignore */
  }
}
