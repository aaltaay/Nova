/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import { readCollapsed, readSurface } from './stockViewDockPersist';
import {
  parseDockRequest,
  requestStockViewDock,
  STOCK_VIEW_DOCK_REQUEST_EVENT,
} from './requestDockSurface';

describe('parseDockRequest / requestStockViewDock', () => {
  afterEach(() => {
    localStorage.clear();
  });

  it('accepts positions and rejects junk', () => {
    expect(parseDockRequest({ surface: 'positions' })).toEqual({
      surface: 'positions',
    });
    expect(parseDockRequest({ surface: 'chart' })).toBeNull();
    expect(parseDockRequest(null)).toBeNull();
  });

  it('writes persist keys and dispatches the dock event', () => {
    const seen: unknown[] = [];
    const onReq = (e: Event) => {
      seen.push((e as CustomEvent).detail);
    };
    window.addEventListener(STOCK_VIEW_DOCK_REQUEST_EVENT, onReq);
    requestStockViewDock({ surface: 'positions' });
    window.removeEventListener(STOCK_VIEW_DOCK_REQUEST_EVENT, onReq);
    expect(seen).toEqual([{ surface: 'positions' }]);
    expect(readSurface()).toBe('positions');
    expect(readCollapsed()).toBe(false);
  });
});
