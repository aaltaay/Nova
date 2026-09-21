/**
 * Pure view model for the practice account strip (ADR 020). No React, no fetch.
 */
import {
  PRACTICE_REPLAY_KEY_TITLE,
  PRACTICE_STRIP_BP_LABEL,
  PRACTICE_STRIP_CASH_LABEL,
  PRACTICE_STRIP_DAY_PNL_LABEL,
  PRACTICE_STRIP_FEES_LABEL,
  PRACTICE_STRIP_NO_REPLAY,
  PRACTICE_VENUES,
  practiceAccountIdTitle,
  practiceBuyingPowerTitle,
  practiceCashTitle,
  practiceDayPnlTitle,
  practiceFeesTitle,
  type PracticeVenue,
} from '../constantGroups/practice';
import { GLOBAL_BAR_OFFLINE_PLACEHOLDER } from '../constantGroups/global_bar';
import { formatMoney } from '../utils/formatMoney';
import type { PracticeAccount } from './practiceTypes';

export function isPracticeVenue(venue: string | null | undefined): venue is PracticeVenue {
  return (PRACTICE_VENUES as readonly string[]).includes(venue ?? '');
}

export interface PracticeMetricView {
  label: string;
  value: string;
  title: string;
  /** P&L tone class for the header (`global-app-bar__tone--*`), empty otherwise. */
  tone?: string;
}

export interface PracticeAccountView {
  venue: PracticeVenue;
  accountId: string;
  accountTitle: string;
  cash: PracticeMetricView;
  buyingPower: PracticeMetricView;
  dayPnl: PracticeMetricView;
  fees: PracticeMetricView;
  /** Sim only. `null` on Paper; a stated absence when Sim has nothing loaded. */
  replay: { value: string; title: string; loaded: boolean } | null;
}

const money = (n: number | null | undefined): string =>
  n == null || !Number.isFinite(n) ? GLOBAL_BAR_OFFLINE_PLACEHOLDER : formatMoney(n);

/** Signed money for P&L (`+$1.00` / `-$1.00` / `$0.00` / `--`). */
export function signedMoney(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return GLOBAL_BAR_OFFLINE_PLACEHOLDER;
  const body = formatMoney(Math.abs(n));
  return n > 0 ? `+${body}` : n < 0 ? `-${body}` : body;
}

export function pnlTone(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n === 0) return 'global-app-bar__tone--flat';
  return n > 0 ? 'global-app-bar__tone--up' : 'global-app-bar__tone--down';
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

export function buildPracticeAccountView(account: PracticeAccount): PracticeAccountView {
  const { venue } = account;
  const dayPnl = dayPnlOf(account);
  const fills = Number.isFinite(account.fills_today) ? account.fills_today : 0;
  const replayKey = account.replay_key?.trim() || '';
  return {
    venue,
    accountId: account.account_id,
    accountTitle: practiceAccountIdTitle(venue, account.account_id, money(account.starting_cash)),
    cash: {
      label: PRACTICE_STRIP_CASH_LABEL,
      value: money(account.cash),
      title: practiceCashTitle(money(account.net_liquidation)),
    },
    buyingPower: {
      label: PRACTICE_STRIP_BP_LABEL,
      value: money(account.buying_power),
      title: practiceBuyingPowerTitle(money(account.gross_position_value)),
    },
    dayPnl: {
      label: PRACTICE_STRIP_DAY_PNL_LABEL,
      value: signedMoney(dayPnl),
      title: practiceDayPnlTitle(
        signedMoney(account.realized_pnl),
        signedMoney(account.unrealized_pnl),
        account.day_started_et || 'the day start',
      ),
      tone: pnlTone(dayPnl),
    },
    fees: {
      label: PRACTICE_STRIP_FEES_LABEL,
      value: money(account.commissions_today),
      title: practiceFeesTitle(fills),
    },
    replay:
      venue === 'sim'
        ? {
            value: replayKey || PRACTICE_STRIP_NO_REPLAY,
            title: PRACTICE_REPLAY_KEY_TITLE,
            loaded: replayKey.length > 0,
          }
        : null,
  };
}
