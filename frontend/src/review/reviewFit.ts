/** Visible range for the 04:00-16:00 ET session, in the chart's ET-encoded clock. */

import type { Time } from 'lightweight-charts';
import { isoToEtTime } from '../tickerChartData';

function wall(date: string, hour: number, minute: number): number {
  const [year, month, day] = date.split('-').map(Number);
  const utcGuess = Date.UTC(year, month - 1, day, hour, minute, 0);
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(new Date(utcGuess));
  const pick = (type: string) => Number(parts.find((part) => part.type === type)?.value);
  const asUtc = Date.UTC(pick('year'), pick('month') - 1, pick('day'), pick('hour'), pick('minute'), pick('second'));
  return isoToEtTime(new Date(utcGuess - (asUtc - utcGuess)).toISOString(), false) as number;
}

export function sessionVisibleRange(date: string): { from: Time; to: Time } {
  // Blank time before 04:00 so "4:00 AM" is not cut off at the left edge,
  // and a little after 16:00 so the last candle is not flush with the scale.
  return {
    from: (wall(date, 4, 0) - 90 * 60) as Time,
    to: (wall(date, 16, 0) + 40 * 60) as Time,
  };
}
