/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  IbkrAccountProvider,
  useIbkrAccountContext,
} from './IbkrAccountContext';
import { useIbkrAccount } from './useIbkrAccount';

vi.mock('../sample_data/SampleDataContext', () => ({
  useSampleDataOptional: () => null,
}));

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ ibkrConnected: true }),
}));

vi.mock('../constants', async () => {
  const actual = await vi.importActual<typeof import('../constants')>('../constants');
  return { ...actual, IBKR_ACCOUNT_POLL_MS: 60_000, API_BASE_URL: 'http://test' };
});

function DualConsumer() {
  const a = useIbkrAccountContext();
  const b = useIbkrAccount(true);
  return (
    <div data-testid="dual">
      {a.summary?.NetLiquidation ?? 'none'}:{b.summary?.NetLiquidation ?? 'none'}:
      {a === b ? 'same' : 'diff'}
    </div>
  );
}

describe('IbkrAccountProvider', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/account')) {
          return {
            ok: true,
            json: async () => ({
              connected: true,
              mode: 'paper',
              NetLiquidation: 1000,
              BuyingPower: 900,
            }),
          };
        }
        if (String(url).includes('/positions')) {
          return { ok: true, json: async () => [] };
        }
        return { ok: true, json: async () => [] };
      }),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('serves one poll result to context and useIbkrAccount consumers', async () => {
    await act(async () => {
      root.render(
        <IbkrAccountProvider>
          <DualConsumer />
        </IbkrAccountProvider>,
      );
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const el = container.querySelector('[data-testid="dual"]');
    expect(el?.textContent).toBe('1000:1000:same');
    expect(fetch).toHaveBeenCalled();
    const accountCalls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.filter(
      (c: unknown[]) => String(c[0]).includes('/account'),
    );
    expect(accountCalls.length).toBe(1);
  });
});
