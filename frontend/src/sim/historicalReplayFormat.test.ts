import { expect, it } from 'vitest';
import { previousEtWeekday, sourceLabel } from './historicalReplayFormat';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

const base: HistoricalSnapshot = { active: true, symbol: 'IMCC', last: 2, volume: 1, source: 'trades', as_of: '', prints: [] };

it('labels every snapshot source, including trade coverage end in ET', () => {
  expect(sourceLabel(base)).toBe('Recorded trades · one-second timestamps');
  const through = Date.UTC(2026, 8, 18, 13, 30) / 1000;  // 09:30 ET
  expect(sourceLabel({ ...base, source: 'mixed', selection: {
    coverage_through: through, symbol: 'IMCC', date: '2026-09-18', start: '04:00', end: '20:00' } }))
    .toBe('Recorded trades through 09:30:00 ET · completed candles after');
  expect(sourceLabel({ ...base, source: 'completed_bars' })).toBe('Completed candles · trade tape unavailable');
  expect(sourceLabel({ ...base, source: 'loading' })).toBe('Loading…');
});

it('previous weekday follows the Eastern calendar, not the browser zone', () => {
  // 01:00 UTC Tuesday is still Monday evening in New York.
  expect(previousEtWeekday(new Date(Date.UTC(2026, 8, 22, 1, 0)))).toBe('2026-09-18');
  expect(previousEtWeekday(new Date(Date.UTC(2026, 8, 23, 15, 0)))).toBe('2026-09-22');
});
