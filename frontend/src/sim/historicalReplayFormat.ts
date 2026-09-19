/** Pure formatting for the historical replay panel and quote/tape card. */
import { SIM_ET_TIME_ZONE } from './simConstants';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

/** Previous Eastern weekday; the API's holiday-aware default_date replaces it. */
export function previousEtWeekday(now = new Date()): string {
  const et = new Date(now.toLocaleString('en-US', { timeZone: SIM_ET_TIME_ZONE }));
  et.setDate(et.getDate() - 1);
  while (et.getDay() === 0 || et.getDay() === 6) et.setDate(et.getDate() - 1);
  return et.toLocaleDateString('en-CA');
}

export function etTime(value: string | number): string {
  const when = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  return when.toLocaleTimeString('en-US', { timeZone: SIM_ET_TIME_ZONE, hour12: false });
}

export function sourceLabel(data: HistoricalSnapshot): string {
  switch (data.source) {
    case 'trades':
      return 'Recorded trades · one-second timestamps';
    case 'mixed': {
      const through = data.selection?.coverage_through;
      return `Recorded trades through ${through ? `${etTime(through)} ET` : 'the download'} · completed candles after`;
    }
    case 'completed_bars':
      return 'Completed candles · trade tape unavailable';
    default:
      return 'Loading…';
  }
}
