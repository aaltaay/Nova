/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useIbkrDepth } from './useIbkrDepth';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  readyState = 0;
  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.readyState = 3;
    this.onclose?.({});
  }

  send() {}
}

type DepthState = ReturnType<typeof useIbkrDepth>;

function Harness({
  symbol,
  uiActive = true,
  onValue,
}: {
  symbol: string | null;
  uiActive?: boolean;
  onValue: (state: DepthState) => void;
}) {
  const state = useIbkrDepth(symbol, uiActive);
  onValue(state);
  return null;
}

describe('useIbkrDepth lifecycle', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: DepthState | null;

  function renderSymbol(symbol: string | null, uiActive = true) {
    act(() => {
      root.render(
        <Harness
          symbol={symbol}
          uiActive={uiActive}
          onValue={state => {
            latest = state;
          }}
        />,
      );
    });
  }

  beforeEach(() => {
    FakeWebSocket.instances = [];
    latest = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.useFakeTimers();
  });

  afterEach(() => {
    try {
      act(() => {
        root.unmount();
      });
    } catch {
      /* already unmounted */
    }
    container.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('clears the book on symbol switch and ignores the prior symbol', () => {
    renderSymbol('NXTC');
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain('/depth/NXTC');

    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'book',
          symbol: 'NXTC',
          data: { bids: [{ price: 1, size: 1 }], asks: [], l1_fallback: false },
        }),
      });
    });
    expect(latest?.book?.symbol).toBe('NXTC');

    renderSymbol('MVO');
    expect(latest?.book).toBeNull();
    expect(FakeWebSocket.instances.at(-1)?.url).toContain('/depth/MVO');

    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'book',
          symbol: 'NXTC',
          data: { bids: [{ price: 9, size: 9 }], asks: [], l1_fallback: false },
        }),
      });
    });
    expect(latest?.book).toBeNull();
  });

  it('cancels a pending reconnect timer on unmount', () => {
    renderSymbol('AAPL');
    act(() => {
      FakeWebSocket.instances[0].onclose?.({});
    });
    expect(FakeWebSocket.instances).toHaveLength(1);

    act(() => {
      root.unmount();
    });
    act(() => {
      vi.advanceTimersByTime(8_000);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('backs off a refused line up to 5 s instead of asking every second (AZTA 2026-10-02)', () => {
    renderSymbol('AZTA');
    const refuse = () => act(() => {
      const ws = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
      ws.onopen?.({});
      ws.onmessage?.({ data: JSON.stringify({ type: 'error', message: 'No Level 2 line free for AZTA' }) });
      ws.onclose?.({});
    });
    const waits: number[] = [];
    for (let i = 0; i < 5; i += 1) {
      refuse();
      const before = FakeWebSocket.instances.length;
      let waited = 0;
      while (FakeWebSocket.instances.length === before && waited < 40_000) {
        act(() => {
          vi.advanceTimersByTime(500);
        });
        waited += 500;
      }
      waits.push(waited);
    }
    expect(waits).toEqual([1_000, 2_000, 4_000, 5_000, 5_000]);
    expect(latest?.error).toContain('No Level 2 line free');
  });

  it('folds the book watcher frames and starts over for another symbol', () => {
    renderSymbol('SSTI');
    const send = (ws: FakeWebSocket, symbol: string, data: unknown) => act(() => {
      ws.onmessage?.({ data: JSON.stringify({ type: 'book_watch', symbol, data }) });
    });
    const frame = {
      schema_version: 1, now: 100, reset: true, seq: 1, watching: true, reason: null, window_sec: 60,
      sides: { bid: { pulled_shares: 5800, filled_shares: 0, large_pulls: 1 }, ask: { pulled_shares: 0, filled_shares: 0, large_pulls: 0 } },
      drops: [{ seq: 1, ts: 99, side: 'bid', price: 8.05, pulled: 5800, filled: 0, outcome: 'pulled', large_pull: true, on_approach: false }],
    };
    send(FakeWebSocket.instances[0], 'SSTI', frame);
    expect(latest?.watch?.drops.map(d => d.price)).toEqual([8.05]);
    expect(latest?.watch?.sides?.bid.pulled).toBe(5800);
    send(FakeWebSocket.instances[0], 'SSTI', { ...frame, reset: false, drops: [{ ...frame.drops[0], seq: 2, price: 8.04 }] });
    expect(latest?.watch?.drops.map(d => d.price)).toEqual([8.05, 8.04]);

    renderSymbol('MSGY');
    expect(latest?.watch).toBeNull();
    send(FakeWebSocket.instances[0], 'SSTI', frame); // the old socket's frame never reaches the new symbol
    expect(latest?.watch).toBeNull();
  });

  it('keeps the LULD bands its socket sends, and starts over for another symbol (ADR 047)', () => {
    renderSymbol('GRML');
    const ws = FakeWebSocket.instances[0];
    const frame = (symbol: string, data: Record<string, unknown>) => act(() => {
      ws.onmessage?.({ data: JSON.stringify({ type: 'luld', symbol, data }) });
    });
    frame('GRML', { schema_version: 1, symbol: 'GRML', state: 'bands', exact: true, lower: 14.18, upper: 17.33 });
    expect(latest?.luld?.lower).toBe(14.18);
    frame('GRML', { schema_version: 9, symbol: 'GRML', state: 'bands' });   // an unknown version is no view
    expect(latest?.luld).toBeNull();
    frame('GRML', { schema_version: 1, symbol: 'GRML', state: 'paused', exact: false, lower: null, upper: null });
    expect(latest?.luld?.state).toBe('paused');
    renderSymbol('MVO');
    expect(latest?.luld).toBeNull();
  });

  it('holds the latest book while hidden and applies it on show', () => {
    renderSymbol('AAPL', false);
    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'book',
          symbol: 'AAPL',
          data: { bids: [{ price: 1, size: 1 }], asks: [], l1_fallback: false },
        }),
      });
    });
    expect(latest?.book).toBeNull();
    expect(FakeWebSocket.instances).toHaveLength(1);

    renderSymbol('AAPL', true);
    expect(latest?.book?.symbol).toBe('AAPL');
    expect(latest?.book?.bids[0]?.price).toBe(1);
  });
});
