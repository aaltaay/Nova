/**
 * Factory for a new user-created Nova Action (Create Customized Button).
 */

import {
  NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_BUY_MARKET_SHARES,
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
  NOVA_ACTION_DEFAULT_SHORT_OFFSET_DOLLARS,
  type NovaActionKind,
} from '../constants';
import type { NovaActionRecord } from './novaActionTypes';

export type CustomButtonSide = 'buy' | 'sell' | 'short';

export function kindsForSide(side: CustomButtonSide): NovaActionKind[] {
  if (side === 'buy') return ['buy_market', 'buy_limit_ask_offset'];
  // ADR 048: a short and its covers, each Short with its own buy stop.
  if (side === 'short') {
    return ['short_limit_bid_offset', 'short_limit_ask_offset', 'cover_limit_ask_offset', 'cover_pos'];
  }
  return [
    'sell_limit_bid_offset',
    'sell_limit_ask_offset',
    'sell_pos_pct_ask',
    'sell_pos_pct_bid_offset',
    'exit_pos',
    'exit_pos_pct',
    'cancel_symbol',
    'cancel_all_orders',
    'cancel_and_exit',
  ];
}

export function defaultKindForSide(side: CustomButtonSide): NovaActionKind {
  if (side === 'short') return 'short_limit_bid_offset';
  return side === 'buy' ? 'buy_market' : 'sell_pos_pct_ask';
}

export function createBlankNovaAction(
  name: string,
  kind: NovaActionKind,
  /** A Short hotkey's buy stop starts at the venue's Settings > Trade offset (ADR 048). */
  shortStopOffset?: number,
): NovaActionRecord {
  let params: NovaActionRecord['params'] = {};
  if (kind === 'exit_pos_pct') {
    params = { percent: 50 };
  } else if (kind === 'sell_pos_pct_ask') {
    params = { percent: 50, offsetDollars: 0 };
  } else if (kind === 'sell_pos_pct_bid_offset') {
    params = {
      percent: 50,
      offsetDollars: NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
    };
  } else if (kind === 'buy_market') {
    params = { shares: NOVA_ACTION_DEFAULT_BUY_MARKET_SHARES };
  } else if (
    kind === 'buy_limit_ask_offset'
    || kind === 'sell_limit_bid_offset'
    || kind === 'sell_limit_ask_offset'
  ) {
    params = {
      shares: NOVA_ACTION_DEFAULT_SHARES,
      offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
    };
  } else if (kind === 'short_limit_bid_offset' || kind === 'short_limit_ask_offset') {
    // A cent over the bid, or a cent under the ask: both above the bid, as SSR asks of a short.
    params = {
      shares: NOVA_ACTION_DEFAULT_SHARES,
      offsetDollars: kind === 'short_limit_bid_offset'
        ? NOVA_ACTION_DEFAULT_SHORT_OFFSET_DOLLARS
        : -NOVA_ACTION_DEFAULT_SHORT_OFFSET_DOLLARS,
      ...(shortStopOffset != null ? { stopOffsetDollars: shortStopOffset } : {}),
    };
  } else if (kind === 'cover_limit_ask_offset') {
    params = { offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS };
  }

  return {
    id: `nova-custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    name: name.trim() || 'Custom1',
    kind,
    key: { label: '', key: '' },
    params,
    enabled: true,
    showButton: true,
  };
}
