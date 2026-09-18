/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  noteHodMomoLiveAlert,
  rememberHodMomoAlertSnapshot,
  resetHodMomoAlertSoundForTests,
  setHodMomoAlertSoundEnabled,
} from './hodMomoAlertSound';
import { useHodMomoStream } from './useHodMomoStream';

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

function Harness() {
  useHodMomoStream();
  return null;
}

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
            start() {},
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
});
