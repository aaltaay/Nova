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
  onValue,
}: {
  symbol: string | null;
  onValue: (state: DepthState) => void;
}) {
  const state = useIbkrDepth(symbol);
  onValue(state);
  return null;
}

describe('useIbkrDepth lifecycle', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: DepthState | null;

  function renderSymbol(symbol: string | null) {
    act(() => {
      root.render(
        <Harness
          symbol={symbol}
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
});
