/**
 * @vitest-environment jsdom
 *
 * Two states, both explicit: a book the local recorder archived for this
 * playhead second, and a moment it never covered (#309). Nothing in between --
 * the panel must never present an empty ladder as if it were the market.
 */
import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { HistoricalDepth, HistoricalL2Chip } from './HistoricalDepth';
import type { HistoricalDepthBook } from './historicalTypes';

// 2026-09-18 08:41:16 UTC = 04:41:16 ET.
const RECORDED_TS = Date.UTC(2026, 8, 18, 8, 41, 16) / 1000;

function recorded(overrides: Partial<HistoricalDepthBook> = {}): HistoricalDepthBook {
  return {
    symbol: 'IMCC',
    bids: [
      { price: 1.88, size: 900, side: 'bid', mm: 'ISLAND' },
      { price: 1.87, size: 400, side: 'bid', mm: 'ARCA' },
    ],
    asks: [{ price: 1.9, size: 300, side: 'ask', mm: 'NSDQ' }],
    ts: RECORDED_TS,
    age_sec: 0.4,
    l1_fallback: false,
    session_id: 'IMCC:depth:abc123',
    source: 'l2_recorder',
    ...overrides,
  };
}

describe('replay Level 2', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function render(node: ReactNode) {
    await act(async () => {
      root.render(node);
    });
  }

  it('draws the recorded book in the live montage, stamped with when it was recorded', async () => {
    await render(<HistoricalDepth depth={recorded()} />);
    const ladder = container.querySelector('[data-testid="historical-l2"]')!;
    expect(ladder.getAttribute('data-depth-source')).toBe('l2_recorder');
    expect(container.querySelector('[data-testid="historical-l2-empty"]')).toBeNull();
    expect(container.querySelector('[data-testid="historical-l2-recorded"]')?.textContent)
      .toBe('Recorded book at 04:41:16 ET');
    const bids = [...ladder.querySelectorAll('.das-l2-side--bid .das-l2-row--tiered')];
    const asks = [...ladder.querySelectorAll('.das-l2-side--ask .das-l2-row--tiered')];
    expect(bids.map(row => row.querySelector('.das-l2-price')?.textContent)).toEqual(['1.88', '1.87']);
    expect(bids.map(row => row.querySelector('.das-l2-size')?.textContent)).toEqual(['900', '400']);
    expect(asks.map(row => row.querySelector('.das-l2-price')?.textContent)).toEqual(['1.90']);
    expect(asks[0].querySelector('.das-l2-mm')?.textContent).toBe('NSDQ');
  });

  it('says depth was not recorded rather than showing an empty market', async () => {
    await render(<HistoricalDepth depth={null} />);
    const ladder = container.querySelector('[data-testid="historical-l2"]')!;
    expect(ladder.getAttribute('data-depth-source')).toBe('none');
    expect(container.querySelector('[data-testid="historical-l2-recorded"]')).toBeNull();
    expect(container.querySelector('[data-testid="historical-l2-empty"]')?.textContent)
      .toBe('Level 2 was not recorded for this moment');
    // The frame stays -- same pane, same column headers, just no levels.
    expect(ladder.querySelectorAll('.das-l2-colhead')).toHaveLength(2);
    expect(ladder.querySelectorAll('.das-l2-row--tiered')).toHaveLength(0);
    // The rail hides .ibkr-depth-fallback-badge, so the note must not use it.
    expect(ladder.querySelector('.ibkr-depth-fallback-badge')).toBeNull();
  });

  it('renders nothing but the frame when a recorded session is missing the prop', async () => {
    await render(<HistoricalDepth />);
    expect(container.querySelector('[data-testid="historical-l2-empty"]')).toBeTruthy();
  });

  it('chip names which of the two states the operator is looking at', async () => {
    await render(<HistoricalL2Chip depth={null} />);
    const chip = () => container.querySelector('[data-testid="historical-l2-chip"]')!;
    expect(chip().textContent).toBe('ReplayNo L2 recorded');
    expect(chip().className).toContain('sv-shortability-chip--unknown');
    expect(chip().getAttribute('title')).toMatch(/trades only/);
    await render(<HistoricalL2Chip depth={recorded()} />);
    expect(chip().textContent).toBe('ReplayRecorded L2');
    expect(chip().className).toContain('sv-shortability-chip--ok');
    expect(chip().getAttribute('title')).toMatch(/recorded locally/);
  });
});
