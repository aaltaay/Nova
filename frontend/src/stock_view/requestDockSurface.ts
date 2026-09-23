/**
 * Ask the shared Positions / Orders dock to switch surface.
 * Latch writes persist keys first so a remount still lands on the request.
 */
import type { OrdersTodayFilterId, StockViewDockSurface } from '../constants';
import { writeCollapsed, writeFilter, writeSurface } from './stockViewDockPersist';

export const STOCK_VIEW_DOCK_REQUEST_EVENT = 'nova:stock-view-dock';

export interface StockViewDockRequest {
  surface: StockViewDockSurface;
  filter?: OrdersTodayFilterId;
}

export function parseDockRequest(detail: unknown): StockViewDockRequest | null {
  if (!detail || typeof detail !== 'object') return null;
  const surface = (detail as StockViewDockRequest).surface;
  if (surface !== 'positions' && surface !== 'orders') {
    return null;
  }
  const filter = (detail as StockViewDockRequest).filter;
  if (
    filter != null &&
    filter !== 'working' &&
    filter !== 'filled' &&
    filter !== 'canceled' &&
    filter !== 'partial_filled' &&
    filter !== 'all'
  ) {
    return null;
  }
  return filter ? { surface, filter } : { surface };
}

export function requestStockViewDock(req: StockViewDockRequest): void {
  const parsed = parseDockRequest(req);
  if (!parsed) return;
  writeSurface(parsed.surface);
  writeCollapsed(false);
  if (parsed.filter) writeFilter(parsed.filter);
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(STOCK_VIEW_DOCK_REQUEST_EVENT, { detail: parsed }),
  );
}
