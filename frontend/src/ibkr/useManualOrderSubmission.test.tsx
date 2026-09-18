/**
 * @vitest-environment jsdom
 *
 * One idempotency key per Submit gesture, and no same-tick double place.
 * The `submitting` state lands a render late, so it cannot guard on its own.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const placeIbkrOrder = vi.fn();

vi.mock('./placeOrder', () => ({
  placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args),
}));
vi.mock('./notifyOrderRejected', () => ({
  notifyOrderRejected: vi.fn(),
}));
let skipConfirm = true;
vi.mock('./placeConfirmPrefs', () => ({
  readSkipPlaceConfirm: () => skipConfirm,
}));

import { useManualOrderSubmission } from './useManualOrderSubmission';

function params() {
  return {
    symbol: 'AAPL',
    mode: 'paper' as const,
    connected: true,
    spendLocked: false,
    needsPinUnlock: false,
    side: 'BUY' as const,
    shortEntry: false,
    shortBlockReason: null,
    orderType: 'MKT' as const,
    quantityMode: 'shares' as const,
    quantityValue: '10',
    limitPrice: '',
    stopPrice: '',
    outsideRth: false,
    referencePrice: 10,
    summary: { BuyingPower: 100000 } as never,
    position: null,
    onNeedsPin: () => undefined,
  };
}

describe('useManualOrderSubmission gesture identity', () => {
  beforeEach(() => {
    skipConfirm = true;
    placeIbkrOrder.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 7, error: null });
  });

  it('places once when Submit fires twice inside one tick', async () => {
    const { result } = renderHook(() => useManualOrderSubmission(params()));
    await act(async () => {
      await Promise.all([
        result.current.executeOrder(),
        result.current.executeOrder(),
      ]);
    });
    expect(placeIbkrOrder).toHaveBeenCalledTimes(1);
  });

  it('carries one key from Submit through a double-clicked Confirm', async () => {
    skipConfirm = false;
    const { result } = renderHook(() => useManualOrderSubmission(params()));
    await act(async () => {
      result.current.submit({ preventDefault: () => undefined } as never);
    });
    expect(placeIbkrOrder).not.toHaveBeenCalled();
    expect(result.current.confirmSummary).toBeTruthy();

    await act(async () => {
      await Promise.all([
        result.current.executeOrder(),
        result.current.executeOrder(),
      ]);
    });
    expect(placeIbkrOrder).toHaveBeenCalledTimes(1);
    const key = placeIbkrOrder.mock.calls[0][1];
    expect(typeof key).toBe('string');
    expect(key).toMatch(/^manual:/);
  });

  it('confirm copy says SHORT when short_entry is set', async () => {
    skipConfirm = false;
    const { result } = renderHook(() =>
      useManualOrderSubmission({
        ...params(),
        side: 'SELL',
        shortEntry: true,
        symbol: 'NVDA',
      }),
    );
    await act(async () => {
      result.current.submit({ preventDefault: () => undefined } as never);
    });
    expect(result.current.confirmSummary).toMatch(/^SHORT 10 NVDA /);
    expect(result.current.confirmSummary).not.toMatch(/^SELL /);
  });

  it('forwards outside_rth true from the ticket checkbox', async () => {
    const { result } = renderHook(() =>
      useManualOrderSubmission({ ...params(), outsideRth: true }),
    );
    await act(async () => {
      await result.current.executeOrder();
    });
    expect(placeIbkrOrder.mock.calls[0][0].outside_rth).toBe(true);
  });

  it('forwards outside_rth false when Extended Hours is unchecked', async () => {
    const { result } = renderHook(() =>
      useManualOrderSubmission({ ...params(), outsideRth: false }),
    );
    await act(async () => {
      await result.current.executeOrder();
    });
    expect(placeIbkrOrder.mock.calls[0][0].outside_rth).toBe(false);
  });

  it('mints a fresh key for the next gesture', async () => {
    const { result } = renderHook(() => useManualOrderSubmission(params()));
    await act(async () => {
      await result.current.executeOrder();
    });
    await act(async () => {
      await result.current.executeOrder();
    });
    expect(placeIbkrOrder).toHaveBeenCalledTimes(2);
    expect(placeIbkrOrder.mock.calls[0][1]).not.toBe(
      placeIbkrOrder.mock.calls[1][1],
    );
  });
});
