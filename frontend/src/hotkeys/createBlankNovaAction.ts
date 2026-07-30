/**
 * Factory for a new user-created Nova Action (Create Customized Button).
 */

import {
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
  type NovaActionKind,
} from '../constants';
import type { NovaActionRecord } from './novaActionTypes';

export type CustomButtonSide = 'buy' | 'sell';

export function kindsForSide(side: CustomButtonSide): NovaActionKind[] {
  if (side === 'buy') return ['buy_limit_ask_offset'];
  return [
    'sell_limit_bid_offset',
    'exit_pos',
    'exit_pos_pct',
    'cancel_symbol',
    'cancel_and_exit',
  ];
}

export function defaultKindForSide(side: CustomButtonSide): NovaActionKind {
  return side === 'buy' ? 'buy_limit_ask_offset' : 'sell_limit_bid_offset';
}

export function createBlankNovaAction(
  name: string,
  kind: NovaActionKind,
): NovaActionRecord {
  const params =
    kind === 'exit_pos_pct'
      ? { percent: 50 }
      : kind === 'buy_limit_ask_offset' || kind === 'sell_limit_bid_offset'
        ? {
            shares: NOVA_ACTION_DEFAULT_SHARES,
            offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
          }
        : {};

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
