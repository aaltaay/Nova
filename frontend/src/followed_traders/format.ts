/** How the Followed traders page writes its numbers and times. Unknown is an em dash, never 0. */
import { FT_EXIT_PENDING, FT_EXIT_UNAVAILABLE, FT_EXIT_WAITING, FT_STAKE_USD } from './constants';
import type { FollowedExit, FollowedTrade, PointPl, RangePl } from './types';

export const DASH = '—';
const MINUS = '−';

const ET_CLOCK = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

const ET_HOUR = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', minute: '2-digit' });
const ET_DAY = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short',
  month: 'short',
  day: 'numeric',
});

/** "4:00 AM" in New York time. */
export function etHour(ts: number): string {
  return ET_HOUR.format(new Date(ts * 1000));
}

/** "Wed, Oct 14" in New York time. */
export function etDay(ts: number): string {
  return ET_DAY.format(new Date(ts * 1000));
}

/** "10:42:07" in New York time. */
export function etTime(ts: number | null | undefined): string {
  if (ts === null || ts === undefined || !Number.isFinite(ts)) return DASH;
  return ET_CLOCK.format(new Date(ts * 1000));
}

/** A stock price: four decimals under $1, two from $1. */
export function price(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return DASH;
  return p.toFixed(Math.abs(p) < 1 ? 4 : 2);
}

function signed(x: number, digits: number, suffix = ''): string {
  const s = Math.abs(x).toFixed(digits);
  if (Number(s) === 0) return `${s}${suffix}`;
  return `${x > 0 ? '+' : MINUS}${s}${suffix}`;
}

/** A percent with its sign: "+8.82%", "−0.96%", "0.00%". */
export function signedPct(x: number): string {
  return signed(x, 2, '%');
}

export function isRangePl(pl: PointPl | RangePl): pl is RangePl {
  return 'low_per_share' in pl;
}

/** P/L per share: "+0.25", or "−0.30 to −0.10" for a window exit; four decimals on a sub-dollar stock. */
export function plPerShare(pl: PointPl | RangePl | null, avgPrice: number): string {
  if (!pl) return DASH;
  const digits = Math.abs(avgPrice) < 1 ? 4 : 2;
  if (isRangePl(pl)) return `${signed(pl.low_per_share, digits)} to ${signed(pl.high_per_share, digits)}`;
  return signed(pl.per_share, digits);
}

export function plPct(pl: PointPl | RangePl | null): string {
  if (!pl) return DASH;
  if (isRangePl(pl)) return `${signed(pl.low_pct, 2, '%')} to ${signed(pl.high_pct, 2, '%')}`;
  return signed(pl.pct, 2, '%');
}

/** Dollars with their sign and cents: "+$26.09", "−$72.38", "$0.00". */
export function signedUsd(x: number): string {
  const s = Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (Number(Math.abs(x).toFixed(2)) === 0) return `$${s}`;
  return `${x > 0 ? '+' : MINUS}$${s}`;
}

/** Dollars short enough for a calendar square: "+$45", "−$1.2k", "$0". */
export function shortUsd(x: number): string {
  const a = Math.abs(x);
  const body = a >= 1000 ? `${(a / 1000).toFixed(a >= 10_000 ? 0 : 1)}k` : a.toFixed(0);
  if (body === '0') return '$0';
  return `${x > 0 ? '+' : MINUS}$${body}`;
}

/** What `FT_STAKE_USD` in the trade would have made, from its P/L in %: "−$26.32", or "−$15.00 to +$5.00" for a
 *  window exit. */
export function plAtStake(pl: PointPl | RangePl | null): string {
  if (!pl) return DASH;
  const usd = (pct: number) => signedUsd((pct / 100) * FT_STAKE_USD);
  if (isRangePl(pl)) return `${usd(pl.low_pct)} to ${usd(pl.high_pct)}`;
  return usd(pl.pct);
}

/** Up, down or flat, for the P/L's colour; a range that straddles zero is flat. */
export function plTone(pl: PointPl | RangePl | null): 'up' | 'down' | 'flat' {
  if (!pl) return 'flat';
  const [lo, hi] = isRangePl(pl) ? [pl.low_per_share, pl.high_per_share] : [pl.per_share, pl.per_share];
  if (lo > 0) return 'up';
  if (hi < 0) return 'down';
  return 'flat';
}

/** "45s", "12m 05s", "1h 02m". */
export function duration(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`;
}

/** How long it was held: one time, a floor ("≥ 12m 05s"), or a window ("12m 05s–14m 00s"). */
export function held(h: FollowedTrade['held']): string {
  if (h.min_sec === null) return DASH;
  if (h.max_sec === null) return `≥ ${duration(h.min_sec)}`;
  if (h.max_sec === h.min_sec) return duration(h.min_sec);
  return `${duration(h.min_sec)}–${duration(h.max_sec)}`;
}

/** When it was entered: a time, "by 10:42:07" (open before the feed saw it), or a window. */
export function entered(entry: FollowedTrade['entry']): string {
  if (!entry.known) return `by ${etTime(entry.ts)}`;
  if (entry.since_ts !== null) return `${etTime(entry.since_ts)}–${etTime(entry.ts)}`;
  return etTime(entry.ts);
}

/** When it was closed: a time, or the window it happened in. */
export function exited(exit: FollowedExit): string {
  if (exit.to_ts === null) return DASH;
  if (exit.from_ts !== null) return `${etTime(exit.from_ts)}–${etTime(exit.to_ts)}`;
  return etTime(exit.to_ts);
}

/** The exit price: a fill, a low–high range (no single fill is invented), or why there is none. */
export function exitPrice(exit: FollowedExit): string {
  if (exit.state === 'at') return price(exit.price);
  if (exit.state === 'range') return `${price(exit.low)}–${price(exit.high)}`;
  if (exit.state === 'pending') return exit.why ? FT_EXIT_WAITING : FT_EXIT_PENDING;
  return FT_EXIT_UNAVAILABLE;
}
