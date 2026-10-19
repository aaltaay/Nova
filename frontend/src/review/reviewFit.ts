/** Visible range for the 04:00-16:00 ET session, in the chart's ET-encoded clock. */

import type { Time } from 'lightweight-charts';
import { isoToEtTime } from '../tickerChartData';

function wall(date: string, hour: number, minute: number): number {
  const [year, month, day] = date.split('-').map(Number);
  const guess = new Date(Date.UTC(year, month - 1, day, hour, minute, 0));
  const utc = guess.toLocaleString('en-US', { timeZone: 'UTC' });
  const et = guess.toLocaleString('en-US', { timeZone: 'America/New_York' });
  const offset = new Date(et).getTime() - new Date(utc).getTime();
  const instant = new Date(guess.getTime() - offset);
  return isoToEtTime(instant.toISOString(), false) as number;
}

export function sessionVisibleRange(date: string): { from: Time; to: Time } {
  return { from: wall(date, 4, 0) as Time, to: wall(date, 16, 0) as Time };
}
