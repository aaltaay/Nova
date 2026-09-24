/**
 * @vitest-environment jsdom
 *
 * QA C32: one bare NaN in the `initial` frame (Python json.dumps) used to hide
 * the whole day's alerts behind "No alerts yet" beside FEED LIVE.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useHodMomoStream } from './useHodMomoStream';

// Live desk: the stream asks whether Sim is replaying (#486); no IBKR status poller here.
vi.mock('../sim/useSimReplayDesk', () => ({ useSimReplayDesk: () => false }));

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
  }
}

let latest: ReturnType<typeof useHodMomoStream> | null = null;

function Harness() {
  latest = useHodMomoStream();
  return null;
}

const RAW_ALERT = (id: string, created: number) =>
  `{"id":"${id}","timestamp":"2026-09-22T02:29:05.000Z","ticker":"VEEE","strategy_id":12,`
  + `"strategy_name":"Running Up Alert","price":16.95,"change_pct":null,"rvol":NaN,"float_shares":null,`
  + `"gap_pct":null,"volume":null,"momentum_pct":null,"rvol_source":null,"consolidation_count":1,`
  + `"consolidated_ids":[],"created_ts":${created}}`;

describe('useHodMomoStream reads a NaN frame (QA C32)', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    FakeWebSocket.instances = [];
    latest = null;
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<Harness />);
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('keeps the day when one alert carries NaN, and drops exact repeats', () => {
    const ws = FakeWebSocket.instances[0];
    const frame = `{"type":"initial","alerts":[${RAW_ALERT('a', 1790046256.1)},${RAW_ALERT('a', 1790046256.1)},`
      + `${RAW_ALERT('a', 1790046029.8)}],"total":3}`;
    act(() => ws.onmessage?.({ data: frame }));
    expect(latest?.alerts).toHaveLength(2);
    expect(latest?.alerts[0].rvol).toBeNull();
    expect(latest?.feedError ?? null).toBeNull();
  });

  it('states a frame it cannot read instead of an empty strip', () => {
    const ws = FakeWebSocket.instances[0];
    act(() => ws.onmessage?.({ data: '{"type":"initial","alerts":[' }));
    expect(latest?.alerts).toEqual([]);
    expect(latest?.feedError).toMatch(/unreadable/);
  });
});
