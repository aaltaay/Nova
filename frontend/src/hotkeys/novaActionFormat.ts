/**
 * Display helpers for Nova Action rows (landing + manager).
 */

import { NOVA_ACTION_KIND_LABELS } from '../constants';
import type { NovaActionRecord } from './novaActionTypes';

export function formatNovaActionParams(row: NovaActionRecord): string {
  if (row.kind === 'exit_pos_pct') return `Qty: ${row.params.percent ?? 50}%`;
  if (row.kind === 'buy_limit_ask_offset' || row.kind === 'sell_limit_bid_offset') {
    return `Qty: ${row.params.shares ?? 100}`;
  }
  if (row.kind === 'exit_pos' || row.kind === 'cancel_and_exit') return 'Position';
  if (row.kind === 'cancel_symbol') return 'All open';
  return '';
}

export function formatNovaActionListLabel(row: NovaActionRecord): string {
  const params = formatNovaActionParams(row);
  const base = row.name || NOVA_ACTION_KIND_LABELS[row.kind];
  return params ? `${base} · ${params}` : base;
}

export function describeNovaAction(row: NovaActionRecord): string {
  switch (row.kind) {
    case 'cancel_symbol':
      return 'Cancel all open orders for the active symbol.';
    case 'cancel_and_exit':
      return 'Cancel open orders, then flatten the position at market.';
    case 'exit_pos':
      return 'Flatten the full position at market.';
    case 'exit_pos_pct':
      return `Exit ${row.params.percent ?? 50}% of the position at market.`;
    case 'buy_limit_ask_offset':
      return `Place a BUY limit at Ask + $${row.params.offsetDollars ?? 0.05}, size ${row.params.shares ?? 100}.`;
    case 'sell_limit_bid_offset':
      return `Place a SELL limit at Bid - $${row.params.offsetDollars ?? 0.05}, size ${row.params.shares ?? 100}.`;
    default:
      return NOVA_ACTION_KIND_LABELS[row.kind];
  }
}
