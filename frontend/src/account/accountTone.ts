/**
 * How a money figure is coloured on the Account page (and the header's Day's).
 * P&L is red / green only once it moves at least PNL_TONE_MIN_USD; smaller
 * moves, rounded zeros, costs and cash movements stay neutral.
 */
import { PNL_TONE_MIN_USD } from '../constantGroups/account_page';

export type Tone = 'up' | 'down' | 'flat' | 'bot' | 'muted';

/** What a signed figure is: P&L (tinted past the floor), a cost (muted), cash moved (plain). */
export type MoneyKind = 'pnl' | 'cost' | 'cash';

export function toneOf(n: number | null | undefined, minAbs: number = PNL_TONE_MIN_USD): Tone {
  if (n == null || !Number.isFinite(n)) return 'flat';
  const cents = Math.round(n * 100) / 100;
  if (cents === 0 || Math.abs(cents) < minAbs) return 'flat';
  return cents > 0 ? 'up' : 'down';
}

export function toneOfKind(n: number | null | undefined, kind: MoneyKind): Tone {
  if (kind === 'cost') return 'muted';
  if (kind === 'cash') return 'flat';
  return toneOf(n);
}

export const toneClass = (tone: Tone): string => `acct-tone--${tone}`;
