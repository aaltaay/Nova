/** Turn a cut review payload into the recorded feed the desk chart paints. */

import type { RecordedChartFeed } from '../chart';
import type { ReviewPayload } from './reviewFixture';
import { TF_PANE, type ReviewTf } from './reviewQuery';

const PANE_IDS = {
  '10s': '10Sec',
  '1m': '1Min',
  '5m': '5Min',
  '1d': '1Day',
} as const;

export function feedFromPayload(payload: ReviewPayload): RecordedChartFeed {
  const bars: RecordedChartFeed['bars'] = {};
  for (const tf of Object.keys(TF_PANE) as ReviewTf[]) {
    const frame = payload.timeframes[tf];
    if (frame) bars[PANE_IDS[tf]] = frame.bars;
  }
  return {
    kind: 'recorded',
    symbol: payload.symbol,
    date: payload.date,
    asOfIso: payload.as_of_iso,
    source: payload.source === 'fixture' ? 'fixture' : 'front-door',
    bars,
    vwapBars: payload.timeframes['1m']?.bars ?? [],
  };
}
