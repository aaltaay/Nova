/**
 * Pure figures behind the compact header account cluster (Day's / TAV and
 * their cards). One shape whichever account is THE account on the venue: the
 * IBKR summary on Live, Nova's practice ledger on Paper / Sim (ADR 020). The
 * buttons never learn which one they are showing. No React, no fetch.
 */
import { GLOBAL_BAR_OFFLINE_PLACEHOLDER } from '../constantGroups/global_bar';
import type { IbkrAccountSummary } from '../ibkr/types';
import { dayPnlOf } from '../practice/practiceAccountModel';
import type { PracticeAccount } from '../practice/practiceTypes';
import { formatMoney } from '../utils/formatMoney';
import { dayPnlFromSummary } from './globalBarMoney';

export type HeaderAccountSource = 'ibkr' | 'practice';

export interface HeaderAccountFigures {
  source: HeaderAccountSource;
  openPnl: number | null;
  realizedPnl: number | null;
  dayPnl: number | null;
  /** Total Account Value -- IBKR NetLiquidation / practice net_liquidation. */
  netLiquidation: number | null;
  cash: number | null;
  buyingPower: number | null;
  /** IBKR only; the practice ledger reports no maintenance margin. */
  excessLiquidity: number | null;
  grossPositionValue: number | null;
  /** Practice only. */
  feesToday: number | null;
  startingCash: number | null;
  /** Sim only: `''` while Sim has nothing loaded; `null` off Sim. */
  replayKey: string | null;
}

const finite = (n: number | null | undefined): number | null =>
  n == null || !Number.isFinite(n) ? null : n;

/** `$1,234.56`, or the header placeholder -- never a fabricated zero. */
export const headerMoney = (n: number | null | undefined): string =>
  n == null || !Number.isFinite(n) ? GLOBAL_BAR_OFFLINE_PLACEHOLDER : formatMoney(n);

export function figuresFromSummary(summary: IbkrAccountSummary | null): HeaderAccountFigures {
  return {
    source: 'ibkr',
    openPnl: finite(summary?.UnrealizedPnL),
    realizedPnl: finite(summary?.RealizedPnL),
    dayPnl: dayPnlFromSummary(summary?.RealizedPnL, summary?.UnrealizedPnL),
    netLiquidation: finite(summary?.NetLiquidation),
    cash: finite(summary?.TotalCashValue),
    buyingPower: finite(summary?.BuyingPower),
    excessLiquidity: finite(summary?.ExcessLiquidity),
    grossPositionValue: finite(summary?.GrossPositionValue),
    feesToday: null,
    startingCash: null,
    replayKey: null,
  };
}

export function figuresFromPractice(account: PracticeAccount): HeaderAccountFigures {
  return {
    source: 'practice',
    openPnl: finite(account.unrealized_pnl),
    realizedPnl: finite(account.realized_pnl),
    dayPnl: dayPnlOf(account),
    netLiquidation: finite(account.net_liquidation),
    cash: finite(account.cash),
    buyingPower: finite(account.buying_power),
    excessLiquidity: null,
    grossPositionValue: finite(account.gross_position_value),
    feesToday: finite(account.commissions_today),
    startingCash: finite(account.starting_cash),
    replayKey: account.venue === 'sim' ? (account.replay_key?.trim() ?? '') : null,
  };
}

/**
 * Day's percent = dayPnl / (netLiquidation - dayPnl), i.e. against the value
 * the account started the day with. Null unless that base is > 0 -- a zero or
 * negative base has no honest percent.
 */
export function dayPnlPercent(dayPnl: number | null, netLiquidation: number | null): number | null {
  if (dayPnl == null || netLiquidation == null) return null;
  const base = netLiquidation - dayPnl;
  if (!(base > 0)) return null;
  return (dayPnl / base) * 100;
}
