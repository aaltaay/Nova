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

/** Each pane's subtitle, from the source the payload names for it (never the live desk's IBKR note). */
export const REVIEW_SOURCE_NOTES: Record<string, string> = {
  'massive-trades': 'Massive tape -- built from the consolidated trades',
  'massive-minutes': 'Massive minute bars',
  'massive-daily': "Massive daily bars -- this day's candle from its minutes",
};
export const REVIEW_FIXTURE_NOTE = 'Sample -- not a recorded day';

export function reviewPaneNote(tf: ReviewTf, source: string | undefined, fixture: boolean): string | undefined {
  if (fixture) return REVIEW_FIXTURE_NOTE;
  const words = source ? REVIEW_SOURCE_NOTES[source] : undefined;
  return words ? `${tf} · ${words}` : undefined;
}

export function feedFromPayload(payload: ReviewPayload): RecordedChartFeed {
  const bars: RecordedChartFeed['bars'] = {};
  const notes: NonNullable<RecordedChartFeed['notes']> = {};
  const fixture = payload.source === 'fixture';
  for (const tf of Object.keys(TF_PANE) as ReviewTf[]) {
    const frame = payload.timeframes[tf];
    if (!frame) continue;
    bars[PANE_IDS[tf]] = frame.bars;
    const note = reviewPaneNote(tf, frame.source, fixture);
    if (note) notes[PANE_IDS[tf]] = note;
  }
  return {
    kind: 'recorded',
    symbol: payload.symbol,
    date: payload.date,
    asOfIso: payload.as_of_iso,
    source: fixture ? 'fixture' : 'front-door',
    bars,
    vwapBars: payload.timeframes['1m']?.bars ?? [],
    notes,
  };
}
