/**
 * Header Cash / Margin chip.
 *
 * TWS AccountType is ownership (INDIVIDUAL / IRA / LLC), not Cash vs Margin.
 * AccountSummaryTags has no CASH / MARGIN / RegT / PortfolioMargin field.
 * TradingType-S is usually STKNOPT (securities trading config).
 * WhatIfPMEnabled and Leverage / BuyingPower are not classifiers.
 * Only explicit CASH / MARGIN tokens map. Otherwise Unknown.
 */
import {
  GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
  GLOBAL_BAR_ACCOUNT_TYPE_RAW_MISSING,
  GLOBAL_BAR_ACCOUNT_TYPE_RAW_PREFIX,
  GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
  GLOBAL_BAR_ACCOUNT_TYPE_TRADING_PREFIX,
  GLOBAL_BAR_ACCOUNT_TYPE_UNKNOWN,
} from '../constantGroups/global_bar';
import type { IbkrAccountSummary } from './types';

export type AccountTypeKind = 'cash' | 'margin' | 'unknown';

export type AccountTypeChipView = {
  kind: AccountTypeKind;
  label: string;
  tooltip: string;
};

const CASH_TOKENS = new Set(['CASH', 'CASH ACCOUNT']);
const MARGIN_TOKENS = new Set([
  'MARGIN',
  'MRGN',
  'REGT',
  'REGT MARGIN',
  'REG T MARGIN',
  'PORTFOLIO MARGIN',
  'PMRGN',
  'UNCLEARED MARGIN ACCOUNT',
  'PM',
]);

const LABELS: Record<AccountTypeKind, string> = {
  cash: GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  margin: GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
  unknown: GLOBAL_BAR_ACCOUNT_TYPE_UNKNOWN,
};

export function classifyAccountType(raw: string | null | undefined): AccountTypeKind {
  const key = (raw ?? '').trim().toUpperCase();
  if (!key) return 'unknown';
  if (CASH_TOKENS.has(key)) return 'cash';
  if (MARGIN_TOKENS.has(key)) return 'margin';
  return 'unknown';
}

export function classifyMarginKind(summary: IbkrAccountSummary): AccountTypeKind {
  for (const raw of [summary.AccountType, summary.TradingType]) {
    const kind = classifyAccountType(raw);
    if (kind !== 'unknown') return kind;
  }
  return 'unknown';
}

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
