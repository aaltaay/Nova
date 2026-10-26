/** A labelled sample session. It is not a recorded tape. */

import type { RawBar } from '../tickerChartData';
import { cutBars, sessionCandle } from './reviewCut';
import type { ReviewLevels } from './reviewLevels';
import type { ReviewTf } from './reviewQuery';

export interface ReviewPayload {
  ok: true;
  schema_version: 1;
  symbol: string;
  date: string;
  as_of: string;
  as_of_iso: string;
  source: string;
  lookahead: false;
  vwap_anchor: '04:00';
  /** `source` names where a frame's bars came from (`massive-trades`, `massive-minutes`, `massive-daily`); absent = unstated. */
  timeframes: Partial<Record<ReviewTf, { bars: RawBar[]; source?: string }>>;
  levels: ReviewLevels;
  setups: { kind: string; time: string; price: number; label: string }[];
}

function mix(seed: number): number {
  let value = seed >>> 0;
  value = Math.imul(value ^ (value >>> 16), 2246822507);
  value = Math.imul(value ^ (value >>> 13), 3266489909);
  return ((value ^ (value >>> 16)) >>> 0) / 4294967296;
}

function stamp(date: string, minuteOfDay: number): string {
  const hour = Math.floor(minuteOfDay / 60);
  const minute = minuteOfDay % 60;
  const probe = new Date(Date.UTC(
    Number(date.slice(0, 4)),
    Number(date.slice(5, 7)) - 1,
    Number(date.slice(8, 10)),
    hour,
    minute,
  ));
  const utc = probe.toLocaleString('en-US', { timeZone: 'UTC' });
  const et = probe.toLocaleString('en-US', { timeZone: 'America/New_York' });
  const offsetMin = Math.round((new Date(et).getTime() - new Date(utc).getTime()) / 60000);
  const sign = offsetMin <= 0 ? '-' : '+';
  const abs = Math.abs(offsetMin);
  const hh = String(Math.floor(abs / 60)).padStart(2, '0');
  const mm = String(abs % 60).padStart(2, '0');
  return `${date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00${sign}${hh}:${mm}`;
}

function walk(symbol: string, date: string, stepMin: number): RawBar[] {
  let seed = 2166136261;
  for (const ch of symbol) seed = Math.imul(seed ^ ch.charCodeAt(0), 16777619);
  let price = 4 + mix(seed) * 12;
  const bars: RawBar[] = [];
  for (let minute = 4 * 60; minute < 16 * 60; minute += stepMin) {
    seed = Math.imul(seed ^ minute, 16777619);
    const drift = (mix(seed) - 0.48) * 0.15;
    const open = price;
    price = Math.max(0.5, price + drift);
    const high = Math.max(open, price) + mix(seed ^ 3) * 0.08;
    const low = Math.min(open, price) - mix(seed ^ 7) * 0.08;
    bars.push({
      t: stamp(date, minute),
      o: round(open),
      h: round(high),
      l: round(Math.max(0.2, low)),
      c: round(price),
      v: Math.round(1000 + mix(seed ^ 9) * 8000),
    });
  }
  return bars;
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

function rollup(bars: RawBar[], stepMin: number): RawBar[] {
  const out: RawBar[] = [];
  for (let index = 0; index < bars.length; index += stepMin) {
    const slice = bars.slice(index, index + stepMin);
    if (!slice.length) continue;
    out.push({
      t: slice[0].t,
      o: slice[0].o,
      h: Math.max(...slice.map((bar) => bar.h)),
      l: Math.min(...slice.map((bar) => bar.l)),
      c: slice[slice.length - 1].c,
      v: slice.reduce((sum, bar) => sum + bar.v, 0),
    });
  }
  return out;
}

function flatTops(fives: RawBar[]): ReviewPayload['setups'] {
  const found: ReviewPayload['setups'] = [];
  let index = 0;
  while (index + 2 < fives.length && found.length < 4) {
    const window = fives.slice(index, index + 3);
    const highs = window.map((bar) => bar.h);
    const top = Math.max(...highs);
    if (top > 0 && (top - Math.min(...highs)) / top <= 0.005) {
      found.push({ kind: 'flat_top', time: window[2].t, price: top, label: 'flat top' });
      index += 3;
    } else {
      index += 1;
    }
  }
  return found;
}

function dailies(date: string, session: RawBar | null): RawBar[] {
  const end = new Date(`${date}T12:00:00Z`);
  const rows: RawBar[] = [];
  let price = Math.max(1, (session?.c ?? 8) * 0.7);
  for (let back = 130; back >= 1; back -= 1) {
    const day = new Date(end.getTime() - back * 86400000);
    if (day.getUTCDay() === 0 || day.getUTCDay() === 6) continue;
    const iso = day.toISOString().slice(0, 10);
    const open = price;
    price = Math.max(0.5, price * (1 + ((back % 7) - 3) * 0.004));
    rows.push({
      t: iso,
      o: round(open),
      h: round(Math.max(open, price) * 1.02),
      l: round(Math.min(open, price) * 0.98),
      c: round(price),
      v: 100000 + back * 1000,
    });
  }
  if (session) rows.push(session);
  return rows;
}

export function fixturePayload(symbol: string, date: string, tfs: ReviewTf[], asOf: string): ReviewPayload {
  const [hour, minute] = asOf.split(':').map(Number);
  const asOfIso = stamp(date, hour * 60 + minute);
  const allMinutes = walk(symbol, date, 1);
  const minutes = cutBars(allMinutes, '1m', asOfIso);
  const fives = cutBars(rollup(allMinutes, 5), '5m', asOfIso);
  const session = sessionCandle(date, minutes);
  const timeframes: ReviewPayload['timeframes'] = { '1m': { bars: minutes } };
  if (tfs.includes('5m')) timeframes['5m'] = { bars: fives };
  if (tfs.includes('10s')) {
    const tens: RawBar[] = [];
    for (const bar of allMinutes) {
      for (let seconds = 0; seconds < 60; seconds += 10) {
        tens.push({ ...bar, t: bar.t.replace(/T(\d{2}):(\d{2}):\d{2}/, `T$1:$2:${String(seconds).padStart(2, '0')}`) });
      }
    }
    timeframes['10s'] = { bars: cutBars(tens, '10s', asOfIso) };
  }
  const daily = dailies(date, session);
  if (tfs.includes('1d')) timeframes['1d'] = { bars: daily };
  const premarket = minutes.filter((bar) => bar.t.slice(11, 16) < '09:30');
  const opening = asOf >= '09:35'
    ? minutes.filter((bar) => bar.t.slice(11, 16) >= '09:30' && bar.t.slice(11, 16) < '09:35')
    : [];
  const prior = daily.filter((bar) => bar.t < date).at(-1);
  return {
    ok: true,
    schema_version: 1,
    symbol,
    date,
    as_of: asOf,
    as_of_iso: asOfIso,
    source: 'fixture',
    lookahead: false,
    vwap_anchor: '04:00',
    timeframes,
    levels: {
      hod: session?.h ?? null,
      lod: session?.l ?? null,
      premarket_high: premarket.length ? Math.max(...premarket.map((bar) => bar.h)) : null,
      opening_range_high: opening.length ? Math.max(...opening.map((bar) => bar.h)) : null,
      opening_range_low: opening.length ? Math.min(...opening.map((bar) => bar.l)) : null,
      prior_high: prior?.h ?? null,
      prior_low: prior?.l ?? null,
      prior_close: prior?.c ?? null,
    },
    setups: flatTops(fives),
  };
}
