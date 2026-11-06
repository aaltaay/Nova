/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOD_MOMO_ALERT_BATCH_MS } from '../constants';
import {
  noteHodMomoLiveAlert,
  rememberHodMomoAlertSnapshot,
  resetHodMomoAlertSoundForTests,
  setHodMomoAlertSoundEnabled,
} from './hodMomoAlertSound';
import { subscribeHodMomoLiveAlerts } from './hodMomoLiveAlerts';
import { useHodMomoStream } from './useHodMomoStream';

const mocks = vi.hoisted(() => ({ replayDesk: false, ping: vi.fn() }));

vi.mock('../sim/useSimReplayDesk', () => ({ useSimReplayDesk: () => mocks.replayDesk }));

vi.mock('./hodMomoAlertSound', async () => {
  const actual = await vi.importActual<typeof import('./hodMomoAlertSound')>(
    './hodMomoAlertSound',
  );
  return {
    ...actual,
    noteHodMomoLiveAlert: vi.fn(actual.noteHodMomoLiveAlert),
    rememberHodMomoAlertSnapshot: vi.fn(actual.rememberHodMomoAlertSnapshot),
  };
});

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

const shownIds = () => latest?.alerts.map(alert => alert.id);

function send(ws: FakeWebSocket, payload: unknown) {
  ws.onmessage?.({ data: JSON.stringify(payload) });
}

function hodAlert(id: string, ticker = 'ABCD') {
  return {
    id,
    timestamp: '2026-09-18T10:00:00Z',
    ticker,
    strategy_id: 7,
    strategy_name: 'Low Float - High Rel Vol',
    price: 4.2,
    change_pct: 12,
    rvol: 8,
    float_shares: 1_000_000,
    gap_pct: 9,
    volume: 200_000,
    momentum_pct: 5,
    rvol_source: 'ibkr',
    consolidation_count: 1,
    consolidated_ids: [id],
  };
}

describe('useHodMomoStream alert ping', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    FakeWebSocket.instances = [];
    localStorage.clear();
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.stubGlobal(
      'AudioContext',
      class {
        currentTime = 0;
        state = 'running';
        destination = {};
        resume() {}
        createOscillator() {
          return {
            connect() {},
            frequency: { value: 0 },
            start: mocks.ping,
            stop() {},
          };
        }
        createGain() {
          return {
            connect() {},
            gain: { value: 0, exponentialRampToValueAtTime() {} },
          };
        }
      },
    );
    resetHodMomoAlertSoundForTests();
    mocks.replayDesk = false;
    mocks.ping.mockClear();
    vi.mocked(noteHodMomoLiveAlert).mockClear();
    vi.mocked(rememberHodMomoAlertSnapshot).mockClear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<Harness />);
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
    localStorage.clear();
    resetHodMomoAlertSoundForTests();
  });

  it('pings a live HOD row, skips snapshot replay and muted / duplicate live ids', () => {
    const ws = FakeWebSocket.instances[0];
    const existing = hodAlert('snap-1', 'OLD');
    act(() => {
      send(ws, { type: 'initial', alerts: [existing], total: 1 });
    });
    expect(rememberHodMomoAlertSnapshot).toHaveBeenCalledWith([existing]);
    expect(noteHodMomoLiveAlert).not.toHaveBeenCalled();

    act(() => {
      send(ws, { type: 'alert', alert: hodAlert('live-1', 'NEW1') });
    });
    expect(noteHodMomoLiveAlert).toHaveBeenCalledTimes(1);

    act(() => {
      send(ws, { type: 'alert', alert: hodAlert('live-1', 'NEW1') });
    });
    expect(noteHodMomoLiveAlert).toHaveBeenCalledTimes(1);

    setHodMomoAlertSoundEnabled(false);
    act(() => {
      send(ws, { type: 'alert', alert: hodAlert('live-2', 'NEW2') });
    });
    expect(noteHodMomoLiveAlert).toHaveBeenCalledTimes(2);
    expect(vi.mocked(noteHodMomoLiveAlert).mock.results[1]?.value).toBe('muted');

    act(() => {
      send(ws, { type: 'initial', alerts: [existing, hodAlert('live-1', 'NEW1')], total: 2 });
    });
    expect(noteHodMomoLiveAlert).toHaveBeenCalledTimes(2);
  });

  it('stays silent while Sim replays, pings new live alerts at the live edge, never late (#486)', () => {
    const ws = FakeWebSocket.instances[0];
    act(() => {
      send(ws, { type: 'initial', alerts: [], total: 0 });
    });

    mocks.replayDesk = true;
    act(() => {
      root.render(<Harness />);
    });
    act(() => {
      send(ws, { type: 'alert', alert: hodAlert('during-replay', 'PAST') });
    });
    expect(noteHodMomoLiveAlert).toHaveBeenCalledTimes(1);
    expect(vi.mocked(noteHodMomoLiveAlert).mock.results[0]?.value).toBe('replaying');
    expect(mocks.ping).not.toHaveBeenCalled();

    mocks.replayDesk = false;
    act(() => {
      root.render(<Harness />);
    });
    // The alert heard while replaying is seen: back at the edge a re-send never pings late.
    act(() => {
      send(ws, { type: 'alert', alert: hodAlert('during-replay', 'PAST') });
    });
    expect(mocks.ping).not.toHaveBeenCalled();

    act(() => {
      send(ws, { type: 'alert', alert: hodAlert('at-edge', 'NOW') });
    });
    expect(vi.mocked(noteHodMomoLiveAlert).mock.results.at(-1)?.value).toBe('pinged');
    expect(mocks.ping).toHaveBeenCalledTimes(1);
  });

  it('a second initial frame on one socket replaces the list: batch dropped, count reset, no ping or toast (#800)', () => {
    vi.useFakeTimers();
    const toasts = vi.fn();
    const unsubscribe = subscribeHodMomoLiveAlerts(toasts);
    try {
      const ws = FakeWebSocket.instances[0];
      act(() => send(ws, { type: 'initial', alerts: [hodAlert('fri-1', 'OLDA'), hodAlert('fri-2', 'OLDB')], total: 2 }));
      expect(shownIds()).toEqual(['fri-1', 'fri-2']);
      expect(latest?.totalToday).toBe(2);

      // A Friday alert still waits in the batch when the 04:00 rollover restates the list.
      act(() => send(ws, { type: 'alert', alert: hodAlert('fri-3', 'OLDC') }));
      expect(toasts).toHaveBeenCalledTimes(1);
      expect(mocks.ping).toHaveBeenCalledTimes(1);
      act(() => send(ws, { type: 'initial', alerts: [], total: 0 }));
      expect(shownIds()).toEqual([]);
      expect(latest?.totalToday).toBe(0);
      act(() => { vi.advanceTimersByTime(HOD_MOMO_ALERT_BATCH_MS * 4); });
      expect(shownIds()).toEqual([]);
      expect(latest?.totalToday).toBe(0);

      // A snapshot never pings or toasts, even for an alert this desk never saw.
      act(() => send(ws, { type: 'initial', alerts: [hodAlert('mon-0', 'SNAP')], total: 1 }));
      expect(shownIds()).toEqual(['mon-0']);
      act(() => send(ws, { type: 'initial', alerts: [], total: 0 }));
      expect(noteHodMomoLiveAlert).toHaveBeenCalledTimes(1);
      expect(mocks.ping).toHaveBeenCalledTimes(1);
      expect(toasts).toHaveBeenCalledTimes(1);

      // Monday's first alert behaves as any fresh one: one row, one ping, one toast; a re-send adds nothing.
      act(() => { vi.advanceTimersByTime(1_000); });
      act(() => send(ws, { type: 'alert', alert: hodAlert('mon-1', 'NEW') }));
      act(() => send(ws, { type: 'alert', alert: hodAlert('mon-1', 'NEW') }));
      act(() => { vi.advanceTimersByTime(HOD_MOMO_ALERT_BATCH_MS * 2); });
      expect(shownIds()).toEqual(['mon-1']);
      expect(latest?.totalToday).toBe(1);
      expect(mocks.ping).toHaveBeenCalledTimes(2);
      expect(toasts).toHaveBeenCalledTimes(2);
      expect(toasts).toHaveBeenLastCalledWith(expect.objectContaining({ id: 'mon-1' }));

      // Restated with it (as on a reconnect), then sent once more: still one row, no second ping or toast.
      act(() => send(ws, { type: 'initial', alerts: [hodAlert('mon-1', 'NEW')], total: 1 }));
      act(() => send(ws, { type: 'alert', alert: hodAlert('mon-1', 'NEW') }));
      act(() => { vi.advanceTimersByTime(HOD_MOMO_ALERT_BATCH_MS * 2); });
      expect(shownIds()).toEqual(['mon-1']);
      expect(latest?.totalToday).toBe(1);
      expect(mocks.ping).toHaveBeenCalledTimes(2);
      expect(toasts).toHaveBeenCalledTimes(2);
    } finally {
      unsubscribe();
      vi.useRealTimers();
    }
  });
});
