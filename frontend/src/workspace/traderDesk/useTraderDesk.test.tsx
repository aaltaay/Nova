/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
});
