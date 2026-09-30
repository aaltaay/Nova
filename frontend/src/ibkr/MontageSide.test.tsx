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
import { applyBookWatchFrame } from './bookWatch';
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

describe('MontageSide: what left the book (ADR 033 amendment)', () => {
  let container: HTMLDivElement;
  let root: Root;
  const NOW_S = 1_790_682_311.878;
  const NOW_MS = 9_000_000;
  const drop = (seq: number, over: Record<string, unknown>) => ({
    seq, ts: NOW_S - 0.8, side: 'ask', price: 8.25, dropped: 2000, pulled: 2000, filled: 0, outcome: 'pulled',
    level_before: 2100, level_after: 100, distance_ticks: 0, distance_at_post_ticks: 5, lifetime_sec: 0.65,
    large_pull: true, on_approach: true, ...over,
  });
  const watch = applyBookWatchFrame(null, {
    schema_version: 1, now: NOW_S, reset: true, seq: 3, watching: true, reason: null, window_sec: 60,
    sides: { bid: { pulled_shares: 0, filled_shares: 0, large_pulls: 0 }, ask: { pulled_shares: 2000, filled_shares: 8200, large_pulls: 1 } },
    drops: [
      drop(1, { ts: NOW_S - 1.5, price: 8.19, pulled: 0, filled: 3000, outcome: 'traded', large_pull: false, on_approach: false }),
      drop(2, { ts: NOW_S - 0.95, price: 8.2, pulled: 0, filled: 5200, outcome: 'traded', large_pull: false, on_approach: false }),
      drop(3, {}),
    ],
  }, NOW_MS);
  const asks = [lvl(8.25, 100, 'ask'), lvl(8.25, 2000, 'ask'), lvl(8.26, 2000, 'ask'), lvl(8.28, 2000, 'ask')];

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<MontageSide side="ask" levels={asks} peak={2000} watch={watch} nowMs={NOW_MS} />);
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('marks what traded and what was pulled where the size was, adding no row', () => {
    expect(container.querySelectorAll('.das-l2-row')).toHaveLength(10);
    const traded = container.querySelector<HTMLElement>('[data-testid="l2-pullmark-traded"]');
    expect(traded?.textContent).toBe('✓ 8,200 traded');
    // Above the book: over the column head, never over the inside row.
    expect(traded?.closest('.das-l2-pullmarks')?.className).toContain('das-l2-pullmarks--head');
    expect(traded?.closest('.das-l2-row')).toBeNull();
    const pulled = container.querySelector<HTMLElement>('[data-testid="l2-pullmark-approach"]');
    expect(pulled?.textContent).toBe('✕ 2,000 pulled');
    // After the two 8.25 asks: on the boundary above the 8.26 row.
    expect(pulled?.closest('.das-l2-row')?.textContent).toContain('8.26');
    expect(pulled?.getAttribute('data-tip')).toContain('never a detection');
  });

  it('hatches every row at a price pulled in the last minute and draws nothing over its digits', () => {
    const hatched = [...container.querySelectorAll<HTMLElement>('.das-l2-row--pulled-here')];
    expect(hatched.map(r => r.textContent)).toEqual(['8.25100NSDQ', '8.252,000NSDQ']); // price, size, venue: no glyph
    expect(hatched[0].getAttribute('data-tip-title')).toBe('8.25: pulled here once in the last minute');
    expect(hatched[1].getAttribute('data-tip')).toContain('2,000 offered pulled');
  });
});

describe('MontageSide: a hidden seller (ADR 033 amendment, 2026-09-30)', () => {
  let container: HTMLDivElement;
  let root: Root;
  const NOW_S = 1_790_682_311.878;
  const NOW_MS = 9_000_000;
  const watch = applyBookWatchFrame(null, {
    schema_version: 1, now: NOW_S, reset: true, seq: 0, watching: true, reason: null, window_sec: 60,
    sides: {
      bid: { pulled_shares: 0, filled_shares: 0, large_pulls: 0, hidden_shares: 0 },
      ask: { pulled_shares: 0, filled_shares: 2000, large_pulls: 0, hidden_shares: 12_400 },
    },
    drops: [],
    hidden: [{
      seq: 1, id: '1-XYZ-ask-5', ts: NOW_S - 0.5, side: 'ask', price: 5, state: 'holding', hidden: 12_400,
      printed: 14_400, shown_max: 2000, refills: 7, started_ts: NOW_S - 9.5, last_print_ts: NOW_S - 0.5,
    }],
  }, NOW_MS);
  const asks = [lvl(5, 1200, 'ask'), lvl(5.01, 1500, 'ask'), lvl(5.01, 800, 'ask'), lvl(5.02, 4500, 'ask')];

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<MontageSide side="ask" levels={asks} peak={4500} watch={watch} nowMs={NOW_MS} />);
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('outlines the row it holds at and marks it underneath, adding no row', () => {
    expect(container.querySelectorAll('.das-l2-row')).toHaveLength(10);
    const outlined = [...container.querySelectorAll<HTMLElement>('.das-l2-row--hidden-here')];
    expect(outlined.map(r => r.textContent)).toEqual(['5.001,200NSDQ']);
    expect(outlined[0].getAttribute('data-tip-title')).toBe('Hidden seller at 5.00: 12,400 beyond what it showed');
    const mark = container.querySelector<HTMLElement>('[data-testid="l2-pullmark-hidden"]');
    expect(mark?.textContent).toBe('◆ 12.4K hidden');
    // On the boundary above the 5.01 rows: under the price it holds at.
    expect(mark?.closest('.das-l2-row')?.textContent).toContain('5.01');
    expect(mark?.closest('.das-l2-pullmarks')?.className).toContain('das-l2-pullmarks--hidden');
    expect(mark?.getAttribute('data-tip')).toContain('never a detection');
  });
});
