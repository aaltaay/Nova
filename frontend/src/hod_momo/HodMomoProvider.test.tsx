/**
 * @vitest-environment jsdom
 *
 * The 04:00 ET rollover on the shared HOD Momo stream (#800): the Scanner's
 * HOD Momo / Running Up lists and counts and the Trader's Focus rail all read
 * this provider. A Sim desk off the live edge keeps its playhead's history while
 * the live list underneath is replaced; back at the edge it shows the new session.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOD_MOMO_ALERT_BATCH_MS } from '../constants';
import { useHodMomo } from './HodMomoContext';
import { HodMomoProvider } from './HodMomoProvider';
import type { AlertObject } from './types';
import type { HodMomoReplay } from './useHodMomoReplay';

const mocks = vi.hoisted(() => ({ replay: null as HodMomoReplay | null }));

vi.mock('../sim/useSimReplayDesk', () => ({ useSimReplayDesk: () => mocks.replay != null }));
vi.mock('./useHodMomoReplay', () => ({ useHodMomoReplay: () => mocks.replay }));
vi.mock('./useHodMomoConfig', () => ({
  useHodMomoConfig: () => ({
    state: { loaded: false, strategies: {}, master: {} },
    updateStrategy: () => {},
    updateMaster: () => {},
    resetStrategy: async () => {},
    resetAll: async () => {},
  }),
}));

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

const RUNNING_UP = 12;
const LOW_FLOAT = 7;

function hodAlert(id: string, ticker: string, strategyId: number): AlertObject {
  return {
    id, ticker, timestamp: '2026-10-19T08:00:05Z', created_ts: 1_792_396_805, strategy_id: strategyId,
    strategy_name: strategyId === RUNNING_UP ? 'Running Up Alert' : 'Low Float - High Rel Vol',
    price: 4.2, change_pct: 12, rvol: 8, float_shares: 1_000_000, gap_pct: null, volume: 200_000,
    momentum_pct: null, rvol_source: 'ibkr', consolidation_count: 1, consolidated_ids: [],
  };
}

let seen: { ids: string[]; hod: number; runningUp: number; replaying: boolean } | null = null;

function Probe() {
  const { stream, hodCount, runningUpCount, replay } = useHodMomo();
  seen = { ids: stream.alerts.map(a => a.id), hod: hodCount, runningUp: runningUpCount, replaying: replay != null };
  return null;
}

function send(ws: FakeWebSocket, payload: unknown) {
  ws.onmessage?.({ data: JSON.stringify(payload) });
}

describe('HodMomoProvider at the 04:00 rollover', () => {
  let container: HTMLDivElement;
  let root: Root;
  const mount = () => act(() => root.render(<HodMomoProvider><Probe /></HodMomoProvider>));

  beforeEach(() => {
    FakeWebSocket.instances = [];
    mocks.replay = null;
    seen = null;
    localStorage.clear();
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.useFakeTimers();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    mount();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('a Sim desk off the live edge keeps its playhead list; back at the edge it shows the new session', () => {
    const ws = FakeWebSocket.instances[0];
    act(() => send(ws, {
      type: 'initial', alerts: [hodAlert('fri-hod', 'OLDA', LOW_FLOAT), hodAlert('fri-up', 'OLDB', RUNNING_UP)], total: 2,
    }));
    expect(seen).toEqual({ ids: ['fri-hod', 'fri-up'], hod: 1, runningUp: 1, replaying: false });

    // Off the live edge the lists show the playhead's history.
    mocks.replay = {
      state: {
        date: '2026-10-16', minute: 1_792_180_800, loading: false, error: null, recorded: true, source: 'recorded',
        rebuild: null,
      },
      alerts: [hodAlert('past', 'PAST', LOW_FLOAT)],
    };
    mount();
    expect(seen).toEqual({ ids: ['past'], hod: 1, runningUp: 0, replaying: true });

    // 04:00 rolls on the live socket underneath, then Monday's first alert arrives.
    act(() => send(ws, { type: 'initial', alerts: [], total: 0 }));
    act(() => send(ws, { type: 'alert', alert: hodAlert('mon-up', 'NEW', RUNNING_UP) }));
    act(() => { vi.advanceTimersByTime(HOD_MOMO_ALERT_BATCH_MS * 2); });
    expect(seen).toEqual({ ids: ['past'], hod: 1, runningUp: 0, replaying: true });

    // Back at the live edge: Monday's list and counts, nothing of Friday's.
    mocks.replay = null;
    mount();
    expect(seen).toEqual({ ids: ['mon-up'], hod: 0, runningUp: 1, replaying: false });
  });

  it('a live desk replaces its rows and counts at the rollover', () => {
    const ws = FakeWebSocket.instances[0];
    act(() => send(ws, {
      type: 'initial', alerts: [hodAlert('fri-hod', 'OLDA', LOW_FLOAT), hodAlert('fri-up', 'OLDB', RUNNING_UP)], total: 2,
    }));
    act(() => send(ws, { type: 'alert', alert: hodAlert('fri-late', 'OLDC', LOW_FLOAT) }));
    act(() => send(ws, { type: 'initial', alerts: [], total: 0 }));
    act(() => { vi.advanceTimersByTime(HOD_MOMO_ALERT_BATCH_MS * 2); });
    expect(seen).toEqual({ ids: [], hod: 0, runningUp: 0, replaying: false });
  });
});
