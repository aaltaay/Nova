/**
 * Factory for a new user-created Nova Action (Create Customized Button).
 */

import {
  NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_BUY_MARKET_SHARES,
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
  type NovaActionKind,
} from '../constants';
import type { NovaActionRecord } from './novaActionTypes';

export type CustomButtonSide = 'buy' | 'sell';

export function kindsForSide(side: CustomButtonSide): NovaActionKind[] {
  if (side === 'buy') return ['buy_market', 'buy_limit_ask_offset'];
  return [
    'sell_limit_bid_offset',
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
  return side === 'buy' ? 'buy_market' : 'sell_pos_pct_ask';
}

export function createBlankNovaAction(
  name: string,
  kind: NovaActionKind,
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
  } else if (kind === 'buy_limit_ask_offset' || kind === 'sell_limit_bid_offset') {
    params = {
      shares: NOVA_ACTION_DEFAULT_SHARES,
      offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
    };
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
