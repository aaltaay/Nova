/**
 * The phone ticket's one-tap buttons, as the desk's own Nova Actions (hotkeys/runNovaAction).
 *
 * The phone decides nothing about an order. Each button is one of the desk's action kinds with its
 * numbers (shares, percent of the position, cents from the bid or ask), and `runNovaAction` does with it
 * exactly what the desk's hotkey does: the same gate, the same price read from Level 2, the same size
 * from the position, the same order body. What this file adds is the words on the button, read from the
 * same top of book -- a label, never the price the order goes out at.
 */
import {
  NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  type NovaActionKind,
} from '../../constants';
import type { NovaActionParams, NovaActionRecord } from '../../hotkeys/novaActionTypes';
import { buildLongExitPercent } from '../../ibkr/exitPosition';
import { plainPrice, roundToTick } from '../../utils/priceTick';

const NO_KEY = { label: '', key: '' };

function action(kind: NovaActionKind, name: string, params: NovaActionParams = {}): NovaActionRecord {
  return { id: `phone-${kind}`, name, kind, key: NO_KEY, params, enabled: true, showButton: false };
}

/** Buy at the market. */
export function buyMarket(shares: number): NovaActionRecord {
  return action('buy_market', `Buy ${shares} market`, { shares });
}

/** Buy with a limit a few cents over the Ask: fills now, and no higher than the limit. */
export function buyLimit(shares: number): NovaActionRecord {
  return action('buy_limit_ask_offset', `Buy ${shares} limit`, {
    shares, offsetDollars: NOVA_ACTION_DEFAULT_OFFSET_DOLLARS, outsideRth: true,
  });
}

/** Sell part of the long at the Ask: the order rests there until a buyer takes it. */
export function sellAtAsk(percent: number): NovaActionRecord {
  return action('sell_pos_pct_ask', percent === 100 ? 'Sell all at the Ask' : `Sell ${percent}% at the Ask`, { percent, offsetDollars: 0 });
}

/** Sell part of the long into the Bid: a limit a few cents under it, so it fills now. */
export function sellAtBid(percent: number): NovaActionRecord {
  return action('sell_pos_pct_bid_offset', percent === 100 ? 'Sell all at the Bid' : `Sell ${percent}% at the Bid`, {
    percent, offsetDollars: NOVA_ACTION_DEFAULT_BID_EXIT_OFFSET_DOLLARS,
  });
}

/** Cancel the stock's working orders, then close the whole position. Never held by the padlock. */
export function flatten(): NovaActionRecord {
  return action('cancel_and_exit', 'Flatten');
}

/** Cancel every working order, on every stock. Never held by the padlock. */
export function cancelAll(): NovaActionRecord {
  return action('cancel_all_orders', 'Cancel all orders');
}

/** The shares a Sell button would sell, or null when there is no long to sell that much of. */
export function sellShares(heldQty: number | null | undefined, percent: number): number | null {
  const built = buildLongExitPercent(heldQty, percent);
  return built.ok ? built.qty : null;
}

/** The limit a Buy limit tapped now would carry, for the button's words; null without an Ask. */
export function buyLimitPrice(ask: number | null | undefined): number | null {
  return ask != null && ask > 0 ? roundToTick(ask + NOVA_ACTION_DEFAULT_OFFSET_DOLLARS) : null;
}

export function priceWord(price: number | null | undefined): string {
  return price != null && Number.isFinite(price) && price > 0 ? plainPrice(price) : '—';
}

/** "+0.05": the cents a Buy limit adds to the Ask. */
export const BUY_LIMIT_OFFSET_WORD = `+${NOVA_ACTION_DEFAULT_OFFSET_DOLLARS.toFixed(2)}`;

/** The stepper's step for a share count: 1 under 10 shares, 10 under 100, then 100. */
export function qtyStep(qty: number): number {
  if (qty < 10) return 1;
  if (qty < 100) return 10;
  return 100;
}

/** One step up or down from `qty`, never under 1. A step down from a round number lands on the next one down. */
export function stepQty(qty: number, direction: 1 | -1): number {
  const from = Number.isFinite(qty) && qty > 0 ? Math.floor(qty) : 0;
  if (direction > 0) return from + qtyStep(from);
  const step = qtyStep(from - 1);
  return Math.max(1, from - step);
}
