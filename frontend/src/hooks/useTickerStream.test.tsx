/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TICKER_WS_RECONNECT_MS } from '../constants';
import { useTickerStream, type TickerStreamState } from './useTickerStream';

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

function Harness({
  symbol,
  onValue,
}: {
  symbol: string | null;
  onValue: (state: TickerStreamState) => void;
}) {
  const state = useTickerStream(symbol);
  onValue(state);
  return null;
}

function sendInitial(ws: FakeWebSocket, symbol: string) {
  ws.onmessage?.({
    data: JSON.stringify({
      type: 'initial',
      symbol,
      snapshot: { latest_trade: { price: 10 } },
    }),
  });
}

describe('useTickerStream reconnect', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: TickerStreamState | null;

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
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => {})),
    );
    vi.useFakeTimers();
  });

  afterEach(() => {
    try {
      act(() => {
        root.unmount();
      });
    } catch {
      /* already unmounted by the cancel-timer case */
    }
    container.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('clears detail and stale when the symbol switches', () => {
    renderSymbol('AAPL');
    expect(FakeWebSocket.instances).toHaveLength(1);

    act(() => {
      sendInitial(FakeWebSocket.instances[0], 'AAPL');
    });
    expect(latest?.detail?.symbol).toBe('AAPL');
    expect(latest?.stale).toBe(false);

    renderSymbol('MSFT');
    expect(latest?.detail).toBeNull();
    expect(latest?.stale).toBe(false);
    expect(latest?.disconnectedSince).toBeNull();
    expect(FakeWebSocket.instances.at(-1)?.url).toContain('/ticker/MSFT');
  });

  it('schedules a reconnect after close and keeps the last quote as stale', () => {
    renderSymbol('AAPL');
    const first = FakeWebSocket.instances[0];
    act(() => {
      sendInitial(first, 'AAPL');
    });
    expect(latest?.stale).toBe(false);

    act(() => {
      first.onclose?.({});
    });
    expect(latest?.detail?.symbol).toBe('AAPL');
    expect(latest?.stale).toBe(true);
    expect(latest?.disconnectedSince).toEqual(expect.any(Number));
    expect(FakeWebSocket.instances).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(TICKER_WS_RECONNECT_MS);
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(FakeWebSocket.instances[1].url).toContain('/ticker/AAPL');

    act(() => {
      sendInitial(FakeWebSocket.instances[1], 'AAPL');
    });
    expect(latest?.stale).toBe(false);
    expect(latest?.disconnectedSince).toBeNull();
  });

  it('cancels a pending reconnect timer on unmount', () => {
    renderSymbol('AAPL');
    act(() => {
      sendInitial(FakeWebSocket.instances[0], 'AAPL');
      FakeWebSocket.instances[0].onclose?.({});
    });
    expect(FakeWebSocket.instances).toHaveLength(1);

    act(() => {
      root.unmount();
    });
    act(() => {
      vi.advanceTimersByTime(TICKER_WS_RECONNECT_MS * 4);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
