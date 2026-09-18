import { describe, expect, it } from 'vitest';
import {
  buildManualOrder,
  forcedManualOrderQty,
  isStopFamilyType,
  manualOrderConfirmPriceText,
  nudgeQuantityValue,
  presetsForQuantityMode,
  resolveOrderQuantity,
  type ManualOrderValues,
} from './orderEntry';

const base: ManualOrderValues = {
  symbol: 'aapl',
  side: 'BUY',
  orderType: 'MKT',
  quantityMode: 'shares',
  quantityValue: '100',
  limitPrice: '',
  stopPrice: '',
  outsideRth: false,
};

const context = {
  marketReferencePrice: 25,
  buyingPower: 10_000,
  positionQty: 200,
};

/** Free-sizing path — bypass temporary TICKER_TRADE_FORCE_QTY lock. */
const unlocked = { forceQty: null as number | null };

describe('manual order sizing', () => {
  it('does not force qty when TICKER_TRADE_FORCE_QTY is null', () => {
    expect(forcedManualOrderQty()).toBeNull();
    expect(resolveOrderQuantity(base, context)).toEqual({
      quantity: 100,
      referencePrice: 25,
    });
  });

  it('honors an explicit forceQty override', () => {
    expect(
      resolveOrderQuantity(base, context, { forceQty: 1 }),
    ).toEqual({ quantity: 1, referencePrice: 25 });
  });

  it('preserves direct share quantities when unlocked', () => {
    expect(resolveOrderQuantity(base, context, unlocked)).toEqual({
      quantity: 100,
      referencePrice: 25,
    });
  });

  it('converts dollars to fractional shares at the active price', () => {
    expect(
      resolveOrderQuantity(
        { ...base, quantityMode: 'dollars', quantityValue: '333.33' },
        context,
        unlocked,
      ),
    ).toEqual({ quantity: 13.3332, referencePrice: 25 });
  });

  it('sizes percentage buys from buying power', () => {
    expect(
      resolveOrderQuantity(
        { ...base, quantityMode: 'percent', quantityValue: '10' },
        context,
        unlocked,
      ),
    ).toEqual({ quantity: 40, referencePrice: 25 });
  });

  it('sizes percentage sells from a long position', () => {
    expect(
      resolveOrderQuantity(
        {
          ...base,
          side: 'SELL',
          quantityMode: 'percent',
          quantityValue: '25',
        },
        context,
        unlocked,
      ),
    ).toEqual({ quantity: 50, referencePrice: 25 });
  });

  it('rejects percentage sells without a long position', () => {
    expect(
      resolveOrderQuantity(
        {
          ...base,
          side: 'SELL',
          quantityMode: 'percent',
          quantityValue: '25',
        },
        { ...context, positionQty: null },
        unlocked,
      ),
    ).toEqual({ error: 'A long position is required for percentage sells' });
  });
});

describe('manual order payloads', () => {
  it('builds an extended-hours limit order from ticket qty', () => {
    const result = buildManualOrder(
      {
        ...base,
        orderType: 'LMT',
        limitPrice: '24.75',
        outsideRth: true,
      },
      context,
    );
    expect(result).toEqual({
      ok: true,
      payload: {
        symbol: 'AAPL',
        side: 'BUY',
        qty: 100,
        order_type: 'LMT',
        limit_price: 24.75,
        outside_rth: true,
      },
      quantity: 100,
      referencePrice: 24.75,
    });
  });

  it('builds a stop order with its trigger price', () => {
    const result = buildManualOrder(
      {
        ...base,
        side: 'SELL',
        orderType: 'STP',
        stopPrice: '23.5',
      },
      context,
    );
    expect(result).toMatchObject({
      ok: true,
      payload: {
        symbol: 'AAPL',
        side: 'SELL',
        qty: 100,
        order_type: 'STP',
        stop_price: 23.5,
        outside_rth: false,
      },
    });
  });

  it('builds a market order with outside_rth', () => {
    const result = buildManualOrder({ ...base, outsideRth: true }, context);
    expect(result).toEqual({
      ok: true,
      payload: {
        symbol: 'AAPL',
        side: 'BUY',
        qty: 100,
        order_type: 'MKT',
        outside_rth: true,
      },
      quantity: 100,
      referencePrice: 25,
    });
  });

  it('builds a stop-limit with both prices', () => {
    const result = buildManualOrder(
      {
        ...base,
        side: 'SELL',
        orderType: 'STP LMT',
        stopPrice: '23.5',
        limitPrice: '23.25',
      },
      context,
    );
    expect(result).toMatchObject({
      ok: true,
      payload: {
        symbol: 'AAPL',
        side: 'SELL',
        qty: 100,
        order_type: 'STP LMT',
        stop_price: 23.5,
        limit_price: 23.25,
        outside_rth: false,
      },
      referencePrice: 23.25,
    });
  });

  it('rejects stop-limit without a limit price', () => {
    const result = buildManualOrder(
      {
        ...base,
        orderType: 'STP LMT',
        stopPrice: '23.5',
        limitPrice: '',
      },
      context,
    );
    expect(result).toEqual({ ok: false, error: 'Limit price is required' });
  });

  it('builds a trailing stop with trail $ in stop_price', () => {
    const result = buildManualOrder(
      {
        ...base,
        side: 'SELL',
        orderType: 'TRAIL',
        stopPrice: '0.35',
      },
      context,
    );
    expect(result).toMatchObject({
      ok: true,
      payload: {
        symbol: 'AAPL',
        side: 'SELL',
        qty: 100,
        order_type: 'TRAIL',
        stop_price: 0.35,
        outside_rth: false,
      },
    });
  });

  it('rejects a trailing stop without a trail amount', () => {
    const result = buildManualOrder(
      {
        ...base,
        orderType: 'TRAIL',
        stopPrice: '',
      },
      context,
    );
    expect(result).toEqual({ ok: false, error: 'Trail amount is required' });
  });

  it('builds a stop order with outside_rth', () => {
    const result = buildManualOrder(
      {
        ...base,
        side: 'SELL',
        orderType: 'STP',
        stopPrice: '23.5',
        outsideRth: true,
      },
      context,
    );
    expect(result).toMatchObject({
      ok: true,
      payload: {
        symbol: 'AAPL',
        side: 'SELL',
        qty: 100,
        order_type: 'STP',
        stop_price: 23.5,
        outside_rth: true,
      },
    });
  });

  it('returns mode-specific quick-size presets', () => {
    expect(presetsForQuantityMode('shares')).toEqual([10, 50, 100, 500]);
    expect(presetsForQuantityMode('percent')).toEqual([10, 25, 50, 100]);
    expect(presetsForQuantityMode('dollars')).toEqual([100, 500, 1000, 5000]);
  });
});

describe('stop family helpers', () => {
  it('treats Stop Limit and Trailing Stop as the Stop family', () => {
    expect(isStopFamilyType('STP')).toBe(true);
    expect(isStopFamilyType('STP LMT')).toBe(true);
    expect(isStopFamilyType('TRAIL')).toBe(true);
    expect(isStopFamilyType('MKT')).toBe(false);
  });

  it('writes honest confirm price text', () => {
    expect(
      manualOrderConfirmPriceText({
        orderType: 'STP LMT',
        stopPrice: '23.5',
        limitPrice: '23.25',
      }),
    ).toBe(' stop $23.5 limit $23.25');
    expect(
      manualOrderConfirmPriceText({
        orderType: 'TRAIL',
        stopPrice: '0.35',
        limitPrice: '',
      }),
    ).toBe(' trail $0.35');
  });
});

describe('nudgeQuantityValue', () => {
  it('adds and subtracts one from a share quantity', () => {
    expect(nudgeQuantityValue('100', 1, 'shares')).toBe('101');
    expect(nudgeQuantityValue('100', -1, 'shares')).toBe('99');
  });

  it('treats empty or junk input as zero', () => {
    expect(nudgeQuantityValue('', 1, 'shares')).toBe('1');
    expect(nudgeQuantityValue('nope', -1, 'shares')).toBe('0');
  });

  it('never goes below zero and never past 100 percent', () => {
    expect(nudgeQuantityValue('0', -1, 'shares')).toBe('0');
    expect(nudgeQuantityValue('100', 1, 'percent')).toBe('100');
    expect(nudgeQuantityValue('99.5', 1, 'percent')).toBe('100');
  });
});
