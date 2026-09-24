/**
 * @vitest-environment jsdom
 *
 * #543: a print that does not set a price -- IBKR flags it unreported, or its
 * sale conditions report it for volume only -- is a dimmed row that says why.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { TAPE_NO_PRICE_TITLE, TAPE_UNREPORTED_TITLE } from '../constants';
import { TimeSalesView } from './TimeSalesView';
import type { TapePrint } from './tapeFeed';

const base = { symbol: 'PLTR', exchange: 'FINRA', side: 'unknown' as const };

// Newest first, as the feed ring holds them.
const PRINTS: TapePrint[] = [
  { ...base, time: '2026-09-23T13:45:04.000Z', price: 192.8, size: 100, conditions: '', setsPrice: true },
  { ...base, time: '2026-09-23T13:45:03.000Z', price: 190.37, size: 1, conditions: '   I', setsPrice: false },
  {
    ...base, time: '2026-09-23T13:45:02.000Z', price: 190.38, size: 100, conditions: ' 4 W',
    unreported: true, setsPrice: false,
  },
  // No verdict at all (an older backend): a price, as before.
  { ...base, time: '2026-09-23T13:45:01.000Z', price: 192.75, size: 200 },
];

describe('Time & Sales dims prints that do not set a price', () => {
  let container: HTMLDivElement;
  let root: Root;

  function render(prints: TapePrint[]) {
    act(() => {
      root.render(<TimeSalesView symbol="PLTR" feed={{ prints, connected: true, error: null }} />);
    });
    return [...container.querySelectorAll<HTMLElement>('.ts-row')];
  }

  beforeEach(() => {
    localStorage.clear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    localStorage.clear();
  });

  it('dims an unreported print and a volume-only one, each with its reason', () => {
    const rows = render(PRINTS);
    expect(rows.map(r => r.classList.contains('ts-row--no-price'))).toEqual([false, true, true, false]);
    expect(rows.map(r => r.classList.contains('ts-row--unreported'))).toEqual([false, false, true, false]);
    expect(rows.map(r => r.getAttribute('data-sets-price'))).toEqual([null, '0', '0', null]);
    expect(rows.map(r => r.getAttribute('title'))).toEqual([
      null, TAPE_NO_PRICE_TITLE, TAPE_UNREPORTED_TITLE, null,
    ]);
  });

  it('re-renders a replayed row whose verdict changed', () => {
    const replayed = { ...PRINTS[0], replayId: 'job:1' };
    expect(render([replayed])[0].classList.contains('ts-row--no-price')).toBe(false);
    const rows = render([{ ...replayed, setsPrice: false }]);
    expect(rows[0].classList.contains('ts-row--no-price')).toBe(true);
    expect(rows[0].getAttribute('title')).toBe(TAPE_NO_PRICE_TITLE);
  });
});
