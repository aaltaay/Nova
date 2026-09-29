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
