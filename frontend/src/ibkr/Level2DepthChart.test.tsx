/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { L2_DEPTH_CHART_HINT, L2_DEPTH_CHART_STORAGE_KEY } from '../constants';
import { PREFS_BUNDLE_KEYS } from '../settings/prefsBundle';
import { applyBookWatchFrame } from './bookWatch';
import { Level2DepthChart, depthReadout } from './Level2DepthChart';
import { Level2Frame } from './Level2Frame';
import {
  depthDollars, depthSteps, readLevel2DepthChart, reloadLevel2DepthChartForTesting, setLevel2DepthChart,
} from './level2DepthSwitch';
import type { DepthLevel } from './types';

const row = (side: 'bid' | 'ask', price: number, size: number, mm = 'NSDQ'): DepthLevel => ({ side, price, size, mm });
const BIDS = [row('bid', 4.46, 500), row('bid', 4.45, 600), row('bid', 4.44, 700)];
const ASKS = [row('ask', 4.47, 600), row('ask', 4.48, 500), row('ask', 4.5, 12_000), row('ask', 4.5, 6_000, 'ARCA')];

beforeEach(() => {
  localStorage.clear();
  reloadLevel2DepthChartForTesting();
});
afterEach(cleanup);

function mount(watch: Parameters<typeof Level2DepthChart>[0]['watch'] = null) {
  return render(
    <Level2Frame data-testid="frame">
      <Level2DepthChart bids={BIDS} asks={ASKS} watch={watch} />
    </Level2Frame>,
  );
}

describe('the sums the depth chart draws', () => {
  it('is one step per price, summed outward from the inside, in shares and dollars', () => {
    expect(depthSteps(ASKS)).toEqual([
      { price: 4.47, size: 600, shares: 600, dollars: 600 * 4.47 },
      { price: 4.48, size: 500, shares: 1_100, dollars: 600 * 4.47 + 500 * 4.48 },
      { price: 4.5, size: 18_000, shares: 19_100, dollars: 600 * 4.47 + 500 * 4.48 + 18_000 * 4.5 },
    ]);
  });

  it('skips an empty row and a price that is not a number', () => {
    expect(depthSteps([row('bid', 4.46, 0), row('bid', Number.NaN, 500)])).toEqual([]);
  });

  it('writes dollars in three figures', () => {
    expect([depthDollars(940.4), depthDollars(53_216), depthDollars(1_079_000)]).toEqual(['$940', '$53.2K', '$1.08M']);
  });

  it('says what rests between the inside and a price', () => {
    expect(depthReadout('ask', depthSteps(ASKS)[2])).toBe('19,100 · $85.9K offered up to 4.50 (18,000 at that price)');
    expect(depthReadout('bid', depthSteps(BIDS)[1])).toBe('1,100 · $4.9K bid down to 4.45 (600 at that price)');
  });
});

describe('the depth chart over the book', () => {
  it('is off until the operator turns it on', () => {
    expect(readLevel2DepthChart()).toBe(false);
    expect(mount().queryByTestId('l2-depth-chart')).toBeNull();
  });

  it('turns on from the right-click menu, stays on, and turns off there', () => {
    const { getByTestId, queryByTestId } = mount();
    fireEvent.contextMenu(getByTestId('frame'), { clientX: 40, clientY: 40 });
    const on = getByTestId('l2-depth-chart-switch');
    expect(on.getAttribute('aria-checked')).toBe('false');
    fireEvent.click(on);
    expect(queryByTestId('l2-size-menu')).toBeNull();
    expect(getByTestId('l2-depth-chart')).toBeTruthy();
    expect(JSON.parse(localStorage.getItem(L2_DEPTH_CHART_STORAGE_KEY) ?? '{}').value).toBe(true);
    act(() => reloadLevel2DepthChartForTesting());
    expect(readLevel2DepthChart()).toBe(true);

    fireEvent.contextMenu(getByTestId('frame'), { clientX: 40, clientY: 40 });
    expect(getByTestId('l2-depth-chart-switch').getAttribute('aria-checked')).toBe('true');
    fireEvent.click(getByTestId('l2-depth-chart-switch'));
    expect(queryByTestId('l2-depth-chart')).toBeNull();
  });

  it('travels with the exported desk preferences', () => {
    expect(PREFS_BUNDLE_KEYS).toContain(L2_DEPTH_CHART_STORAGE_KEY);
  });

  it('shows each side\'s shares and dollars at its far edge', () => {
    act(() => setLevel2DepthChart(true));
    const { getByTestId } = mount();
    expect(getByTestId('l2-depth-total-bid').textContent).toBe('1,800$8.0Kbid');
    expect(getByTestId('l2-depth-total-ask').textContent).toBe('19,100$85.9Koffered');
    expect(getByTestId('l2-depth-read').textContent).toBe(L2_DEPTH_CHART_HINT);
  });

  it('reads out the price under the pointer, and the hint again when it leaves', () => {
    act(() => setLevel2DepthChart(true));
    const { getByTestId } = mount();
    const plot = getByTestId('l2-depth-chart').querySelector('.l2-depth__plot') as HTMLElement;
    plot.getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 60, right: 400, bottom: 60, x: 0, y: 0, toJSON: () => ({}) });
    fireEvent.mouseMove(plot, { clientX: 390 });
    expect(getByTestId('l2-depth-read').textContent).toBe('19,100 · $85.9K offered up to 4.50 (18,000 at that price)');
    fireEvent.mouseMove(plot, { clientX: 190 });
    expect(getByTestId('l2-depth-read').textContent).toBe('500 · $2.2K bid down to 4.46 (500 at that price)');
    fireEvent.mouseLeave(plot);
    expect(getByTestId('l2-depth-read').textContent).toBe(L2_DEPTH_CHART_HINT);
  });

  it('marks a big seller the watcher is following on its step, and none that ended', () => {
    act(() => setLevel2DepthChart(true));
    const wall = (over: Record<string, unknown>) => ({
      id: '1-XYZ-ask-4.5', kind: 'big_seller', side: 'ask', price: 4.5, state: 'holding', size_first: 18_000,
      size_now: 18_000, size_peak: 18_000, traded: 0, median_level: 550, multiple: 32.7, first_seen_ts: 80,
      seen_from_start: false, called_ts: 83, ended_ts: null, held_sec: 20, distance: 0.03, distance_pct: 0.67,
      distance_called: 0.03, on_approach: null, back: null, clear_sec: null, how: null, left: null, ...over,
    });
    const watch = (big: unknown[]) => applyBookWatchFrame(null, {
      schema_version: 1, now: 100, reset: true, seq: 0, watching: true, reason: null, window_sec: 60,
      sides: null, drops: [], hidden: [], big,
    }, 7_000_000);
    const held = mount(watch([wall({})]));
    expect(held.getByTestId('l2-depth-wall').textContent).toBe('Seller 4.50 · 18.0K');
    cleanup();
    expect(mount(watch([wall({ state: 'pulled', ended_ts: 99 })])).queryByTestId('l2-depth-wall')).toBeNull();
  });

  it('draws nothing for an empty book', () => {
    act(() => setLevel2DepthChart(true));
    const { queryByTestId } = render(<Level2Frame><Level2DepthChart bids={[]} asks={[]} /></Level2Frame>);
    expect(queryByTestId('l2-depth-chart')).toBeNull();
  });
});
