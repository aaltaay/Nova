/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
} from '../constants';
import {
  useWorkspace,
  WorkspaceProvider,
} from './WorkspaceContext';

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    enabled: true,
    connected: true,
    mode: 'paper',
    orders_enabled: false,
    spend_status: 'locked',
  }),
}));

type Snapshot = {
  selectedSymbol: string | null;
  discoveryProvider: string;
  alpacaFeed: string;
  ibkrConnected: boolean;
  setSelectedSymbol: (sym: string | null) => void;
};

let latest: Snapshot | null = null;

function Probe() {
  const ws = useWorkspace();
  latest = {
    selectedSymbol: ws.selectedSymbol,
    discoveryProvider: ws.discoveryProvider,
    alpacaFeed: ws.alpacaFeed,
    ibkrConnected: ws.ibkrConnected,
    setSelectedSymbol: ws.setSelectedSymbol,
  };
  return null;
}

describe('WorkspaceProvider', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    latest = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          discovery_provider: 'ibkr',
          data_feed: 'sip',
        }),
      })),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('exposes defaults before config resolves', () => {
    act(() => {
      root.render(
        <WorkspaceProvider>
          <Probe />
        </WorkspaceProvider>,
      );
    });
    expect(latest?.selectedSymbol).toBeNull();
    expect(latest?.discoveryProvider).toBe(DISCOVERY_PROVIDER_DEFAULT);
    expect(latest?.alpacaFeed).toBe(DATA_FEED_DEFAULT);
    expect(latest?.ibkrConnected).toBe(true);
  });

  it('loads discovery/feed from /api/config', async () => {
    act(() => {
      root.render(
        <WorkspaceProvider>
          <Probe />
        </WorkspaceProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(latest?.discoveryProvider).toBe('ibkr');
    expect(latest?.alpacaFeed).toBe('sip');
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/api\/config$/));
  });

  it('updates selectedSymbol via setSelectedSymbol', async () => {
    act(() => {
      root.render(
        <WorkspaceProvider>
          <Probe />
        </WorkspaceProvider>,
      );
    });
    await act(async () => {
      latest?.setSelectedSymbol('aapl');
    });
    expect(latest?.selectedSymbol).toBe('aapl');
    await act(async () => {
      latest?.setSelectedSymbol(null);
    });
    expect(latest?.selectedSymbol).toBeNull();
  });
});
