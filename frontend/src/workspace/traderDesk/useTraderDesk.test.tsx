/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { requestOpenOnDesk } from './openRequest';
import { TRADER_DESK_STORAGE_KEY } from './protocol';
import { useTraderDesk } from './useTraderDesk';

type Fan = {
  name: string;
  handler: ((ev: MessageEvent) => void) | null;
  postMessage: (data: unknown) => void;
  addEventListener: (type: string, fn: (ev: MessageEvent) => void) => void;
  removeEventListener: () => void;
  close: () => void;
};

function installFanChannel() {
  const rooms = new Map<string, Fan[]>();
  class FanChannel {
    name: string;
    handler: Fan['handler'] = null;
    constructor(name: string) {
      this.name = name;
      const list = rooms.get(name) ?? [];
      list.push(this);
      rooms.set(name, list);
    }
    postMessage(data: unknown) {
      for (const peer of rooms.get(this.name) ?? []) {
        if (peer !== this) peer.handler?.({ data } as MessageEvent);
      }
    }
    addEventListener(_type: string, fn: (ev: MessageEvent) => void) {
      this.handler = fn;
    }
    removeEventListener() {
      this.handler = null;
    }
    close() {
      const list = (rooms.get(this.name) ?? []).filter((c) => c !== this);
      rooms.set(this.name, list);
    }
  }
  vi.stubGlobal('BroadcastChannel', FanChannel);
}

type DeskApi = ReturnType<typeof useTraderDesk>;

function Probe(props: Parameters<typeof useTraderDesk>[0] & { onReady: (api: DeskApi) => void }) {
  const { onReady, ...deskProps } = props;
  const api = useTraderDesk(deskProps);
  onReady(api);
  return null;
}

describe('useTraderDesk', () => {
  let hostEl: HTMLDivElement;
  let floatEl: HTMLDivElement;
  let hostRoot: Root;
  let floatRoot: Root;
  let hostDesk: DeskApi | null;
  let floatDesk: DeskApi | null;

  beforeEach(() => {
    installFanChannel();
    hostDesk = null;
    floatDesk = null;
    hostEl = document.createElement('div');
    floatEl = document.createElement('div');
    document.body.append(hostEl, floatEl);
    hostRoot = createRoot(hostEl);
    floatRoot = createRoot(floatEl);
  });

  afterEach(() => {
    act(() => {
      hostRoot.unmount();
      floatRoot.unmount();
    });
    hostEl.remove();
    floatEl.remove();
    vi.unstubAllGlobals();
  });

  it('docks a float tab into the host over the desk bus', async () => {
    const gave = vi.fn();
    const accepted: string[] = [];
    await act(async () => {
      hostRoot.render(
        <Probe
          windowId="host-1"
          role="host"
          onDockRequest={(symbol) => {
            accepted.push(symbol);
            return true;
          }}
          onGaveTab={vi.fn()}
          onReady={(api) => {
            hostDesk = api;
          }}
        />,
      );
      floatRoot.render(
        <Probe
          windowId="float-1"
          role="float"
          onDockRequest={() => false}
          onGaveTab={gave}
          onReady={(api) => {
            floatDesk = api;
          }}
        />,
      );
    });
    await act(async () => {
      floatDesk?.requestDock('IPST');
    });
    expect(accepted).toEqual(['IPST']);
    expect(gave).toHaveBeenCalledWith('IPST');
    expect(hostDesk).toBeTruthy();
    expect(localStorage.getItem(TRADER_DESK_STORAGE_KEY)).toMatch(/dock-request|tab-docked/);
  });

  it('opens a symbol in the host for a window that is not a desk (the Top 9 pop-up)', async () => {
    localStorage.clear();
    const hostOpened = vi.fn(() => true);
    const floatOpened = vi.fn(() => true);
    await act(async () => {
      hostRoot.render(
        <Probe windowId="host-1" role="host" onDockRequest={() => false} onOpenRequest={hostOpened}
          onGaveTab={vi.fn()} onReady={() => {}} />,
      );
      floatRoot.render(
        <Probe windowId="float-1" role="float" onDockRequest={() => false} onOpenRequest={floatOpened}
          onGaveTab={vi.fn()} onReady={() => {}} />,
      );
    });
    let ok: boolean | null = null;
    await act(async () => {
      ok = await requestOpenOnDesk('ztg', { from: 'gainers', waitMs: 300 });
    });
    expect(ok).toBe(true);
    expect(hostOpened).toHaveBeenCalledTimes(1);
    expect(hostOpened.mock.calls[0]).toEqual(['ZTG', expect.any(String), 'gainers']);
    // A float never opens tabs for another window: only the host takes the request.
    expect(floatOpened).not.toHaveBeenCalled();
  });

  it('says no desk answered when there is no host window', async () => {
    localStorage.clear();
    let ok: boolean | null = null;
    await act(async () => {
      ok = await requestOpenOnDesk('ZTG', { from: 'gainers', waitMs: 50 });
    });
    expect(ok).toBe(false);
  });
});
