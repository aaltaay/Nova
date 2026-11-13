/**
 * @vitest-environment jsdom
 *
 * A Time & Sales on a stock no lane is on (ADR 071): it drops the tape it can no longer keep live, says where your
 * lane is, never reconnects by its backoff and never takes your lane back by itself, and comes back with the tab's
 * Level 2 -- on the same poll when a lane comes to its stock, or at once when the tab comes to the front.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LANE_WAIT_POLL_MS } from '../constantGroups/market_ui';
import { resetLaneWatchForTests } from './laneWait';
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

const lane = { you: 'TGHL', claude: null, bots: null };
const TAPE_LANE = { type: 'lane', symbol: 'ABC', message: 'Your Level 2 moved to TGHL.', lane };
const DEPTH_LANE = { type: 'error', symbol: 'ABC', message: 'Your Level 2 moved to TGHL.', evicted: true, lane };

const PRINT = {
  type: 'print', symbol: 'ABC', time: '2026-10-01T13:45:00.000Z', price: 5.12, size: 300, exchange: 'NSDQ',
  conditions: '', side: 'ask', bid: 5.11, ask: 5.12,
};

const empty = { symbol: null, since: null, depth: false, tape: false, recording: false, error: null };

function lanesAnswer(you: string | null, claude: string | null = null) {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      schema_version: 1, you: { ...empty, symbol: you }, claude: { ...empty, symbol: claude },
      bots: { ...empty, setup: null, why: null, waiting: [] }, recording_error: null,
    }),
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

describe('useIbkrTape on a stock no lane is on', () => {
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

  function noLane(ws: FakeWebSocket, frame: unknown = TAPE_LANE) {
    act(() => {
      ws.frame(frame);
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
    resetLaneWatchForTests();
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

  it('a lane frame drops the tape it can no longer keep live, says where your lane is and never asks by itself', async () => {
    render(true);
    act(() => {
      sockets()[0].frame({ type: 'subscribed', symbol: 'ABC' });
      sockets()[0].frame(PRINT);
    });
    await wait(20);                                          // the print reaches the pane
    expect(tape?.prints).toHaveLength(1);
    noLane(sockets()[0]);                                    // your lane moved on while this pane is in front
    expect(tape?.prints).toEqual([]);
    expect(tape?.connected).toBe(false);
    expect(tape?.error).toBeNull();
    expect(tape?.laneWait?.text).toBe('Your Time & Sales is on TGHL — click here or bring this tab to the front to have it on ABC');
    fetchMock.mockResolvedValue(lanesAnswer('TGHL'));
    await wait(60_000);
    expect(sockets()).toHaveLength(1);                       // two windows in front never pass the lane to and fro
  });

  it('a hidden pane shows the lane words, and no old tape, when it is shown', async () => {
    render(true);
    act(() => {
      sockets()[0].frame({ type: 'subscribed', symbol: 'ABC' });
      sockets()[0].frame(PRINT);
    });
    await wait(20);
    render(false);
    noLane(sockets()[0]);
    expect(tape?.prints).toHaveLength(1);                    // a hidden pane draws nothing new
    render(true);                                            // shown: your lane is asked for, the words stay until it answers
    expect(tape?.prints).toEqual([]);
    expect(tape?.laneWait).toMatchObject({ you: 'TGHL' });
  });

  it('never reconnects by its backoff, and views a lane that comes to its stock', async () => {
    render(false);
    noLane(sockets()[0]);
    fetchMock.mockResolvedValueOnce(lanesAnswer('TGHL'));
    await wait(LANE_WAIT_POLL_MS);
    expect(sockets()).toHaveLength(1);                       // no lane on ABC: no socket
    fetchMock.mockResolvedValueOnce(lanesAnswer('TGHL', 'ABC'));
    await wait(LANE_WAIT_POLL_MS);
    expect(sockets()).toHaveLength(2);                       // Claude's lane came to ABC: asked again
    expect(sockets()[1].url).toContain('/ws/ibkr/tape/ABC?tab=1&front=0');
    await wait(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);              // and the poll stopped
  });

  it('brings your lane the moment the tab comes to the front, showing why until it answers', () => {
    render(false);
    noLane(sockets()[0]);
    render(true);
    expect(sockets()).toHaveLength(2);
    expect(sockets()[1].url).toContain('/ws/ibkr/tape/ABC?tab=1&front=1');
    expect(tape?.laneWait).toMatchObject({ you: 'TGHL' });
    act(() => sockets()[1].frame({ type: 'subscribed', symbol: 'ABC' }));
    expect(tape?.laneWait).toBeNull();
    expect(tape?.connected).toBe(true);
  });

  it('an ask the backend refuses says why, then falls back to the backoff', async () => {
    render(false);
    noLane(sockets()[0]);
    render(true);
    act(() => {
      sockets()[1].frame({ type: 'error', symbol: 'ABC', message: 'IBKR allows ABC\'s tape again in 9 s' });
      sockets()[1].close();
    });
    expect(tape?.laneWait).toBeNull();
    expect(tape?.error).toBe('IBKR allows ABC\'s tape again in 9 s');
    await wait(1_000);
    expect(sockets()).toHaveLength(3);
  });

  it("the tab's Level 2 and Time & Sales wait on one poll and come back together", async () => {
    renderTab(false);
    expect(depthSockets()).toHaveLength(1);
    expect(tapeSockets()).toHaveLength(1);
    noLane(depthSockets()[0], DEPTH_LANE);
    noLane(tapeSockets()[0]);
    fetchMock.mockResolvedValueOnce(lanesAnswer('TGHL'));
    await wait(LANE_WAIT_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(1);              // one request for both panes
    expect(sockets()).toHaveLength(2);                       // no lane on ABC: neither asks
    fetchMock.mockResolvedValueOnce(lanesAnswer('ABC'));
    await wait(LANE_WAIT_POLL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(depthSockets().map((s) => s.url.split('?')[1])).toEqual(['tab=1&front=0', 'tab=1&front=0']);
    expect(tapeSockets().map((s) => s.url.split('?')[1])).toEqual(['tab=1&front=0', 'tab=1&front=0']);
    await wait(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);              // and the poll stopped
  });

  it('brought to the front, the tab asks for both lines at once, saying where your lane was until they answer', async () => {
    renderTab(false);
    noLane(depthSockets()[0], DEPTH_LANE);
    noLane(tapeSockets()[0]);
    fetchMock.mockResolvedValueOnce(lanesAnswer('RUNR'));
    await wait(LANE_WAIT_POLL_MS);
    renderTab(true);
    expect(depthSockets().map((s) => s.url.split('?')[1])).toEqual(['tab=1&front=0', 'tab=1&front=1']);
    expect(tapeSockets().map((s) => s.url.split('?')[1])).toEqual(['tab=1&front=0', 'tab=1&front=1']);
    expect(depth?.laneWait).toMatchObject({ you: 'RUNR' });  // the poll's newest word
    expect(tape?.laneWait).toMatchObject({ you: 'RUNR' });
    act(() => {
      depthSockets()[1].frame({ type: 'subscribed', symbol: 'ABC' });
      tapeSockets()[1].frame({ type: 'subscribed', symbol: 'ABC' });
    });
    expect(depth?.laneWait).toBeNull();
    expect(tape?.laneWait).toBeNull();
    await wait(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);              // nothing waits on the poll any more
  });
});
