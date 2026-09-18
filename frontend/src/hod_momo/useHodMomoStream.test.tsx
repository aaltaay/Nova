/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOD_MOMO_ALERT_BATCH_MS } from '../constants';
import * as ping from './hodMomoAlertPing';
import { useHodMomoStream } from './useHodMomoStream';

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

  send() {}
}

function Harness({ onValue }: { onValue: (state: ReturnType<typeof useHodMomoStream>) => void }) {
  const state = useHodMomoStream();
  onValue(state);
  return null;
}

function send(ws: FakeWebSocket, payload: unknown) {
  ws.onmessage?.({ data: JSON.stringify(payload) });
}

describe('useHodMomoStream alert ping wiring', () => {
  let container: HTMLDivElement;
  let root: Root;
  let snapshotSpy: ReturnType<typeof vi.spyOn>;
  let arrivalsSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    FakeWebSocket.instances = [];
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.useFakeTimers();
    ping.resetHodMomoAlertPingForTests();
    snapshotSpy = vi.spyOn(ping, 'ingestHodMomoAlertSnapshot');
    arrivalsSpy = vi.spyOn(ping, 'ingestHodMomoAlertArrivals');
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    snapshotSpy.mockRestore();
    arrivalsSpy.mockRestore();
    ping.resetHodMomoAlertPingForTests();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('seeds snapshot on initial and pings only a live new HOD row', async () => {
    act(() => {
      root.render(<Harness onValue={() => undefined} />);
    });
    const ws = FakeWebSocket.instances[0];
    expect(ws).toBeTruthy();

    act(() => {
      send(ws, {
        type: 'initial',
        alerts: [
          {
            id: 'seed-1',
            ticker: 'SEED',
            timestamp: '2026-09-18T13:00:00.000Z',
            strategy_id: 7,
          },
        ],
        total: 1,
      });
    });
    expect(snapshotSpy).toHaveBeenCalledTimes(1);
    expect(arrivalsSpy).not.toHaveBeenCalled();

    act(() => {
      send(ws, {
        type: 'alert',
        alert: {
          id: 'live-1',
          ticker: 'NEWT',
          timestamp: '2026-09-18T13:01:00.000Z',
          strategy_id: 7,
        },
      });
      send(ws, {
        type: 'alert',
        alert: {
          id: 'seed-1',
          ticker: 'SEED',
          timestamp: '2026-09-18T13:00:00.000Z',
          strategy_id: 7,
        },
      });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HOD_MOMO_ALERT_BATCH_MS);
    });
    expect(arrivalsSpy).toHaveBeenCalledTimes(1);
    const batch = arrivalsSpy.mock.calls[0][0];
    expect(batch).toHaveLength(1);
    expect(batch[0].id).toBe('live-1');
  });
});
