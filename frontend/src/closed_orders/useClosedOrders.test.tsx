/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useClosedOrders } from './useClosedOrders';

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
});
