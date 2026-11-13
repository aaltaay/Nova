/**
 * @vitest-environment jsdom
 *
 * A Level 2 on a stock no lane is on (ADR 071): it says where your lane is, never reconnects by its backoff and
 * never takes your lane back by itself -- two windows in front would pass it to and fro. It asks again with
 * `front=1` when it comes to the front or its words are clicked, and with `front=0` when the lanes poll finds a
 * lane on its stock; the words stay up until the line answers.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LANE_WAIT_POLL_MS } from '../constantGroups/market_ui';
import { bringLane, resetLaneWatchForTests } from './laneWait';
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

const LANE_FRAME = {
  type: 'error', symbol: 'ABC', message: 'Your Level 2 moved to TGHL.', evicted: true,
  lane: { you: 'TGHL', claude: null, bots: null },
};

const empty = { symbol: null, since: null, depth: false, tape: false, recording: false, error: null };

function lanesAnswer(you: string | null, bots: string | null = null) {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      schema_version: 1, you: { ...empty, symbol: you }, claude: empty,
      bots: { ...empty, symbol: bots, setup: null, why: null, waiting: [] }, recording_error: null,
    }),
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

describe('useIbkrDepth on a stock no lane is on', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: DepthState | null;
  let fetchMock: ReturnType<typeof vi.fn>;

  function render(uiActive: boolean, traderTab = true) {
    act(() => {
      root.render(<Harness uiActive={uiActive} traderTab={traderTab} onValue={(s) => { latest = s; }} />);
    });
  }

  function noLane(ws: FakeWebSocket) {
    act(() => {
      ws.frame(LANE_FRAME);
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
    resetLaneWatchForTests();
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

  it('never reconnects by its backoff, and views a lane that comes to its stock', async () => {
    render(false);
    noLane(sockets()[0]);
    fetchMock.mockResolvedValueOnce(lanesAnswer('TGHL'));
    await wait(LANE_WAIT_POLL_MS);
    expect(sockets()).toHaveLength(1);                       // no lane on ABC: no socket
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/ibkr/lanes');
    fetchMock.mockResolvedValueOnce(lanesAnswer('TGHL', 'ABC'));
    await wait(LANE_WAIT_POLL_MS);
    expect(sockets()).toHaveLength(2);                       // the bots' lane came to ABC: asked again
    expect(sockets()[1].url).toContain('front=0');           // ... without moving your lane
    await wait(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(2);              // and the poll stopped
  });

  it('a poll the backend does not answer leaves it waiting', async () => {
    render(false);
    noLane(sockets()[0]);
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    await wait(3 * LANE_WAIT_POLL_MS);
    expect(sockets()).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('brings your lane the moment the tab comes to the front, showing why until it answers', () => {
    render(false);
    noLane(sockets()[0]);
    expect(sockets()).toHaveLength(1);
    render(true);
    expect(sockets()).toHaveLength(2);
    expect(sockets()[1].url).toContain('/ws/ibkr/depth/ABC?tab=1&front=1');
    expect(latest?.laneWait).toMatchObject({ you: 'TGHL' });
    act(() => sockets()[1].frame({ type: 'subscribed', symbol: 'ABC' }));
    expect(latest?.laneWait).toBeNull();
    expect(latest?.connected).toBe(true);
  });

  it('a lane frame on the pane in front says where your lane is and never asks again by itself', async () => {
    render(true);
    noLane(sockets()[0]);
    expect(latest?.laneWait).toMatchObject({ you: 'TGHL' });
    expect(latest?.laneWait?.text).toBe('Your Level 2 is on TGHL — click here or bring this tab to the front to have it on ABC');
    expect(latest?.error).toBeNull();
    fetchMock.mockResolvedValue(lanesAnswer('TGHL'));
    await wait(60_000);
    expect(sockets()).toHaveLength(1);                       // two windows in front never pass the lane to and fro
  });

  it('a click on its words brings your lane here', () => {
    render(true);
    noLane(sockets()[0]);
    act(() => bringLane('abc'));
    expect(sockets()).toHaveLength(2);
    expect(sockets()[1].url).toContain('front=1');
  });

  it('the poll keeps where your lane is now', async () => {
    render(true);
    noLane(sockets()[0]);
    fetchMock.mockResolvedValue(lanesAnswer('RUNR'));
    await wait(LANE_WAIT_POLL_MS);
    expect(latest?.laneWait).toMatchObject({ you: 'RUNR' });
    expect(latest?.laneWait?.plain).toBe('Your Level 2 is on RUNR, not ABC');
  });

  it('an ask that closes unanswered falls back to the backoff', async () => {
    render(false);
    noLane(sockets()[0]);
    render(true);
    act(() => sockets()[1].close());
    expect(latest?.laneWait).toBeNull();
    await wait(1_000);
    expect(sockets()).toHaveLength(3);
  });

  it('an IBKR refusal is still an error and asks again by its backoff', async () => {
    render(true);
    act(() => {
      sockets()[0].frame({ type: 'error', symbol: 'ABC', message: 'IBKR 309: max depth requests' });
      sockets()[0].close();
    });
    expect(latest?.laneWait).toBeNull();
    expect(latest?.error).toBe('IBKR 309: max depth requests');
    await wait(1_000);
    expect(sockets()).toHaveLength(2);
  });
});
