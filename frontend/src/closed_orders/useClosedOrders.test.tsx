/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useClosedOrders } from './useClosedOrders';
import type { IbkrAccountState } from '../ibkr/IbkrAccountContext';
import type { ClosedOrder } from './types';

const ctxRef: { current: IbkrAccountState | null } = { current: null };

vi.mock('../ibkr/IbkrAccountContext', () => ({
  useOptionalIbkrAccountContext: () => ctxRef.current,
}));

// The desk's shared status poll is not this hook's request; Live unless a test says otherwise.
const statusRef: { current: { mode: string; venue?: string; stale?: boolean } } = { current: { mode: 'live', venue: 'live' } };
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => statusRef.current }));

function Probe({ connected }: { connected: boolean }) {
  const { orders, error } = useClosedOrders(connected);
  return (
    <div data-testid="closed-probe">
      {orders.length}:{error ?? 'ok'}
    </div>
  );
}

describe('useClosedOrders', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    ctxRef.current = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => [{ order_id: 19112, symbol: 'IVF', status: 'Filled' }],
      })),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('keeps last-good closed orders when disconnected', async () => {
    await act(async () => {
      root.render(<Probe connected />);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="closed-probe"]')?.textContent).toBe(
      '1:ok',
    );

    await act(async () => {
      root.render(<Probe connected={false} />);
    });
    const text = container.querySelector('[data-testid="closed-probe"]')?.textContent ?? '';
    expect(text.startsWith('1:')).toBe(true);
    expect(text).toContain('IBKR disconnected -- last known as of');
  });

  it('reads closed orders from the account context and does not poll', async () => {
    ctxRef.current = {
      summary: null,
      positions: [],
      orders: [],
      closedOrders: [{ order_id: 7, symbol: 'DAIC', status: 'Filled' } as ClosedOrder],
      loading: false,
      error: null,
      stale: false,
      staleSince: null,
      refresh: () => {},
    };
    await act(async () => {
      root.render(<Probe connected />);
    });
    expect(container.querySelector('[data-testid="closed-probe"]')?.textContent).toBe(
      '1:ok',
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it('on Paper a down Gateway is not "last known": the practice ledger still answers (C68)', async () => {
    statusRef.current = { mode: 'paper', venue: 'paper', stale: false };
    try {
      await act(async () => {
        root.render(<Probe connected={false} />);
      });
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
      expect(container.querySelector('[data-testid="closed-probe"]')?.textContent).toBe('1:ok');
    } finally {
      statusRef.current = { mode: 'live', venue: 'live' };
    }
  });

  it('a list that is not a list is a named failure, never a crash (C3)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })));
    await act(async () => {
      root.render(<Probe connected />);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="closed-probe"]')?.textContent).toBe(
      '0:closed orders unavailable (unexpected shape)',
    );
  });
});
