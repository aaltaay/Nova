/**
 * Header Cash / Margin chip.
 *
 * Connected + snapshot → Cash or Margin (never Unknown). Hidden when disconnected.
 * Raw AccountType stays in the tooltip. Ticket Short uses shortSideVisible.
 */
import {
  GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
  GLOBAL_BAR_ACCOUNT_TYPE_RAW_MISSING,
  GLOBAL_BAR_ACCOUNT_TYPE_RAW_PREFIX,
  GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
  GLOBAL_BAR_ACCOUNT_TYPE_TRADING_PREFIX,
} from '../constantGroups/global_bar';
import { classifyMarginKind } from './accountType';
import type { IbkrAccountSummary } from './types';

export type { AccountTypeKind } from './accountType';
export { classifyAccountType, classifyMarginKind, shortSideVisible } from './accountType';

export type AccountTypeChipView = {
  kind: 'cash' | 'margin';
  label: string;
  tooltip: string;
};

const LABELS: Record<'cash' | 'margin', string> = {
  cash: GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  margin: GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
};

export function accountTypeTooltip(summary: IbkrAccountSummary): string {
  const raw = (summary.AccountType ?? '').trim() || GLOBAL_BAR_ACCOUNT_TYPE_RAW_MISSING;
  const parts = [
    GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
    `${GLOBAL_BAR_ACCOUNT_TYPE_RAW_PREFIX} ${raw}`,
  ];
  const trading = (summary.TradingType ?? '').trim();
  if (trading) {
    parts.push(`${GLOBAL_BAR_ACCOUNT_TYPE_TRADING_PREFIX} ${trading}`);
  }
  return parts.join(' ');
}

export function accountTypeChipView(opts: {
  ibkrConnected: boolean;
  summary: IbkrAccountSummary | null;
}): AccountTypeChipView | null {
  if (!opts.ibkrConnected || !opts.summary?.connected) return null;
  const kind = classifyMarginKind(opts.summary);
  return {
    kind,
    label: LABELS[kind],
    tooltip: accountTypeTooltip(opts.summary),
  };
}
