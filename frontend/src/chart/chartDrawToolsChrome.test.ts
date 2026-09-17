/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it } from 'vitest';
import {
  CHART_DRAW_TOOLS_MENU_Z_INDEX,
  CHART_PORTAL_MAXIMIZE_Z_INDEX,
  chartDrawToolsLayout,
  chartDrawToolsMenuPortalTarget,
} from './chartDrawToolsChrome';

describe('chartDrawToolsChrome', () => {
  afterEach(() => {
    document.querySelector('.chart-portal-host--maximized')?.remove();
  });

  it('flattens tools only when the chart chrome is maximized', () => {
    expect(chartDrawToolsLayout(false)).toBe('cluster');
    expect(chartDrawToolsLayout(true)).toBe('flat');
  });

  it('keeps the cluster menu above the maximize overlay', () => {
    expect(CHART_DRAW_TOOLS_MENU_Z_INDEX).toBeGreaterThan(CHART_PORTAL_MAXIMIZE_Z_INDEX);
  });

  it('portals to body when the chart is not maximized or fullscreen', () => {
    expect(chartDrawToolsMenuPortalTarget()).toBe(document.body);
  });

  it('portals into the maximized host so the overlay cannot bury the menu', () => {
    const host = document.createElement('div');
    host.className = 'chart-portal-host chart-portal-host--maximized';
    document.body.appendChild(host);
    expect(chartDrawToolsMenuPortalTarget()).toBe(host);
  });

  it('prefers the fullscreen element over body (Fullscreen API hides outsiders)', () => {
    const fs = document.createElement('div');
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fs,
    });
    expect(chartDrawToolsMenuPortalTarget()).toBe(fs);
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => null,
    });
  });
});
