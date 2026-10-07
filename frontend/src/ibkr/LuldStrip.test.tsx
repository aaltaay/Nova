/**
 * @vitest-environment jsdom
 *
 * The LULD bands on Level 2 (ADR 047): the strip above the book and the two band rows in it, the lower
 * with the bids and the upper with the asks, each where its price sits -- past the rows when the band is
 * deeper than the ladder reaches, as it usually is.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MontageSide } from './DepthLadder';
import { bookPeak } from './dasDepthTiers';
import { luldMarkers, type LuldView } from './luld';
import { LuldStrip } from './LuldStrip';
import type { DepthLevel } from './types';

const NOW = 1_790_088_000;

function lvl(price: number, size: number, side: 'bid' | 'ask'): DepthLevel {
  return { price, size, side, mm: 'NSDQ' };
}

function view(patch: Partial<LuldView> = {}): LuldView {
  return {
    schema_version: 1, symbol: 'SLRX', source: 'live', state: 'bands', exact: true,
    lower: 4.4, upper: 6.6, reference: 5.5, reference_since: NOW - 60, reference_source: 'mean',
    reference_words: 'the 5-minute average of trades', percent: '20%', prev_close: 1.52, tier: null,
    tier_text: 'at or under $3.00 both tiers share one band', tier_sure: true, spread: null, limit: null,
    straddle: null, anchor: { kind: 'open', ts: NOW - 900, price: 4.9 }, halted_since: null,
    watching_since: NOW - 3600, warm_until: null, gap: null, last: 5.71,
    distance: { down_pct: -0.2294, up_pct: 0.1559 }, near: null, reason: null, history: [],
    note: "Nova's calculation", rules: 'rules', track: null, as_of: NOW, text: 'LULD 4.40 - 6.60', watching: true,
    ...patch,
  };
}

describe('the LULD strip and band rows', () => {
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

  it('draws each band over its column', () => {
    act(() => root.render(<LuldStrip view={view()} nowMs={NOW * 1000} />));
    const strip = container.querySelector<HTMLElement>('[data-testid="l2-luld"]')!;
    expect(strip.dataset.state).toBe('bands');
    expect(container.querySelector('[data-testid="l2-luld-bid"]')!.textContent).toBe('LULD▼ 4.40−22.9%');
    expect(container.querySelector('[data-testid="l2-luld-ask"]')!.textContent).toBe('▲ 6.60+15.6%');
    expect(strip.getAttribute('data-tip')).toContain("Nova's calculation");
  });

  it('turns red and counts down in a limit state', () => {
    const limit = { side: 'up' as const, since: NOW - 4, band: 6.6, pause_at: NOW + 11, overdue: false };
    act(() => root.render(<LuldStrip view={view({ state: 'limit', limit })} nowMs={NOW * 1000} />));
    const strip = container.querySelector<HTMLElement>('[data-testid="l2-luld"]')!;
    expect(strip.className).toContain('das-l2-luld--limit');
    expect(strip.textContent).toBe('LIMIT UP 6.60 · PAUSE IN 11s');
    expect(container.querySelector<HTMLElement>('.das-l2-luld__countdown')!.style.width).toBe('73%');
  });

  it('takes no room outside the bands\' hours', () => {
    act(() => root.render(<LuldStrip view={view({ state: 'off' })} nowMs={NOW * 1000} />));
    expect(container.innerHTML).toBe('');
  });

  it("draws each band as a row of its own at its price, as DAS does, and keeps a short book's height", () => {
    const bids = [lvl(5.71, 1, 'bid'), lvl(5.67, 1, 'bid'), lvl(5.05, 20, 'bid')];
    const asks = [lvl(5.8, 1, 'ask'), lvl(5.98, 1, 'ask'), lvl(6.62, 1, 'ask')];
    const m = luldMarkers(view());
    act(() => root.render(
      <div className="das-l2-montage">
        <MontageSide side="bid" levels={bids} peak={bookPeak(bids, asks)} markers={m.bid} />
        <MontageSide side="ask" levels={asks} peak={bookPeak(bids, asks)} markers={m.ask} />
      </div>,
    ));
    const column = (side: 'bid' | 'ask') => [...container.querySelectorAll<HTMLElement>(`.das-l2-side--${side} > .das-l2-row`)];
    const prices = (side: 'bid' | 'ask') => column(side).map(r => r.querySelector('.das-l2-price')?.textContent ?? '');
    // 4.40 is deeper than every bid shown: its row follows the last one.
    expect(prices('bid').slice(0, 4)).toEqual(['5.71', '5.67', '5.05', '4.40']);
    // 6.60 sorts between the asks at 5.98 and 6.62.
    expect(prices('ask').slice(0, 4)).toEqual(['5.80', '5.98', '6.60', '6.62']);
    // Each band row took an empty padding row's place: ten rows a side, as before.
    expect(column('bid')).toHaveLength(10);
    expect(column('ask')).toHaveLength(10);
    const lower = container.querySelector<HTMLElement>('[data-testid="l2-marker-luld-lower"]')!;
    expect(lower.className).toContain('das-l2-row--luld');
    expect(lower.textContent).toBe('LULD4.40');
    expect(lower.getAttribute('data-tip')).toContain("Nova's calculation");
  });

  it('lights the band row the price is on', () => {
    const asks = [lvl(6.6, 300, 'ask'), lvl(6.61, 100, 'ask')];
    const bids = [lvl(6.6, 7400, 'bid'), lvl(6.59, 100, 'bid')];
    const limit = { side: 'up' as const, since: NOW - 4, band: 6.6, pause_at: NOW + 11, overdue: false };
    const m = luldMarkers(view({ state: 'limit', limit }));
    act(() => root.render(<MontageSide side="ask" levels={asks} peak={bookPeak(bids, asks)} markers={m.ask} />));
    const upper = container.querySelector<HTMLElement>('[data-testid="l2-marker-luld-upper"]')!;
    expect(upper.className).toContain('das-l2-row--luld-hot');
  });
});
