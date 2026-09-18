/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TAPE_UI_MAX_ROWS } from '../constants';
import { TimeSalesPanel } from './TimeSalesPanel';
import type { TapePrint } from './tapeFeed';

function makePrints(n: number): TapePrint[] {
  return Array.from({ length: n }, (_, i) => ({
    symbol: 'AAPL',
    time: `2026-09-18T13:00:${String(59 - (i % 60)).padStart(2, '0')}.000Z`,
    price: n - i,
    size: 100,
    exchange: 'ISLAND',
    side: 'ask' as const,
  }));
}

const prints = makePrints(TAPE_UI_MAX_ROWS);

vi.mock('./useIbkrTape', () => ({
  useIbkrTape: () => ({
    prints,
    connected: true,
    error: null,
  }),
}));

describe('TimeSalesPanel virtual window', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('keeps the full ring but mounts only a viewport window of rows', () => {
    act(() => {
      root.render(<TimeSalesPanel symbol="AAPL" />);
    });
    const rows = container.querySelector('[data-testid="ts-panel-rows"]');
    expect(rows?.getAttribute('data-ring-count')).toBe(String(TAPE_UI_MAX_ROWS));
    const rendered = Number(rows?.getAttribute('data-rendered-count'));
    expect(rendered).toBeGreaterThan(0);
    expect(rendered).toBeLessThan(TAPE_UI_MAX_ROWS);
    expect(container.querySelectorAll('.ts-row')).toHaveLength(rendered);
  });
});
