/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import * as prefillMod from '../ibkr/orderTicketPrefill';
import { chartOrderPrefill, chartOrderSide, stageChartOrder } from './chartOrderActions';

describe('chartOrderActions', () => {
  it('maps Webull rows onto ticket sides', () => {
    expect(chartOrderSide('buy')).toBe('BUY');
    expect(chartOrderSide('sell')).toBe('SELL');
    expect(chartOrderSide('create_order')).toBe('BUY');
  });

  it('stages a limit order at the price under the cursor', () => {
    expect(
      chartOrderPrefill({
        symbol: 'smpl',
        intent: 'sell',
        price: 4.253,
        quantityValue: '100',
      }),
    ).toEqual({
      symbol: 'SMPL',
      side: 'SELL',
      orderType: 'LMT',
      quantityValue: '100',
      limitPrice: '4.25',
    });
  });

  it('routes through the ticket prefill channel, never a place call', () => {
    const spy = vi.spyOn(prefillMod, 'requestOrderTicketPrefill');
    const staged = stageChartOrder({ symbol: 'SMPL', intent: 'buy', price: 4.25 });
    expect(spy).toHaveBeenCalledWith(staged);
    expect(staged.side).toBe('BUY');
    expect(staged.orderType).toBe('LMT');
    spy.mockRestore();
  });
});
