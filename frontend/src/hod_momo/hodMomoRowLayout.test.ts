import { describe, expect, it } from 'vitest';
import {
  HOD_MOMO_ROW_HEIGHT_PX,
  HOD_MOMO_STRATEGY_PILL_LINE_PX,
} from '../constants';
import type { AlertObject } from './types';
import {
  buildHodMomoRowOffsets,
  findRowAtOffset,
  hodMomoAlertRowHeightPx,
  visibleStrategyTags,
} from './hodMomoRowLayout';

function alert(partial: Partial<AlertObject> & Pick<AlertObject, 'id' | 'ticker'>): AlertObject {
  return {
    timestamp: '2026-07-29T16:00:00Z',
    strategy_id: 11,
    strategy_name: 'Squeeze Alert - Up 5% in 5min',
    price: 1,
    change_pct: 5,
    rvol: null,
    float_shares: null,
    gap_pct: null,
    volume: null,
    momentum_pct: null,
    consolidation_count: 1,
    consolidated_ids: [],
    created_ts: 0,
    ...partial,
  };
}

describe('hodMomoRowLayout', () => {
  it('filters Former Momo and stacks height for multi-strategy rows', () => {
    const multi = alert({
      id: 'a',
      ticker: 'DFNS',
      strategies: [
        { id: 1, name: 'Former Momo Stock' },
        { id: 11, name: 'Squeeze Alert - Up 5% in 5min' },
        { id: 10, name: 'Squeeze Alert - Up 10% in 10min' },
      ],
    });
    expect(visibleStrategyTags(multi).map(t => t.id)).toEqual([11, 10]);
    expect(hodMomoAlertRowHeightPx(multi)).toBe(
      HOD_MOMO_ROW_HEIGHT_PX + HOD_MOMO_STRATEGY_PILL_LINE_PX,
    );
  });

  it('keeps single-strategy rows at the base height', () => {
    const one = alert({ id: 'b', ticker: 'AAA' });
    expect(hodMomoAlertRowHeightPx(one)).toBe(HOD_MOMO_ROW_HEIGHT_PX);
  });

  it('builds prefix offsets and finds the row at a scroll position', () => {
    const alerts = [
      alert({ id: '1', ticker: 'A' }),
      alert({
        id: '2',
        ticker: 'B',
        strategies: [
          { id: 11, name: 'Squeeze Alert - Up 5% in 5min' },
          { id: 10, name: 'Squeeze Alert - Up 10% in 10min' },
        ],
      }),
      alert({ id: '3', ticker: 'C' }),
    ];
    const offsets = buildHodMomoRowOffsets(alerts);
    expect(offsets).toEqual([
      0,
      HOD_MOMO_ROW_HEIGHT_PX,
      HOD_MOMO_ROW_HEIGHT_PX + (HOD_MOMO_ROW_HEIGHT_PX + HOD_MOMO_STRATEGY_PILL_LINE_PX),
      offsets[2] + HOD_MOMO_ROW_HEIGHT_PX,
    ]);
    expect(findRowAtOffset(offsets, 0)).toBe(0);
    expect(findRowAtOffset(offsets, HOD_MOMO_ROW_HEIGHT_PX)).toBe(1);
    expect(findRowAtOffset(offsets, offsets[2])).toBe(2);
  });
});
