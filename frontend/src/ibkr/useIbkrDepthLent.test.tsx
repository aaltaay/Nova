/**
 * @vitest-environment jsdom
 *
 * A Trader tab's Level 2 whose line is lent to a setup (ADR 043 decision 6): it says so, never
 * reconnects by its backoff, comes back when the loan ends (the lines poll) or at once when the
 * tab comes to the front -- and keeps the lent words up until the line answers.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { L2_LENT_POLL_MS } from '../constantGroups/market_ui';
import { useIbkrDepth } from './useIbkrDepth';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.({});
  }

  send() {}

  frame(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
}

type DepthState = ReturnType<typeof useIbkrDepth>;

const LENT = {
  type: 'lent',
  symbol: 'ABC',
  to: { symbol: 'AISP', setup_type: 'first_pullback', setup_id: 'AISP-2026-10-01-1' },
  why: 'armed',
  tier: 'armed',
  since: 1_790_900_000,
  text: "Level 2 lent to AISP's first pullback (armed) -- back when it ends or when you bring this tab to the front",
};

const LOAN = {
  lender: 'ABC', borrower: 'AISP', setup_type: 'first_pullback', setup_id: 'AISP-2026-10-01-1',
  since: 1_790_900_000, why: 'near its trigger', tier: 'near', text: null,
};

function linesAnswer(loans: unknown[]) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ schema_version: 1, cap: 3, lines: [], lending: { on: true, loans, recent: [], error: null } }),
  };
}

function Harness({ uiActive, traderTab = true, onValue }: {
  uiActive: boolean;
  traderTab?: boolean;
  onValue: (state: DepthState) => void;
}) {
  const state = useIbkrDepth('ABC', uiActive, { traderTab });
  onValue(state);
  return null;
}

describe('useIbkrDepth with a lent line', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: DepthState | null;
  let fetchMock: ReturnType<typeof vi.fn>;

  function render(uiActive: boolean, traderTab = true) {
    act(() => {
      root.render(<Harness uiActive={uiActive} traderTab={traderTab} onValue={(s) => { latest = s; }} />);
    });
  }

  function lend(ws: FakeWebSocket) {
    act(() => {
      ws.frame(LENT);
      ws.close();
    });
  }

  async function wait(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }

  const sockets = () => FakeWebSocket.instances;

  beforeEach(() => {
    FakeWebSocket.instances = [];
    latest = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    vi.useFakeTimers();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('says it is a Trader tab, and whether it is the tab in front', () => {
    render(false);
    expect(sockets()[0].url).toContain('/ws/ibkr/depth/ABC?tab=1&front=0');
    act(() => root.unmount());
    root = createRoot(container);
    render(true);
    expect(sockets()[1].url).toContain('/ws/ibkr/depth/ABC?tab=1&front=1');
  });

  it('another Level 2 never says it is a Trader tab', () => {
    render(true, false);
    expect(sockets()[0].url).toContain('/ws/ibkr/depth/ABC?front=1');
    expect(sockets()[0].url).not.toContain('tab=1');
  });

  it('never reconnects by its backoff while lent, and comes back when the loan ends', async () => {
    render(false);
    lend(sockets()[0]);
    fetchMock.mockResolvedValueOnce(linesAnswer([LOAN]));
    await wait(L2_LENT_POLL_MS);
    expect(sockets()).toHaveLength(1);                       // the loan stands: no socket
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/ibkr/depth/lines');
    fetchMock.mockResolvedValueOnce(linesAnswer([]));
    await wait(L2_LENT_POLL_MS);
    expect(sockets()).toHaveLength(2);                       // it ended: the line is asked for again
    expect(sockets()[1].url).toContain('front=0');
    await wait(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);              // and the poll stopped
  });

  it('a poll the backend does not answer leaves the line lent', async () => {
    render(false);
    lend(sockets()[0]);
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    await wait(3 * L2_LENT_POLL_MS);
    expect(sockets()).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('takes the line back the moment the tab comes to the front, showing why until it answers', () => {
    render(false);
    lend(sockets()[0]);
    expect(sockets()).toHaveLength(1);
    render(true);
    expect(sockets()).toHaveLength(2);
    expect(sockets()[1].url).toContain('/ws/ibkr/depth/ABC?tab=1&front=1');
    expect(latest?.lent).toMatchObject({ symbol: 'AISP', setupType: 'first_pullback', tier: 'armed' });
    act(() => sockets()[1].frame({ type: 'subscribed', symbol: 'ABC' }));
    expect(latest?.lent).toBeNull();
    expect(latest?.connected).toBe(true);
  });

  it('the poll keeps the newest reason for when the tab is shown', async () => {
    render(false);
    lend(sockets()[0]);
    fetchMock.mockResolvedValue(linesAnswer([LOAN]));
    await wait(L2_LENT_POLL_MS);
    render(true);                                            // shown: the reason is the poll's, then it is taken back
    expect(latest?.lent).toMatchObject({ tier: 'near', why: 'near its trigger' });
  });

  it('a lent frame on the tab in front takes the line back at once', () => {
    render(true);
    lend(sockets()[0]);
    expect(sockets()).toHaveLength(2);
    expect(sockets()[1].url).toContain('front=1');
  });

  it('a take-back that closes unanswered falls back to the backoff', async () => {
    render(false);
    lend(sockets()[0]);
    render(true);
    act(() => sockets()[1].close());
    expect(latest?.lent).toBeNull();
    await wait(1_000);
    expect(sockets()).toHaveLength(3);
  });
});
