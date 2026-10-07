/**
 * The Side column of the Orders and Positions tables (ADR 048 decision 6): which side of the
 * position an order trades, and what it does to it.
 *
 * Read from the row's own record, never guessed: `position_side` / `effect` (a practice row stamps
 * them when it is placed; a Live row takes them from Nova's execution record, or from the position
 * now while an order placed outside Nova is still working). A row without them says the side is
 * not known.
 */
import type { ColumnMeta } from './orderTableColumns';
import type { IbkrOrder, IbkrPosition } from './types';

export type SideTone = 'long' | 'short' | 'unknown';

export type OrderSideWords = {
  /** LONG / SHORT, or ? when not known. */
  tag: string;
  tone: SideTone;
  /** Buy / Sell. */
  action: string;
  /** "opens" / "closes", or null when not known. */
  effect: 'opens' | 'closes' | null;
  /** The cell's hover. */
  tip: string;
  /** A plain-text label for tests and sorting: "Short · Sell · opens". */
  label: string;
};

const TIPS: Record<string, string> = {
  'long:BUY': 'Long · Buy: buys shares you will own. Opens or adds to a long.',
  'long:SELL': 'Long · Sell: sells shares you own. Closes or trims a long.',
  'short:SELL':
    'Short · Sell: sells shares borrowed through IBKR. Opens or adds to a short (IBKR: a short sale).',
  'short:BUY': 'Short · Buy: buys the borrowed shares back. Closes or trims a short (IBKR: buy to cover).',
};

const UNKNOWN_TIP =
  "Side not known: Nova has no record of sending this order, and the position when it was placed " +
  'is not known. Nova never guesses which side an order traded.';

export function orderSideWords(
  order: Pick<IbkrOrder, 'side' | 'position_side' | 'effect' | 'short_entry'>,
): OrderSideWords {
  const action = order.side === 'BUY' ? 'Buy' : 'Sell';
  const side = order.position_side ?? (order.short_entry === true && order.side === 'SELL' ? 'short' : null);
  const effect = order.effect ?? (order.short_entry === true && order.side === 'SELL' ? 'opens' : null);
  if (side !== 'long' && side !== 'short') {
    return { tag: '?', tone: 'unknown', action, effect: null, tip: UNKNOWN_TIP, label: `? · ${action}` };
  }
  const tag = side === 'short' ? 'SHORT' : 'LONG';
  const label = `${side === 'short' ? 'Short' : 'Long'} · ${action}${effect ? ` · ${effect}` : ''}`;
  return { tag, tone: side, action, effect, tip: TIPS[`${side}:${order.side}`] ?? UNKNOWN_TIP, label };
}

export type PositionSideWords = { tag: string; tone: SideTone; note: string; tip: string };

export function positionSideWords(position: Pick<IbkrPosition, 'qty' | 'position_side'>): PositionSideWords {
  const side = position.position_side ?? (position.qty < 0 ? 'short' : position.qty > 0 ? 'long' : null);
  if (side === 'short') {
    return {
      tag: 'SHORT',
      tone: 'short',
      note: 'borrowed · buy back to cover',
      tip: 'Short: shares borrowed through IBKR and sold. Buy them back to cover; Nova covers what is left at 15:55 ET.',
    };
  }
  if (side === 'long') {
    return { tag: 'LONG', tone: 'long', note: 'shares you own', tip: 'Long: shares you own.' };
  }
  return { tag: '?', tone: 'unknown', note: '', tip: 'Side not known.' };
}

/** "Flatten 300" for a long; "Flatten 416 (cover)" for a short, whose flatten buys the borrowed shares back. */
export function flattenLabel(qty: number, base: string): string {
  return qty < 0 ? `${base} ${Math.abs(qty)} (cover)` : `${base} ${Math.abs(qty)}`;
}

export function liquidationTitle(p: Pick<IbkrPosition, 'liquidation_price' | 'liquidation_source'>): string {
  if (p.liquidation_price == null) {
    return 'Liquidation price: not known, or never by this position\'s price alone (a long the account pays for in full).';
  }
  const source = p.liquidation_source ? ` Margin: ${p.liquidation_source}.` : '';
  return (
    `IBKR would liquidate this position near ${p.liquidation_price.toFixed(2)}: where the account's equity ` +
    `falls to its maintenance requirement, every other position held still.${source}`
  );
}

/** Sort key: long before short, then opens before closes; '' (sorts last) when the side is not known. */
export function orderSideSortKey(order: Pick<IbkrOrder, 'side' | 'position_side' | 'effect' | 'short_entry'>): string {
  const words = orderSideWords(order);
  if (words.tone === 'unknown') return '';
  return `${words.tone === 'long' ? '1' : '2'}${words.effect === 'opens' ? '1' : '2'}${words.action}`;
}

export const SIDE_COLUMN_META: ColumnMeta = {
  id: 'side',
  label: 'Side',
  className: 'ibkr-col--text ibkr-col--side',
  title:
    'Which side of the position the order trades (LONG or SHORT) and what it does to it (opens or closes). ' +
    'Hover a cell for more · Drag headers to reorder',
};

export const POSITION_SIDE_META: ColumnMeta = {
  id: 'side',
  label: 'Side',
  className: 'ibkr-col--text ibkr-col--side',
  title: 'LONG: shares you own · SHORT: borrowed, buy back to cover',
};

export const LIQUIDATION_META: ColumnMeta = {
  id: 'liq',
  label: 'Liq. price',
  className: 'ibkr-col--num ibkr-col--liq',
  title: 'Where IBKR would liquidate the position: IBKR\'s what-if margin for the stock, else the published rules',
};
