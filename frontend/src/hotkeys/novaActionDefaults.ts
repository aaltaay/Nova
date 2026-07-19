/**
 * Curated DAS-inspired default Nova Actions profile (Phase G3).
 */

import {
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
} from '../constants';
import { parseKeyChord } from './htkFormat';
import type { NovaActionRecord } from './novaActionTypes';

function chord(label: string) {
  return parseKeyChord(label);
}

/** Default executable set — modifiers keep fat-finger risk low. */
export function createDefaultNovaActions(): NovaActionRecord[] {
  return [
    {
      id: 'nova-cancel-symbol',
      name: 'Cancel symbol orders',
      kind: 'cancel_symbol',
      key: chord('Shift+Backspace'),
      params: {},
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-cancel-and-exit',
      name: 'Cancel + Flatten',
      kind: 'cancel_and_exit',
      key: chord('Ctrl+Shift+Backspace'),
      params: {},
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-exit-pos',
      name: 'Flatten position',
      kind: 'exit_pos',
      key: chord('Ctrl+PageUp'),
      params: {},
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-exit-50',
      name: 'Exit 50%',
      kind: 'exit_pos_pct',
      key: chord('Ctrl+Home'),
      params: { percent: 50 },
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-exit-25',
      name: 'Exit 25%',
      kind: 'exit_pos_pct',
      key: chord('Ctrl+Insert'),
      params: { percent: 25 },
      enabled: true,
      showButton: false,
    },
    {
      id: 'nova-buy-ask',
      name: `Buy Ask+${NOVA_ACTION_DEFAULT_OFFSET_DOLLARS} ${NOVA_ACTION_DEFAULT_SHARES}`,
      kind: 'buy_limit_ask_offset',
      key: chord('Ctrl+Shift+B'),
      params: {
        shares: NOVA_ACTION_DEFAULT_SHARES,
        offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
      },
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-sell-bid',
      name: `Sell Bid-${NOVA_ACTION_DEFAULT_OFFSET_DOLLARS} ${NOVA_ACTION_DEFAULT_SHARES}`,
      kind: 'sell_limit_bid_offset',
      key: chord('Alt+Shift+S'),
      params: {
        shares: NOVA_ACTION_DEFAULT_SHARES,
        offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
      },
      enabled: true,
      showButton: true,
    },
  ];
}
