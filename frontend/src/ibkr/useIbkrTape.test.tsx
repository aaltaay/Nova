/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useIbkrTape, type TapeState } from './useIbkrTape';

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
  onValue: (state: TapeState) => void;
}) {
  const state = useIbkrTape(symbol);
  onValue(state);
  return null;
}

describe('useIbkrTape lifecycle', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: TapeState | null;

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

  it('clears prints on symbol switch and drops the prior symbol', () => {
    renderSymbol('AAPL');
    expect(FakeWebSocket.instances[0].url).toContain('/tape/AAPL');

    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'print',
          symbol: 'AAPL',
          time: '09:30:00',
          price: 10,
          size: 100,
        }),
      });
    });
    expect(latest?.prints).toHaveLength(1);
    expect(latest?.prints[0]?.symbol).toBe('AAPL');

    renderSymbol('MSFT');
    expect(latest?.prints).toEqual([]);
    expect(FakeWebSocket.instances.at(-1)?.url).toContain('/tape/MSFT');

    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'print',
          symbol: 'AAPL',
          time: '09:30:01',
          price: 11,
          size: 50,
        }),
      });
    });
    expect(latest?.prints).toEqual([]);
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
