import { describe, expect, it } from 'vitest';
import {
  buildManualOrder,
  forcedManualOrderQty,
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
  it('forces share qty from TICKER_TRADE_FORCE_QTY by default (SSOT)', () => {
    const forced = forcedManualOrderQty();
    expect(forced).toBe(1);
    expect(resolveOrderQuantity(base, context)).toEqual({
      quantity: 1,
      referencePrice: 25,
    });
    expect(
      resolveOrderQuantity(
        { ...base, quantityMode: 'dollars', quantityValue: '9999' },
        context,
      ),
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
  it('builds an extended-hours limit order with forced qty 1', () => {
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
        qty: 1,
        order_type: 'LMT',
        limit_price: 24.75,
        outside_rth: true,
      },
      quantity: 1,
      referencePrice: 24.75,
    });
  });

  it('builds a stop order with its trigger price (forced qty 1)', () => {
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
        qty: 1,
        order_type: 'STP',
        stop_price: 23.5,
        outside_rth: false,
      },
    });
  });

  it('rejects extended-hours market and stop orders', () => {
    const result = buildManualOrder(
      { ...base, outsideRth: true },
      context,
    );
    expect(result).toEqual({
      ok: false,
      error: 'Extended hours supports Limit orders only',
    });
  });

  it('returns mode-specific quick-size presets', () => {
    expect(presetsForQuantityMode('shares')).toEqual([10, 50, 100, 500]);
    expect(presetsForQuantityMode('percent')).toEqual([10, 25, 50, 100]);
    expect(presetsForQuantityMode('dollars')).toEqual([100, 500, 1000, 5000]);
  });
});
