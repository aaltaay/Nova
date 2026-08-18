/**
 * Curated DAS-inspired default Nova Actions profile (Phase G3)
 * plus Webull-style quick test bindings (nova-wb-*).
 */

import {
  NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_BUY_MARKET_SHARES,
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DESK_SHARES,
} from '../constants';
import { parseKeyChord } from './htkFormat';
import type { NovaActionRecord } from './novaActionTypes';

function chord(label: string) {
  return parseKeyChord(label);
}

/** Default executable set — modifiers keep fat-finger risk low; wb-* adds Webull chords. */
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
      name: `Buy 1 Ask+$${NOVA_ACTION_DEFAULT_OFFSET_DOLLARS} EH`,
      kind: 'buy_limit_ask_offset',
      key: chord('F1'),
      params: {
        shares: NOVA_ACTION_DESK_SHARES,
        offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
        outsideRth: true,
      },
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-sell-bid',
      name: `Sell 1 Bid-$${NOVA_ACTION_DEFAULT_OFFSET_DOLLARS} EH`,
      kind: 'sell_limit_bid_offset',
      key: chord('F2'),
      params: {
        shares: NOVA_ACTION_DESK_SHARES,
        offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
        outsideRth: true,
      },
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-sell-ask',
      name: `Sell 1 Ask+$${NOVA_ACTION_DEFAULT_OFFSET_DOLLARS} EH`,
      kind: 'sell_limit_ask_offset',
      key: chord('F5'),
      params: {
        shares: NOVA_ACTION_DESK_SHARES,
        offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
        outsideRth: true,
      },
      enabled: true,
      showButton: true,
    },
    // Webull-style quick set (paper/live same path; confirm always unless user pref skips)
    {
      id: 'nova-wb-buy-1',
      name: `Buy ${NOVA_ACTION_DEFAULT_BUY_MARKET_SHARES} @MKT`,
      kind: 'buy_market',
      key: chord('Ctrl+1'),
      params: { shares: NOVA_ACTION_DEFAULT_BUY_MARKET_SHARES },
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-wb-cancel-all',
      name: 'Cancel All (all stocks)',
      kind: 'cancel_all_orders',
      key: chord('Ctrl+Z'),
      params: {},
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-wb-sell-100-ask',
      name: 'Sell 100% @ASK',
      kind: 'sell_pos_pct_ask',
      key: chord('Ctrl+4'),
      params: { percent: 100, offsetDollars: 0 },
      enabled: true,
      showButton: true,
    },
    {
      id: 'nova-wb-sell-50-ask',
      name: 'Sell 50% @ASK',
      kind: 'sell_pos_pct_ask',
      key: chord('Ctrl+5'),
      params: { percent: 50, offsetDollars: 0 },
      enabled: true,
      showButton: false,
    },
    {
      id: 'nova-wb-sell-25-ask',
      name: 'Sell 25% @ASK',
      kind: 'sell_pos_pct_ask',
      key: chord('Ctrl+6'),
      params: { percent: 25, offsetDollars: 0 },
      enabled: true,
      showButton: false,
    },
    {
      id: 'nova-wb-sell-50-bid',
      name: `Sell 50% @BID -$${NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS}`,
      kind: 'sell_pos_pct_bid_offset',
      key: chord('Ctrl+2'),
      params: {
        percent: 50,
        offsetDollars: NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
      },
      enabled: true,
      showButton: false,
    },
    {
      id: 'nova-wb-sell-25-bid',
      name: `Sell 25% @BID -$${NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS}`,
      kind: 'sell_pos_pct_bid_offset',
      key: chord('Ctrl+3'),
      params: {
        percent: 25,
        offsetDollars: NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
      },
      enabled: true,
      showButton: false,
    },
  ];
}
