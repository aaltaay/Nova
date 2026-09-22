/**
 * How old a bar-derived sensor reading is (QA W16, 2026-09-22): VWAP / MACD /
 * EMA read "live" from a week-old 1-minute bar set, and the last significant
 * move read "587539s ago". Readings carry `bars_as_of` (the newest bar's epoch
 * seconds); a set older than SENSORS_BARS_STALE_SEC is stale, and ages are
 * written in days / hours / minutes. Pure.
 */
import { STOCK_VIEW_CLOCK_TIMEZONE } from '../constantGroups/chart_api';
import { SENSORS_BARS_STALE_SEC } from '../constantGroups/sensors';
import type { SensorEnvelope } from './types';

const BAR_CLOCK = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
  timeZone: STOCK_VIEW_CLOCK_TIMEZONE,
});

/** "Sep 15, 10:10" (ET) when the reading's newest bar is stale, else null. */
export function sensorBarsStaleLabel(row: Pick<SensorEnvelope, 'data'>, nowSec: number): string | null {
  const t = row.data?.bars_as_of;
  if (typeof t !== 'number' || !Number.isFinite(t) || t <= 0) return null;
  if (nowSec - t <= SENSORS_BARS_STALE_SEC) return null;
  return BAR_CLOCK.format(new Date(t * 1000));
}

/** "45s", "3m 5s", "4h 12m", "6d 19h". */
export function humanAge(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}
