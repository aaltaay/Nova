/**
 * @vitest-environment jsdom
 *
 * A Trader tab's Time & Sales whose line went with its Level 2 to a setup (ADR 043 decision 6):
 * it says so, drops the tape it can no longer keep live, never reconnects by its backoff, and
 * comes back with the tab's Level 2 -- on the same poll when the loan ends, or at once when the
 * tab comes to the front.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { L2_LENT_POLL_MS } from '../constantGroups/market_ui';
import { resetLoanWatchForTests } from './loanWatch';
import { useIbkrDepth } from './useIbkrDepth';
import { useIbkrTape, type TapeState } from './useIbkrTape';

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
  why: 'near its trigger',
  tier: 'near',
  since: 1_790_900_000,
  text: "Level 2 lent to AISP's first pullback (near its trigger) -- back when it ends or when you bring this tab to the front",
};

const LOAN = {
  lender: 'ABC', borrower: 'AISP', setup_type: 'first_pullback', setup_id: 'AISP-2026-10-01-1',
  since: 1_790_900_000, why: 'in a trade', tier: 'trade', text: null, tape: true, tape_state: 'receiving',
  tape_error: null, tape_lent: true, tape_last_print: 1_790_900_010,
};

const PRINT = {
  type: 'print', symbol: 'ABC', time: '2026-10-01T13:45:00.000Z', price: 5.12, size: 300, exchange: 'NSDQ',
  conditions: '', side: 'ask', bid: 5.11, ask: 5.12,
};

function linesAnswer(loans: unknown[]) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ schema_version: 1, cap: 3, lines: [], lending: { on: true, loans, recent: [], error: null } }),
  };
}

function TapeHarness({ uiActive, traderTab = true, onValue }: {
  uiActive: boolean;
  traderTab?: boolean;
  onValue: (state: TapeState) => void;
}) {
  onValue(useIbkrTape('ABC', uiActive, { traderTab }));
  return null;
}

/** The Trader tab's rail: its Level 2 and its Time & Sales on one symbol. */
function TabHarness({ uiActive, onDepth, onTape }: {
  uiActive: boolean;
  onDepth: (state: DepthState) => void;
  onTape: (state: TapeState) => void;
}) {
  onDepth(useIbkrDepth('ABC', uiActive, { traderTab: true }));
  onTape(useIbkrTape('ABC', uiActive, { traderTab: true }));
  return null;
}

describe('useIbkrTape with a lent line', () => {
  let container: HTMLDivElement;
  let root: Root;
  let tape: TapeState | null;
  let depth: DepthState | null;
  let fetchMock: ReturnType<typeof vi.fn>;

  function render(uiActive: boolean, traderTab = true) {
    act(() => {
      root.render(<TapeHarness uiActive={uiActive} traderTab={traderTab} onValue={(s) => { tape = s; }} />);
    });
  }

  function renderTab(uiActive: boolean) {
    act(() => {
      root.render(<TabHarness uiActive={uiActive} onDepth={(s) => { depth = s; }} onTape={(s) => { tape = s; }} />);
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
  const tapeSockets = () => sockets().filter((s) => s.url.includes('/ws/ibkr/tape/'));
  const depthSockets = () => sockets().filter((s) => s.url.includes('/ws/ibkr/depth/'));

  beforeEach(() => {
    FakeWebSocket.instances = [];
    tape = null;
    depth = null;
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
    resetLoanWatchForTests();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('says it is a Trader tab, and whether it is the tab in front', () => {
    render(false);
    expect(sockets()[0].url).toContain('/ws/ibkr/tape/ABC?tab=1&front=0');
    act(() => root.unmount());
    root = createRoot(container);
    render(true);
    expect(sockets()[1].url).toContain('/ws/ibkr/tape/ABC?tab=1&front=1');
  });

  it('another Time & Sales never says it is a Trader tab', () => {
    render(true, false);
    expect(sockets()[0].url).toContain('/ws/ibkr/tape/ABC?front=1');
    expect(sockets()[0].url).not.toContain('tab=1');
  });

  it('a lent frame drops the tape it can no longer keep live and says whose setup took it', async () => {
    render(true);
    act(() => {
      sockets()[0].frame({ type: 'subscribed', symbol: 'ABC' });
      sockets()[0].frame(PRINT);
    });
    await wait(20);                                          // the print reaches the pane
    expect(tape?.prints).toHaveLength(1);
    lend(sockets()[0]);                                      // lent while in front (the focus report trailed)
    expect(tape?.prints).toEqual([]);
    expect(tape?.connected).toBe(false);
    expect(tape?.error).toBeNull();
    expect(tape?.lent).toMatchObject({ symbol: 'AISP', setupType: 'first_pullback', tier: 'near' });
    expect(sockets()).toHaveLength(2);                       // the pane in front asks for it back at once
    expect(sockets()[1].url).toContain('front=1');
  });

  it('a hidden pane shows the lent words, and no old tape, when it is shown', async () => {
    render(true);
    act(() => {
      sockets()[0].frame({ type: 'subscribed', symbol: 'ABC' });
      sockets()[0].frame(PRINT);
    });
    await wait(20);
    render(false);
    lend(sockets()[0]);
    expect(tape?.prints).toHaveLength(1);                    // a hidden pane draws nothing new
    render(true);
    expect(tape?.prints).toEqual([]);
    expect(tape?.lent).toMatchObject({ symbol: 'AISP' });
  });

  it('never reconnects by its backoff while lent, and comes back when the loan ends', async () => {
    render(false);
    lend(sockets()[0]);
    fetchMock.mockResolvedValueOnce(linesAnswer([LOAN]));
    await wait(L2_LENT_POLL_MS);
    expect(sockets()).toHaveLength(1);                       // the loan stands: no socket
    fetchMock.mockResolvedValueOnce(linesAnswer([]));
    await wait(L2_LENT_POLL_MS);
    expect(sockets()).toHaveLength(2);                       // it ended: the line is asked for again
    expect(sockets()[1].url).toContain('/ws/ibkr/tape/ABC?tab=1&front=0');
    await wait(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);              // and the poll stopped
  });

  it('takes the line back the moment the tab comes to the front, showing why until it answers', () => {
    render(false);
    lend(sockets()[0]);
    render(true);
    expect(sockets()).toHaveLength(2);
    expect(sockets()[1].url).toContain('/ws/ibkr/tape/ABC?tab=1&front=1');
    expect(tape?.lent).toMatchObject({ symbol: 'AISP' });
    act(() => sockets()[1].frame({ type: 'subscribed', symbol: 'ABC' }));
    expect(tape?.lent).toBeNull();
    expect(tape?.connected).toBe(true);
  });

  it('a take-back the backend refuses says why, then falls back to the backoff', async () => {
    render(false);
    lend(sockets()[0]);
    render(true);
    act(() => {
      sockets()[1].frame({ type: 'error', symbol: 'ABC', message: 'Resubscribing in 9s — please wait' });
      sockets()[1].close();
    });
    expect(tape?.lent).toBeNull();
    expect(tape?.error).toBe('Resubscribing in 9s — please wait');
    await wait(1_000);
    expect(sockets()).toHaveLength(3);
  });

  it("the tab's Level 2 and Time & Sales wait on one poll and come back together", async () => {
    renderTab(false);
    expect(depthSockets()).toHaveLength(1);
    expect(tapeSockets()).toHaveLength(1);
    lend(depthSockets()[0]);
    lend(tapeSockets()[0]);
    fetchMock.mockResolvedValueOnce(linesAnswer([LOAN]));
    await wait(L2_LENT_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(1);              // one request for both panes
    expect(sockets()).toHaveLength(2);                       // the loan stands: neither asks
    fetchMock.mockResolvedValueOnce(linesAnswer([]));
    await wait(L2_LENT_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(depthSockets().map((s) => s.url.split('?')[1])).toEqual(['tab=1&front=0', 'tab=1&front=0']);
    expect(tapeSockets().map((s) => s.url.split('?')[1])).toEqual(['tab=1&front=0', 'tab=1&front=0']);
    await wait(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);              // and the poll stopped
  });

  it("brought to the front, the tab asks for both lines back at once, saying why until they answer", async () => {
    renderTab(false);
    lend(depthSockets()[0]);
    lend(tapeSockets()[0]);
    fetchMock.mockResolvedValueOnce(linesAnswer([LOAN]));
    await wait(L2_LENT_POLL_MS);
    renderTab(true);
    expect(depthSockets().map((s) => s.url.split('?')[1])).toEqual(['tab=1&front=0', 'tab=1&front=1']);
    expect(tapeSockets().map((s) => s.url.split('?')[1])).toEqual(['tab=1&front=0', 'tab=1&front=1']);
    expect(depth?.lent).toMatchObject({ symbol: 'AISP', tier: 'trade' });   // the poll's newest reason
    expect(tape?.lent).toMatchObject({ symbol: 'AISP', tier: 'trade' });
    act(() => {
      depthSockets()[1].frame({ type: 'subscribed', symbol: 'ABC' });
      tapeSockets()[1].frame({ type: 'subscribed', symbol: 'ABC' });
    });
    expect(depth?.lent).toBeNull();
    expect(tape?.lent).toBeNull();
    await wait(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);              // nothing waits on the poll any more
  });
});
