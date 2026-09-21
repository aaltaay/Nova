/**
 * Pure helpers for Nova's practice account (ADR 020). No React, no fetch.
 * The header figures themselves are built in components/headerAccountFigures.
 */
import { PRACTICE_VENUES, type PracticeVenue } from '../constantGroups/practice';
import type { PracticeAccount } from './practiceTypes';

export function isPracticeVenue(venue: string | null | undefined): venue is PracticeVenue {
  return (PRACTICE_VENUES as readonly string[]).includes(venue ?? '');
}

/** Day P&L from the wire; realized + unrealized when the backend omits the sum. */
export function dayPnlOf(account: Pick<PracticeAccount, 'day_pnl' | 'realized_pnl' | 'unrealized_pnl'>): number | null {
  if (Number.isFinite(account.day_pnl)) return account.day_pnl;
  const realized = Number.isFinite(account.realized_pnl) ? account.realized_pnl : 0;
  const unrealized = Number.isFinite(account.unrealized_pnl) ? account.unrealized_pnl : 0;
  return Number.isFinite(account.realized_pnl) || Number.isFinite(account.unrealized_pnl)
    ? realized + unrealized
    : null;
}
