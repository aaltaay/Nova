/**
 * Level 2's short chips (ADR 048): SSR off / on with its trigger / not known, the halt cool-off while it runs,
 * and LIQ for the position held -- nothing on a replay desk.
 *
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ShortChips } from './ShortChips';

const ctx = vi.hoisted(() => ({ value: null as unknown }));
const facts = vi.hoisted(() => ({ value: { check: null, unavailable: false, error: null, loading: false } as unknown }));

vi.mock('./StockReadContext', () => ({ useStockReadContext: () => ctx.value }));
vi.mock('../ibkr', async (orig) => ({
  ...(await orig<typeof import('../ibkr')>()),
  useShortFacts: () => facts.value,
}));

function check(ssr: Record<string, unknown>, halt: Record<string, unknown> = { state: 'clear', text: '', until: null }) {
  return {
    check: {
      symbol: 'FADE', venue: 'paper', ok: true, first: null, rules: [], bid: 4.9, ask: 4.91, borrowShares: 30000,
      ssr: { effective_on: ssr.state !== 'off', text: 'SSR text.', trigger: null, prior_close: 5.6, ...ssr },
      halt,
    },
    unavailable: false, error: null, loading: false,
  };
}

describe('ShortChips (ADR 048)', () => {
  let root: Root;
  let mount: HTMLDivElement;

  beforeEach(() => {
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
    ctx.value = { symbol: 'FADE', active: true, replay: false, position: null };
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
  });

  const render = () => act(() => root.render(<ShortChips />));
  const text = (id: string) => mount.querySelector(`[data-testid="${id}"]`)?.textContent ?? null;

  it('says SSR on with its trigger, off, or not known', () => {
    facts.value = check({ state: 'on', trigger: 5.04 });
    render();
    expect(text('short-chip-ssr')).toBe('SSR on · 5.04');
    facts.value = check({ state: 'off' });
    render();
    expect(text('short-chip-ssr')).toBe('SSR off');
    facts.value = check({ state: 'unknown' });
    render();
    expect(text('short-chip-ssr')).toBe('SSR ?');
  });

  it('shows the cool-off only while it runs', () => {
    facts.value = check({ state: 'off' }, { state: 'cooloff', text: 'Up-halt resumed 10:32.', until: Date.UTC(2026, 9, 7, 14, 42) / 1000 });
    render();
    expect(text('short-chip-cooloff')).toBe('COOL-OFF · 10:42');
    facts.value = check({ state: 'off' });
    render();
    expect(text('short-chip-cooloff')).toBeNull();
  });

  it('shows LIQ for the position held, and nothing on a replay desk', () => {
    facts.value = check({ state: 'off' });
    ctx.value = { symbol: 'FADE', active: true, replay: false, position: { qty: -416, avgCost: 5.77, liquidationPrice: 13.08 } };
    render();
    expect(text('short-chip-liq')).toBe('LIQ 13.08');
    ctx.value = { symbol: 'FADE', active: true, replay: true, position: null };
    render();
    expect(mount.textContent).toBe('');
  });
});
