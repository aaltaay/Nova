/**
 * Display helpers for Nova Action rows (landing + manager).
 */

import { NOVA_ACTION_KIND_LABELS } from '../constants';
import type { NovaActionRecord } from './novaActionTypes';

export function formatNovaActionParams(row: NovaActionRecord): string {
  if (row.kind === 'exit_pos_pct') return `Qty: ${row.params.percent ?? 50}%`;
  if (row.kind === 'sell_pos_pct_ask' || row.kind === 'sell_pos_pct_bid_offset') {
    const pct = row.params.percent ?? 50;
    const off = row.params.offsetDollars ?? 0;
    return off ? `Qty: ${pct}% · $${off}` : `Qty: ${pct}%`;
  }
  if (
    row.kind === 'buy_market'
    || row.kind === 'buy_limit_ask_offset'
    || row.kind === 'sell_limit_bid_offset'
  ) {
    return `Qty: ${row.params.shares ?? 100}`;
  }
  if (row.kind === 'exit_pos' || row.kind === 'cancel_and_exit') return 'Position';
  if (row.kind === 'cancel_symbol') return 'Symbol open';
  if (row.kind === 'cancel_all_orders') return 'All stocks';
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
    case 'cancel_all_orders':
      return 'Cancel every working order on the connected account (all symbols). Confirms first.';
    case 'cancel_and_exit':
      return 'Cancel open orders, then flatten the position at market.';
    case 'exit_pos':
      return 'Flatten the full position at market.';
    case 'exit_pos_pct':
      return `Exit ${row.params.percent ?? 50}% of the position at market.`;
    case 'buy_market':
      return `Place a BUY market for ${row.params.shares ?? 1} whole share(s). Confirms; never opens a short.`;
    case 'buy_limit_ask_offset':
      return `Place a BUY limit at Ask + $${row.params.offsetDollars ?? 0.05}, size ${row.params.shares ?? 100}.`;
    case 'sell_limit_bid_offset':
      return `Place a SELL limit at Bid - $${row.params.offsetDollars ?? 0.05}, size ${row.params.shares ?? 100}.`;
    case 'sell_pos_pct_ask':
      return `Sell ${row.params.percent ?? 50}% of a long at Ask (limit). Long-only; whole shares; needs L2.`;
    case 'sell_pos_pct_bid_offset':
      return `Sell ${row.params.percent ?? 50}% of a long at Bid - $${row.params.offsetDollars ?? 0.03} (limit). Long-only; needs L2.`;
    default:
      return NOVA_ACTION_KIND_LABELS[row.kind];
  }
}
