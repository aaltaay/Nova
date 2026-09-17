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

const workspace = { ibkrConnected: true };

vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => workspace,
}));

vi.mock('../constants', async () => {
  const actual = await vi.importActual<typeof import('../constants')>('../constants');
  return {
    ...actual,
    IBKR_ACCOUNT_POLL_MS: 1_000,
    IBKR_ORDERS_POLL_MS: 5_000,
    API_BASE_URL: 'http://test',
  };
});

function Probe() {
  const a = useIbkrAccountContext();
  return (
    <div data-testid="probe">
      {a.positions.length}:{a.stale ? 'stale' : 'live'}:{a.error ?? 'ok'}
    </div>
  );
}

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
    workspace.ibkrConnected = true;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.useFakeTimers();
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
          return { ok: true, json: async () => [{ symbol: 'IVF', qty: 1 }] };
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
    vi.useRealTimers();
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
    const closedCalls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.filter(
      (c: unknown[]) => String(c[0]).includes('/orders/closed'),
    );
    expect(closedCalls.length).toBe(1);
  });

  it('does not treat first paint as a disconnect', async () => {
    workspace.ibkrConnected = false;
    await act(async () => {
      root.render(
        <IbkrAccountProvider>
          <Probe />
        </IbkrAccountProvider>,
      );
    });
    expect(container.querySelector('[data-testid="probe"]')?.textContent).toBe(
      '0:live:ok',
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it('keeps last-good positions when Gateway disconnects', async () => {
    await act(async () => {
      root.render(
        <IbkrAccountProvider>
          <Probe />
        </IbkrAccountProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="probe"]')?.textContent).toBe(
      '1:live:ok',
    );

    workspace.ibkrConnected = false;
    await act(async () => {
      root.render(
        <IbkrAccountProvider>
          <Probe />
        </IbkrAccountProvider>,
      );
    });
    const text = container.querySelector('[data-testid="probe"]')?.textContent ?? '';
    expect(text.startsWith('1:stale:')).toBe(true);
    expect(text).toContain('IBKR disconnected -- last known as of');
  });

  it('polls account/positions at 1s and leaves orders/closed on the slower cadence', async () => {
    await act(async () => {
      root.render(
        <IbkrAccountProvider>
          <Probe />
        </IbkrAccountProvider>,
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const calls = () => (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map((c: unknown[]) => String(c[0]));
    const count = (needle: string) => calls().filter((u) => u.includes(needle)).length;
    expect(count('/account')).toBe(1);
    expect(count('/positions')).toBe(1);
    expect(count('/orders/closed')).toBe(1);
    expect(count('/orders')).toBe(2);

    await act(async () => {
      vi.advanceTimersByTime(1_000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(count('/account')).toBe(2);
    expect(count('/positions')).toBe(2);
    expect(count('/orders/closed')).toBe(1);

    await act(async () => {
      vi.advanceTimersByTime(1_000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(count('/account')).toBe(3);
    expect(count('/orders/closed')).toBe(1);

    await act(async () => {
      vi.advanceTimersByTime(3_000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(count('/orders/closed')).toBe(2);
    expect(count('/account')).toBeGreaterThanOrEqual(3);
  });
});
