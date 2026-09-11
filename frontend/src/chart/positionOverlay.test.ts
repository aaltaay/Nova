import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import type { IbkrOrder, IbkrPosition } from '../ibkr/types';
import { isoToEtTime } from '../tickerChartData';
import { buildSeriesTimeIndex } from './chartDrawingTime';
import {
  CHART_POSITION_LONG_COLOR,
  CHART_POSITION_SHORT_COLOR,
} from './positionOverlayConstants';
import {
  fillsFromOrders,
  findOpenPosition,
  mergeFills,
  positionLineTitle,
  positionPriceLineOptions,
  seriesMarkersForFills,
} from './positionOverlay';

function pos(partial: Partial<IbkrPosition> & Pick<IbkrPosition, 'symbol' | 'qty'>): IbkrPosition {
  return {
    market_price: null,
    market_value: null,
    avg_cost: null,
    unrealized_pnl: null,
    realized_pnl: null,
    ...partial,
  };
}

function order(
  partial: Partial<IbkrOrder> & Pick<IbkrOrder, 'order_id' | 'symbol' | 'side'>,
): IbkrOrder {
  return {
    qty: 1,
    order_type: 'MKT',
    limit_price: null,
    status: 'Filled',
    ...partial,
  };
}

describe('findOpenPosition', () => {
  it('returns the matching open row for the chart symbol', () => {
    const found = findOpenPosition(
      [
        pos({ symbol: 'spy', qty: 2, avg_cost: 400 }),
        pos({ symbol: 'FTFT', qty: 1, avg_cost: 2.76, unrealized_pnl: 0.3 }),
      ],
      'ftft',
    );
    expect(found).toEqual({
      symbol: 'FTFT',
      qty: 1,
      avgCost: 2.76,
      unrealizedPnl: 0.3,
    });
  });

  it('ignores a flat row, a missing avg cost, and a different symbol', () => {
    expect(findOpenPosition([pos({ symbol: 'FTFT', qty: 0, avg_cost: 2 })], 'FTFT')).toBeNull();
    expect(findOpenPosition([pos({ symbol: 'FTFT', qty: 1, avg_cost: null })], 'FTFT')).toBeNull();
    expect(findOpenPosition([pos({ symbol: 'AAPL', qty: 1, avg_cost: 190 })], 'FTFT')).toBeNull();
  });
});

describe('positionLineTitle', () => {
  it('shows long qty, avg cost, and signed P/L', () => {
    expect(positionLineTitle({
      symbol: 'FTFT',
      qty: 1,
      avgCost: 2.76,
      unrealizedPnl: 0.3,
    })).toBe('Long 1 @ $2.76  +$0.30');
  });

  it('labels a short and omits P/L when mark is unknown', () => {
    expect(positionLineTitle({
      symbol: 'XYZ',
      qty: -10,
      avgCost: 5,
      unrealizedPnl: null,
    })).toBe('Short 10 @ $5.00');
  });
});

describe('positionPriceLineOptions', () => {
  it('paints a long at avg cost in the long color', () => {
    const line = positionPriceLineOptions({
      symbol: 'FTFT',
      qty: 1,
      avgCost: 2.76,
      unrealizedPnl: 0.3,
    });
    expect(line.price).toBe(2.76);
    expect(line.color).toBe(CHART_POSITION_LONG_COLOR);
    expect(line.axisLabelVisible).toBe(true);
    expect(line.title).toContain('$2.76');
  });

  it('paints a short in the short color', () => {
    const line = positionPriceLineOptions({
      symbol: 'XYZ',
      qty: -4,
      avgCost: 11.5,
      unrealizedPnl: -1,
    });
    expect(line.color).toBe(CHART_POSITION_SHORT_COLOR);
    expect(line.price).toBe(11.5);
  });
});

describe('fillsFromOrders / mergeFills', () => {
  it('keeps filled buys and sells that have a price and a fill time', () => {
    const fills = fillsFromOrders([
      order({
        order_id: 1,
        symbol: 'FTFT',
        side: 'BUY',
        filled_qty: 1,
        avg_fill_price: 2.76,
        filled_at: '2026-09-11T13:30:00.000Z',
      }),
      order({
        order_id: 2,
        symbol: 'FTFT',
        side: 'SELL',
        filled_qty: 0,
        avg_fill_price: 3,
        filled_at: '2026-09-11T14:00:00.000Z',
      }),
      order({
        order_id: 3,
        symbol: 'AAPL',
        side: 'BUY',
        filled_qty: 2,
        avg_fill_price: 190,
        filled_at: '2026-09-11T13:31:00.000Z',
      }),
    ], 'FTFT');
    expect(fills).toEqual([
      {
        orderId: 1,
        timeIso: '2026-09-11T13:30:00.000Z',
        price: 2.76,
        side: 'BUY',
        qty: 1,
      },
    ]);
  });

  it('prefers closed-order fills when the same order_id is in both lists', () => {
    const working = order({
      order_id: 9,
      symbol: 'FTFT',
      side: 'BUY',
      filled_qty: 1,
      avg_fill_price: 2.7,
      filled_at: '2026-09-11T13:00:00.000Z',
    });
    const closed = order({
      order_id: 9,
      symbol: 'FTFT',
      side: 'BUY',
      filled_qty: 1,
      avg_fill_price: 2.76,
      filled_at: '2026-09-11T13:30:00.000Z',
    });
    expect(mergeFills([working], [closed], 'FTFT')).toEqual([
      {
        orderId: 9,
        timeIso: '2026-09-11T13:30:00.000Z',
        price: 2.76,
        side: 'BUY',
        qty: 1,
      },
    ]);
  });
});

describe('seriesMarkersForFills', () => {
  const t0 = isoToEtTime('2026-09-11T13:30:00.000Z', false);
  const t1 = isoToEtTime('2026-09-11T13:31:00.000Z', false);
  const t2 = isoToEtTime('2026-09-11T13:32:00.000Z', false);
  const index = buildSeriesTimeIndex([t0, t1, t2] as Time[]);

  it('places a buy arrow under the nearest bar', () => {
    const markers = seriesMarkersForFills(
      [{
        orderId: 1,
        timeIso: '2026-09-11T13:30:20.000Z',
        price: 2.76,
        side: 'BUY',
        qty: 1,
      }],
      index,
      '1Min',
    );
    expect(markers).toHaveLength(1);
    expect(markers[0]?.shape).toBe('arrowUp');
    expect(markers[0]?.position).toBe('belowBar');
    expect(markers[0]?.color).toBe(CHART_POSITION_LONG_COLOR);
    expect(markers[0]?.text).toBe('$2.76');
    expect(markers[0]?.time).toBe(t0);
  });

  it('places a sell arrow above the bar', () => {
    const markers = seriesMarkersForFills(
      [{
        orderId: 2,
        timeIso: '2026-09-11T13:31:00.000Z',
        price: 3.1,
        side: 'SELL',
        qty: 1,
      }],
      index,
      '1Min',
    );
    expect(markers[0]?.shape).toBe('arrowDown');
    expect(markers[0]?.position).toBe('aboveBar');
    expect(markers[0]?.color).toBe(CHART_POSITION_SHORT_COLOR);
    expect(markers[0]?.time).toBe(t1);
  });
});
