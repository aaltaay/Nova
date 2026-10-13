/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useIbkrDepth } from './useIbkrDepth';
import refusedFrames from './__fixtures__/depth_refused_frames.json';
import { resetViewRegistryForTests, viewLockLabel, viewLockReason } from '../market_view/viewRegistry';

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
    resetViewRegistryForTests();
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

  // The backend's frames for a 309, written by its own socket route (backend/tests/test_depth_wire_fixture.py,
  // the same order as the desk's live capture at 17:41 ET on 2026-10-13, VLO): `subscribed` goes out before
  // IBKR answers, then the refusal and the close. v1275 asked every 1.2 s (BKYI 232 refusals in 275 s),
  // because `subscribed` reset the backoff the refusal had grown; this file's old fake sent no `subscribed`.
  const refusedLikeTheBackend = (symbol: string) => act(() => {
    const ws = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    ws.onopen?.({});
    for (const frame of refusedFrames.frames as Array<Record<string, unknown>>) {
      if (frame.closed) ws.onclose?.({});
      else ws.onmessage?.({ data: JSON.stringify({ ...frame, symbol }) });
    }
  });

  it('backs off a 309 the backend announced as subscribed first (BKYI / VLO 2026-10-13)', () => {
    renderSymbol('VLO');
    const waits: number[] = [];
    for (let i = 0; i < 5; i += 1) {
      refusedLikeTheBackend('VLO');
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
    expect(latest?.error).toContain('IB error 309');
  });

  it('a refused Level 2 locks orders steadily, says no Level 2 with IBKR\'s reason, and a book clears it', () => {
    // v1275 read "Level 2 is behind the market: no word from Nova" 750 ms into each retry, and open before it.
    renderSymbol('VLO');
    const t0 = Date.now();
    refusedLikeTheBackend('VLO');
    for (let ms = 0; ms <= 6_000; ms += 200) {
      const why = viewLockReason('VLO', t0 + ms);
      expect(why).toContain('No Level 2 for VLO: IBKR refused this Level 2 (IB error 309)');
      expect(why).not.toContain('behind the market');
    }
    expect(viewLockLabel(viewLockReason('VLO', t0)!)).toBe('No Level 2 · locked');

    // The retry's `subscribed` (sent before IBKR answers) does not open it; the first book does.
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    const ws = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    act(() => {
      ws.onmessage?.({ data: JSON.stringify({ type: 'subscribed', symbol: 'VLO', instance: 'x' }) });
    });
    expect(viewLockReason('VLO')).toContain('No Level 2 for VLO');
    act(() => {
      ws.onmessage?.({
        data: JSON.stringify({ type: 'book', symbol: 'VLO', seq: 1, at: 1, sent: Date.now() / 1000,
          data: { bids: [{ price: 456, size: 100 }], asks: [], l1_fallback: false } }),
      });
    });
    expect(viewLockReason('VLO')).toBeNull();
  });

  it('a book proves the line: the next drop retries after 1 s again', () => {
    renderSymbol('VLO');
    refusedLikeTheBackend('VLO');
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    refusedLikeTheBackend('VLO');
    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    const ws = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    act(() => {
      ws.onmessage?.({ data: JSON.stringify({ type: 'subscribed', symbol: 'VLO', instance: 'x' }) });
      ws.onmessage?.({
        data: JSON.stringify({ type: 'book', symbol: 'VLO', seq: 1, at: 1, sent: Date.now() / 1000,
          data: { bids: [{ price: 456, size: 1 }], asks: [], l1_fallback: false } }),
      });
      ws.onclose?.({});
    });
    const before = FakeWebSocket.instances.length;
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(FakeWebSocket.instances.length).toBe(before + 1);
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
