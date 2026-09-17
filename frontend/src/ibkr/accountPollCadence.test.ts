import { describe, expect, it } from 'vitest';
import { IBKR_ACCOUNT_POLL_MS, IBKR_ORDERS_POLL_MS } from '../constantGroups/global_bar';

describe('IBKR account cluster cadence (#182)', () => {
  it('refreshes Day P&L / Net Liq / BP / positions at most 1s while Gateway is up', () => {
    expect(IBKR_ACCOUNT_POLL_MS).toBeLessThanOrEqual(1_000);
    expect(IBKR_ACCOUNT_POLL_MS).toBeGreaterThan(0);
  });

  it('keeps orders/closed slower so the 1s cluster poll does not hammer IBKR', () => {
    expect(IBKR_ORDERS_POLL_MS).toBeGreaterThanOrEqual(5_000);
    expect(IBKR_ORDERS_POLL_MS).toBeGreaterThan(IBKR_ACCOUNT_POLL_MS);
  });
});
