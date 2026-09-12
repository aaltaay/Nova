/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  consumeEscapeForFullscreen,
  exitChartFullscreen,
  fullscreenElement,
  getChartFullscreenActive,
  isChartFullscreen,
  markChartFullscreen,
  requestChartFullscreen,
  shouldRestoreGridOnEscape,
  takeEscapeConsumedForFullscreen,
  toggleChartFullscreen,
} from './chartFullscreen';

let current: Element | null = null;

function installFullscreenMock() {
  current = null;
  markChartFullscreen(false);
  takeEscapeConsumedForFullscreen();
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    get: () => current,
  });
  HTMLElement.prototype.requestFullscreen = vi.fn(function (this: HTMLElement) {
    current = this;
    document.dispatchEvent(new Event('fullscreenchange'));
    return Promise.resolve();
  });
  document.exitFullscreen = vi.fn(() => {
    current = null;
    document.dispatchEvent(new Event('fullscreenchange'));
    return Promise.resolve();
  });
}

describe('chartFullscreen', () => {
  beforeEach(installFullscreenMock);

  afterEach(() => {
    current = null;
    markChartFullscreen(false);
    takeEscapeConsumedForFullscreen();
    vi.restoreAllMocks();
  });

  it('request / exit toggle the Fullscreen API on the chart host', async () => {
    const host = document.createElement('div');
    await requestChartFullscreen(host);
    expect(host.requestFullscreen).toHaveBeenCalledTimes(1);
    expect(fullscreenElement()).toBe(host);
    expect(isChartFullscreen(host)).toBe(true);
    expect(getChartFullscreenActive()).toBe(true);

    await exitChartFullscreen();
    expect(document.exitFullscreen).toHaveBeenCalledTimes(1);
    expect(fullscreenElement()).toBeNull();
    expect(isChartFullscreen(host)).toBe(false);
  });

  it('toggle enters then leaves without touching a second element', async () => {
    const host = document.createElement('div');
    await toggleChartFullscreen(host);
    expect(fullscreenElement()).toBe(host);
    await toggleChartFullscreen(host);
    expect(fullscreenElement()).toBeNull();
  });

  it('Esc while fullscreen is consumed so grid maximize stays', () => {
    markChartFullscreen(true);
    expect(consumeEscapeForFullscreen()).toBe(true);
    expect(shouldRestoreGridOnEscape({ key: 'Escape' }, null)).toBe(false);
    expect(takeEscapeConsumedForFullscreen()).toBe(false);
  });

  it('Esc restores the grid only when fullscreen is not active', () => {
    markChartFullscreen(false);
    expect(shouldRestoreGridOnEscape({ key: 'Escape' }, null)).toBe(true);
    expect(shouldRestoreGridOnEscape({ key: 'Escape' }, 'TrendLine')).toBe(false);
    expect(shouldRestoreGridOnEscape({ key: 'Enter' }, null)).toBe(false);
  });
});
