/**
 * @vitest-environment jsdom
 *
 * Level 2 size gauge (operator pick, 2026-09-24): a dark bar along each row's
 * bottom edge on one scale for the whole book. The row keeps its tier colour --
 * the white wash it replaced turned the biggest level into a paler, different
 * looking tier, and scaled each side to its own biggest order.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { L2_DAS_SIZE_BAR } from '../constants';
import { MontageSide } from './DepthLadder';
import type { DepthMarker } from './depthMarkers';
import { bookPeak } from './dasDepthTiers';
import type { DepthLevel } from './types';

function lvl(price: number, size: number, side: 'bid' | 'ask'): DepthLevel {
  return { price, size, side, mm: 'NSDQ' };
}

const BIDS = [lvl(4.84, 100, 'bid'), lvl(4.78, 3001, 'bid')];
const ASKS = [lvl(4.92, 100, 'ask'), lvl(5.18, 722, 'ask')];

describe('MontageSide size gauge', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    const peak = bookPeak(BIDS, ASKS);
    act(() => {
      root.render(
        <div className="das-l2-montage">
          <MontageSide side="bid" levels={BIDS} peak={peak} />
          <MontageSide side="ask" levels={ASKS} peak={peak} />
        </div>,
      );
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  const gauges = (side: 'bid' | 'ask') =>
    [...container.querySelectorAll<HTMLElement>(`.das-l2-side--${side} .das-l2-gauge`)];

  it('draws both sides on one scale', () => {
    expect(gauges('bid').map(g => g.style.width)).toEqual(['3.3%', '100%']);
    expect(gauges('ask').map(g => g.style.width)).toEqual(['3.3%', '24.1%']);
  });

  it('uses the dark gauge colour and keeps the row its tier colour', () => {
    const rows = [...container.querySelectorAll<HTMLElement>('.das-l2-row--tiered')];
    expect(rows).toHaveLength(4);
    for (const row of rows) {
      expect(row.style.backgroundImage).toBe('');
      expect(row.style.backgroundColor).not.toBe('');
      expect(row.querySelector<HTMLElement>('.das-l2-gauge')?.style.backgroundColor)
        .toBe(L2_DAS_SIZE_BAR.replace(/\s+/g, ' '));
    }
  });

  it('puts no gauge on a padded empty row', () => {
    const empty = [...container.querySelectorAll('.das-l2-row--empty')];
    expect(empty.length).toBeGreaterThan(0);
    for (const row of empty) expect(row.querySelector('.das-l2-gauge')).toBeNull();
  });
});

describe('MontageSide plan markers (ADR 037)', () => {
  let container: HTMLDivElement;
  let root: Root;
  const asks = [4.25, 4.25, 4.30, 4.31, 4.34].map(p => lvl(p, 100, 'ask'));
  const marker = (id: string, price: number, working: boolean): DepthMarker => ({
    id, price, label: `${id.toUpperCase()} ${price}`, color: '#0a84ff', working, rests: 'ask', tip: `${id} tip`,
  });

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <MontageSide side="ask" levels={asks} peak={100}
          markers={[marker('entry', 4.27, false), marker('target', 4.52, true)]} />,
      );
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('draws each level over the boundary where it sits and never adds a row', () => {
    expect(container.querySelectorAll('.das-l2-row')).toHaveLength(10);
    const entry = container.querySelector<HTMLElement>('[data-testid="l2-marker-entry"]');
    // 4.27 sits after the two 4.25 asks: on the boundary above the 4.30 row, dashed while only a plan.
    expect(entry?.parentElement?.textContent).toContain('4.30');
    expect(entry?.className).toContain('das-l2-marker--edge');
    expect(entry?.className).toContain('das-l2-marker--plan');
    const target = container.querySelector<HTMLElement>('[data-testid="l2-marker-target"]');
    // Past the book shown: at the foot of the last ask shown, with an arrow, solid behind an order.
    expect(target?.parentElement?.textContent).toContain('4.34');
    expect(target?.className).toContain('das-l2-marker--end');
    expect(target?.className).toContain('das-l2-marker--working');
    expect(target?.textContent).toBe('TARGET 4.52 ↓');
  });
});
