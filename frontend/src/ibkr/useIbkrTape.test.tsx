/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearBarsStoreForTests, getBarsEntry } from '../chart/barsStore';
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
  uiActive = true,
  onValue,
}: {
  symbol: string | null;
  uiActive?: boolean;
  onValue: (state: TapeState) => void;
}) {
  const state = useIbkrTape(symbol, uiActive);
  onValue(state);
  return null;
}

function flushTapeFrame() {
  act(() => {
    vi.advanceTimersByTime(16);
  });
}

describe('useIbkrTape lifecycle', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: TapeState | null;

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
    clearBarsStoreForTests();
    latest = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 16) as unknown as number,
    );
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
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
    flushTapeFrame();
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

  it('seeds an empty 10Sec chart from the first live tape print', () => {
    renderSymbol('SPCI');

    act(() => {
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({
          type: 'print',
          symbol: 'SPCI',
          time: '2026-09-11T13:29:55.000Z',
          price: 150,
          size: 100,
        }),
      });
    });

    const entry = getBarsEntry('SPCI', '10Sec');
    expect(entry?.bars).toEqual([
      {
        t: '2026-09-11T13:29:50.000Z',
        o: 150,
        h: 150,
        l: 150,
        c: 150,
        v: 100,
      },
    ]);
    expect(entry?.coverage?.filling).toBe(true);
  });

  it("carries the backend's unreported / sets_price verdict onto each print (#543)", () => {
    renderSymbol('PLTR');
    act(() => {
      const ws = FakeWebSocket.instances[0];
      const frames = [
        { price: 192.75, size: 200, conditions: '', unreported: false, sets_price: true },
        { price: 190.37, size: 1, conditions: '   I', unreported: false, sets_price: false },
        { price: 190.38, size: 100, conditions: ' 4 W', unreported: true, sets_price: false },
        // An older backend sends neither field: the print reads as a price.
        { price: 192.8, size: 100, conditions: '' },
      ];
      frames.forEach((frame, i) => {
        ws.onmessage?.({
          data: JSON.stringify({
            type: 'print', symbol: 'PLTR', time: `2026-09-23T13:45:0${i + 1}.000Z`, ...frame,
          }),
        });
      });
    });
    flushTapeFrame();
    expect(latest?.prints.map(p => [p.price, p.unreported, p.setsPrice])).toEqual([
      [192.8, false, true],
      [190.38, true, false],
      [190.37, false, false],
      [192.75, false, true],
    ]);
    // The 10Sec candle takes the same verdict: no wick from the volume-only prints.
    expect(getBarsEntry('PLTR', '10Sec')?.bars).toEqual([
      { t: '2026-09-23T13:45:00.000Z', o: 192.75, h: 192.8, l: 192.75, c: 192.8, v: 300 },
    ]);
  });

  it('coalesces a print burst into one ordered ring after one frame', () => {
    renderSymbol('AAPL');
    act(() => {
      const ws = FakeWebSocket.instances[0];
      for (const price of [1, 2, 3, 4, 5]) {
        ws.onmessage?.({
          data: JSON.stringify({
            type: 'print',
            symbol: 'AAPL',
            time: `2026-09-18T13:00:00.00${price}Z`,
            price,
            size: 10,
          }),
        });
      }
    });
    expect(latest?.prints).toEqual([]);
    flushTapeFrame();
    expect(latest?.prints.map(p => p.price)).toEqual([5, 4, 3, 2, 1]);
  });

  it('keeps the ring while hidden and flushes on show without dropping prints', () => {
    renderSymbol('AAPL', false);
    act(() => {
      const ws = FakeWebSocket.instances[0];
      for (const price of [1, 2, 3]) {
        ws.onmessage?.({
          data: JSON.stringify({
            type: 'print',
            symbol: 'AAPL',
            time: `2026-09-18T13:00:00.00${price}Z`,
            price,
            size: 10,
          }),
        });
      }
    });
    flushTapeFrame();
    expect(latest?.prints).toEqual([]);
    expect(getBarsEntry('AAPL', '10Sec')?.bars).toHaveLength(1);

    renderSymbol('AAPL', true);
    expect(latest?.prints.map(p => p.price)).toEqual([3, 2, 1]);
  });
});
