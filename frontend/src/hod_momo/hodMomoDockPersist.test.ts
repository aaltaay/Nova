/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import {
  HOD_MOMO_DOCK_COLLAPSED_KEY,
  HOD_MOMO_DOCK_DEFAULT_COLLAPSED,
  HOD_MOMO_DOCK_DEFAULT_HEIGHT_PX,
  HOD_MOMO_DOCK_HEIGHT_KEY,
  HOD_MOMO_DOCK_MAX_HEIGHT_PX,
  HOD_MOMO_DOCK_MIN_HEIGHT_PX,
} from '../constants';
import {
  clampDockHeightPx,
  readDockCollapsed,
  readDockHeightPx,
  writeDockCollapsed,
  writeDockHeightPx,
} from './hodMomoDockPersist';

afterEach(() => {
  localStorage.removeItem(HOD_MOMO_DOCK_COLLAPSED_KEY);
  localStorage.removeItem(HOD_MOMO_DOCK_HEIGHT_KEY);
});

describe('hodMomoDockPersist', () => {
  it('defaults collapsed and height when unset', () => {
    expect(readDockCollapsed()).toBe(HOD_MOMO_DOCK_DEFAULT_COLLAPSED);
    expect(readDockHeightPx()).toBe(HOD_MOMO_DOCK_DEFAULT_HEIGHT_PX);
  });

  it('round-trips collapsed', () => {
    writeDockCollapsed(false);
    expect(readDockCollapsed()).toBe(false);
    writeDockCollapsed(true);
    expect(readDockCollapsed()).toBe(true);
  });

  it('clamps height on read/write', () => {
    expect(clampDockHeightPx(1)).toBe(HOD_MOMO_DOCK_MIN_HEIGHT_PX);
    expect(clampDockHeightPx(99999)).toBe(HOD_MOMO_DOCK_MAX_HEIGHT_PX);
    writeDockHeightPx(1);
    expect(readDockHeightPx()).toBe(HOD_MOMO_DOCK_MIN_HEIGHT_PX);
    writeDockHeightPx(99999);
    expect(readDockHeightPx()).toBe(HOD_MOMO_DOCK_MAX_HEIGHT_PX);
  });
});
