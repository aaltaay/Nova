/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SymbolInspector } from './HodMomoSymbolInspector';

describe('SymbolInspector (QA C10)', () => {
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
    vi.unstubAllGlobals();
  });

  async function inspect(symbol: string) {
    await act(async () => {
      root.render(<SymbolInspector />);
    });
    const input = container.querySelector('input') as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      setter.call(input, symbol);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => {
      (container.querySelector('.dbg-inspect-btn') as HTMLButtonElement).click();
    });
  }

  it('shows the backend 404 for BRK/B instead of crashing the Scanner view', async () => {
    const fetchMock = vi.fn(async () => new Response('{"detail":"Not Found"}', { status: 404 }));
    vi.stubGlobal('fetch', fetchMock);
    await inspect('BRK/B');
    expect(String(fetchMock.mock.calls[0][0])).toContain('/hod-momo/debug/symbol/BRK%2FB');
    expect(container.querySelector('.dbg-error')?.textContent).toBe('Inspector: Not Found (HTTP 404)');
    expect(container.querySelector('.dbg-inspector-result')).toBeNull();
  });

  it('renders a real snapshot with stated absences', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      symbol: 'GRML',
      snap: { price: 9.42, rvol: null, float_shares: null, gap_pct: null, change_pct: null, volume: null,
        fifty_two_week_high: null, last_enriched: 0 },
      session_high: null,
      decisions: [],
      would_fire_now: null,
    }), { status: 200 })));
    await inspect('GRML');
    const text = container.querySelector('.dbg-inspector-result')?.textContent ?? '';
    expect(text).toContain('$9.42');
    expect(text).not.toContain('—x');
    expect(text).not.toContain('—%');
    expect(text).toContain('never');
  });
});
