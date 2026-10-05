/**
 * @vitest-environment jsdom
 *
 * The ticker stream outside React (#707): every Trader panel reads the part it shows, so a print renders
 * only the panels that show it -- and two readers of one symbol share one socket.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetTickerStreamsForTests, tickerLastTrade } from './tickerStore';
import { useTickerSelect } from './useTickerStream';

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

const send = (ws: FakeWebSocket, msg: object) => act(() => ws.onmessage?.({ data: JSON.stringify(msg) }));

function Price({ symbol, onRender }: { symbol: string; onRender: (price: number | null) => void }) {
  const price = useTickerSelect(symbol, (state) => tickerLastTrade(state, symbol)?.price ?? null);
  onRender(price);
  return null;
}

describe('the ticker store', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    vi.useFakeTimers();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    resetTickerStreamsForTests();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('renders a reader of the price on a new price, not on a print at the same price', () => {
    const seen: (number | null)[] = [];
    act(() => root.render(<Price symbol="AAPL" onRender={(p) => seen.push(p)} />));
    const ws = FakeWebSocket.instances[0];
    send(ws, { type: 'initial', symbol: 'AAPL', snapshot: { latest_trade: { price: 10, timestamp: '2026-10-05T14:00:00Z' } } });
    const afterInitial = seen.length;
    expect(seen.at(-1)).toBe(10);

    send(ws, { type: 'trade_update', symbol: 'AAPL', price: 10, timestamp: '2026-10-05T14:00:01Z', volume: 5_000 });
    send(ws, { type: 'trade_update', symbol: 'AAPL', price: 10, timestamp: '2026-10-05T14:00:02Z', volume: 6_000 });
    expect(seen.length).toBe(afterInitial);

    send(ws, { type: 'trade_update', symbol: 'AAPL', price: 10.05, timestamp: '2026-10-05T14:00:03Z', volume: 7_000 });
    expect(seen.length).toBe(afterInitial + 1);
    expect(seen.at(-1)).toBe(10.05);
  });

  it('shares one socket between readers of one symbol, whatever its case, and closes it after the last', () => {
    act(() => root.render(
      <>
        <Price symbol="AAPL" onRender={() => {}} />
        <Price symbol="aapl" onRender={() => {}} />
      </>,
    ));
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].url).toContain('/ticker/AAPL');

    act(() => root.render(<Price symbol="AAPL" onRender={() => {}} />));
    act(() => vi.advanceTimersByTime(0));
    expect(FakeWebSocket.instances[0].readyState).toBe(0);

    act(() => root.render(null));
    act(() => vi.advanceTimersByTime(0));
    expect(FakeWebSocket.instances[0].readyState).toBe(3);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it('keeps the socket for a reader that leaves and comes back in one commit', () => {
    act(() => root.render(<Price key="a" symbol="MSFT" onRender={() => {}} />));
    act(() => root.render(<Price key="b" symbol="MSFT" onRender={() => {}} />));
    act(() => vi.advanceTimersByTime(0));
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.instances[0].readyState).toBe(0);
  });
});
