/**
 * Chart axis + crosshair time labels (12-hour AM/PM).
 *
 * Bar times are ET wall-clock encoded as UTC timestamps via `isoToEtTime`
 * in `tickerChartData.ts` — format with UTC getters so labels stay ET.
 */

import { TickMarkType, type Time } from 'lightweight-charts';

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

function asDate(time: number): Date {
  return new Date(time * 1000);
}

function pad2(n: number): string {
  return n.toString().padStart(2, '0');
}

/** `5:02 PM` / `12:00 AM` from 0–23 hour (ET-as-UTC). */
export function formatAmPmClock(hour24: number, minute: number, second?: number): string {
  const ampm = hour24 >= 12 ? 'PM' : 'AM';
  let hour = hour24 % 12;
  if (hour === 0) hour = 12;
  const base = `${hour}:${pad2(minute)}`;
  if (second === undefined) return `${base} ${ampm}`;
  return `${base}:${pad2(second)} ${ampm}`;
}

function businessDayParts(
  time: Extract<Time, string | { year: number; month: number; day: number }>,
): { year: number; month: number; day: number } | null {
  if (typeof time === 'string') {
    const [y, m, d] = time.split('-').map(Number);
    if (!y || !m || !d) return null;
    return { year: y, month: m, day: d };
  }
  return { year: time.year, month: time.month, day: time.day };
}

function formatBusinessDay(
  time: Extract<Time, string | { year: number; month: number; day: number }>,
): string {
  const parts = businessDayParts(time);
  if (!parts) return String(time);
  const yy = String(parts.year).slice(-2);
  return `${parts.day} ${MONTHS[parts.month - 1]} '${yy}`;
}

/** Crosshair label — e.g. `23 Jul '26 5:02 PM` (ET). */
export function formatChartCrosshairTime(time: Time): string {
  if (typeof time !== 'number') return formatBusinessDay(time);
  const d = asDate(time);
  const yy = String(d.getUTCFullYear()).slice(-2);
  const clock = formatAmPmClock(d.getUTCHours(), d.getUTCMinutes());
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} '${yy} ${clock}`;
}

/**
 * Axis tick labels. Keep short (library recommends ≤8 chars for Time ticks).
 * Returns null for non-numeric times so the library default applies.
 */
export function formatChartTickMark(
  time: Time,
  tickMarkType: TickMarkType,
  _locale: string,
): string | null {
  if (typeof time !== 'number') return null;
  const d = asDate(time);
  switch (tickMarkType) {
    case TickMarkType.Year:
      return String(d.getUTCFullYear());
    case TickMarkType.Month:
      return `${MONTHS[d.getUTCMonth()]} '${String(d.getUTCFullYear()).slice(-2)}`;
    case TickMarkType.DayOfMonth:
      return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
    case TickMarkType.Time:
      return formatAmPmClock(d.getUTCHours(), d.getUTCMinutes());
    case TickMarkType.TimeWithSeconds:
      return formatAmPmClock(d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds());
    default:
      return null;
  }
}
