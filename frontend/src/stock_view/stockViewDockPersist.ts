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
import { parseBoolFlag, readPref, writePref } from '../utils/prefStore';

export function readCollapsed(): boolean {
  return readPref(
    STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
    STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED,
    parseBoolFlag,
  );
}

export function writeCollapsed(collapsed: boolean): void {
  writePref(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY, collapsed);
}

export function readSampleHidden(): boolean {
  return readPref(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY, false, parseBoolFlag);
}

/** Persist Hide sample. Absent key means "no stored hide", not "show sample". */
export function writeSampleHidden(hidden: boolean): void {
  try {
    if (hidden) {
      localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY, '1');
    } else {
      localStorage.removeItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY);
    }
  } catch {
    /* ignore */
  }
}

/**
 * Working-order sample starts hidden unless global Sample mode is on.
 * A stored Hide still wins over Sample mode.
 */
export function initialSampleHidden(globalSampleActive: boolean): boolean {
  if (readSampleHidden()) return true;
  return !globalSampleActive;
}

function migrateLegacyTab(raw: string | null): OrdersTodayFilterId | null {
  if (raw === 'open') return 'working';
  if (raw === 'closed') return 'all';
  return null;
}

function parseFilter(raw: unknown): OrdersTodayFilterId | null {
  if (
    raw === 'working' ||
    raw === 'filled' ||
    raw === 'canceled' ||
    raw === 'partial_filled' ||
    raw === 'all'
  ) {
    return raw;
  }
  return null;
}

export function readFilter(): OrdersTodayFilterId {
  const stored = readPref(ORDERS_TODAY_FILTER_STORAGE_KEY, null, parseFilter);
  if (stored) return stored;
  try {
    const legacy = migrateLegacyTab(localStorage.getItem(STOCK_VIEW_ORDERS_TAB_KEY));
    if (legacy) return legacy;
  } catch {
    /* ignore */
  }
  return ORDERS_TODAY_FILTER_DEFAULT;
}

export function writeFilter(filter: OrdersTodayFilterId): void {
  writePref(ORDERS_TODAY_FILTER_STORAGE_KEY, filter);
}

function parseSurface(raw: unknown): StockViewDockSurface | null {
  if (raw === 'positions' || raw === 'orders' || raw === 'nova_os') return raw;
  return null;
}

export function readSurface(): StockViewDockSurface {
  return readPref(
    STOCK_VIEW_DOCK_SURFACE_KEY,
    STOCK_VIEW_DOCK_SURFACE_DEFAULT,
    parseSurface,
  );
}

export function writeSurface(surface: StockViewDockSurface): void {
  writePref(STOCK_VIEW_DOCK_SURFACE_KEY, surface);
}
