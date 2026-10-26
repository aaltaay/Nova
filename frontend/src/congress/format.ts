/**
 * The Congress page's words for dates, ranges, seats and sides (ADR 066). A range stays a range: nothing here turns
 * an amount into a share count or a price.
 */
import { LATE_DAYS } from './constants';
import type { Member } from './types';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Oct 12" for 2026-10-12; "Oct 12, 2025" when the year is not `year`. */
export function day(iso: string | null | undefined, year?: number): string {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return iso;
  return `${MONTHS[m - 1]} ${d}${year != null && y !== year ? `, ${y}` : ''}`;
}

/** "$15K–50K", "$1M–5M", "Over $50M": the amount's range, short. The filer's text when it holds no figure. */
export function range(text: string, low: number | null, high: number | null): string {
  const k = (n: number) => (n >= 1_000_000 ? `${+(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}K` : `${n}`);
  if (low == null) return text;
  if (high == null) return `Over $${k(low)}`;
  if (high === low) return `$${k(low)}`;
  return `$${k(low)}–${k(high)}`;
}

/** "$15K–50K" from an amount as filed ("$15,001 - $50,000"). */
export function rangeText(text: string): string {
  const figures = [...text.matchAll(/\$\s*([\d,]+)/g)].map((m) => Number(m[1].replace(/,/g, '')));
  if (figures.length >= 2) return range(text, figures[0], figures[1]);
  if (figures.length === 1) return range(text, figures[0], /over/i.test(text) ? null : figures[0]);
  return text;
}

/** "D-CA-31", "R-PA" (a senator), "D-PR" (a delegate). */
export function seat(m: Pick<Member, 'party' | 'state' | 'district' | 'chamber'>): string {
  const head = `${m.party ?? '?'}-${m.state ?? '?'}`;
  return m.chamber === 'house' && m.district != null && m.district > 0 ? `${head}-${m.district}` : head;
}

export function chamberWord(chamber: string): string {
  return chamber === 'senate' ? 'Senate' : 'House';
}

export function initials(name: string): string {
  const words = name.replace(/[^A-Za-z\s.-]/g, ' ').split(/\s+/).filter((w) => /^[A-Za-z]/.test(w));
  const first = words[0]?.[0] ?? '?';
  const last = words.length > 1 ? words[words.length - 1][0] : '';
  return `${first}${last}`.toUpperCase();
}

/** What the trade was, in a word or two: Bought / Sold / Sold part / Gift / Exchange. */
export function sideWord(t: { side: string; partial?: boolean; gift: boolean }): string {
  if (t.gift) return 'Gift';
  if (t.side === 'buy') return 'Bought';
  if (t.side === 'sell') return t.partial ? 'Sold part' : 'Sold';
  if (t.side === 'exchange') return 'Exchange';
  return 'Other';
}

export function sideClass(t: { side: string; gift: boolean }): string {
  if (t.gift) return 'is-gift';
  return t.side === 'buy' ? 'is-up' : t.side === 'sell' ? 'is-down' : '';
}

/** ok up to 30 days, warn to the 45-day limit, late past it. */
export function lagClass(days: number | null | undefined): string {
  if (days == null) return '';
  return days <= 30 ? 'is-ok' : days <= LATE_DAYS ? 'is-warn' : 'is-late';
}

export function etTime(epochSec: number | null | undefined): string {
  if (!epochSec) return '';
  return new Date(epochSec * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/New_York',
  });
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n == null || !Number.isFinite(n)) return '–';
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`;
}
