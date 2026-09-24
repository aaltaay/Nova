/**
 * What each side and order type does, in plain words, for the ticket's hover
 * card (OrderExplainerCard.tsx; operator ask 2026-09-24: "explain what each one
 * does when I hover ... very visual ... so I can understand").
 *
 * Every line here must stay true of Nova's ticket: Sell only reduces a
 * position (no short entries), Market is refused outside regular hours
 * (`execution/session_gate.py`), a trailing stop's size is the Trail $ field.
 */
import type { ManualOrderType } from './orderEntry';

export type OrderExplainerKind = 'buy' | 'sell' | ManualOrderType;

/** The colour a card, its icon and its example marks are drawn in. */
export type OrderExplainerTone = 'buy' | 'sell' | 'limit' | 'market' | 'stop';

/** A mark in the example's legend: a fill dot or the stop's trigger ring. */
export interface OrderExplainerMark {
  mark: 'buy' | 'sell' | 'trigger';
  text: string;
}

export interface OrderExplainer {
  title: string;
  /** Side or order type -- the small chip beside the title. */
  group: string;
  tone: OrderExplainerTone;
  /**
   * The one sentence; `strong` parts are the words to catch at a glance, in the
   * card's colour or in their own `tone` (a stop limit's "limit" is the limit's blue).
   */
  summary: readonly (string | { strong: string; tone?: OrderExplainerTone })[];
  /** What the picture shows ("Example: sell stop"). */
  caption: string;
  legend: readonly OrderExplainerMark[];
  facts: readonly string[];
}

const SIDE = 'Side';
const ORDER_TYPE = 'Order type';

export const ORDER_EXPLAINERS: Readonly<Record<OrderExplainerKind, OrderExplainer>> = {
  buy: {
    title: 'Buy',
    group: SIDE,
    tone: 'buy',
    summary: ['Buy shares. You make money if the price goes ', { strong: 'up' }, ' after you buy.'],
    caption: 'Example: buy, then the price rises',
    legend: [{ mark: 'buy', text: 'you buy' }],
    facts: [
      'Opens a position, or adds to one you already hold',
      'How it fills is the order type: Limit, Market or Stop',
    ],
  },
  sell: {
    title: 'Sell',
    group: SIDE,
    tone: 'sell',
    summary: ['Sell shares you own. Your gain or loss becomes ', { strong: 'final' }, '.'],
    caption: 'Example: bought low, sold higher',
    legend: [
      { mark: 'buy', text: 'you bought' },
      { mark: 'sell', text: 'you sell' },
    ],
    facts: [
      'Closes or trims your position',
      'Only shares you hold: Nova does not open short positions yet',
    ],
  },
  LMT: {
    title: 'Limit order',
    group: ORDER_TYPE,
    tone: 'limit',
    summary: [
      'You name the ',
      { strong: 'worst price' },
      " you'll accept. It fills there or better, or it waits.",
    ],
    caption: 'Example: buy limit under the price',
    legend: [{ mark: 'buy', text: 'fills at your limit or lower' }],
    facts: [
      'Buy limit: fills at your price or lower',
      'Sell limit: fills at your price or higher',
      'Never fills if the price does not come to you',
    ],
  },
  MKT: {
    title: 'Market order',
    group: ORDER_TYPE,
    tone: 'market',
    summary: ['Fills ', { strong: 'right now' }, ' at the best price on offer.'],
    caption: 'Example: the quote right now',
    legend: [
      { mark: 'buy', text: 'a buy fills at the ask' },
      { mark: 'sell', text: 'a sell fills at the bid' },
    ],
    facts: [
      'Speed first: it fills almost every time, at once',
      'The price is not promised: on a thin or fast stock it can fill far from the last trade',
      'Regular hours only (9:30-4:00 ET)',
    ],
  },
  STP: {
    title: 'Stop order',
    group: ORDER_TYPE,
    tone: 'stop',
    summary: [
      'Waits until the price ',
      { strong: 'reaches your stop' },
      ', then becomes a market order.',
    ],
    caption: 'Example: sell stop under the price',
    legend: [
      { mark: 'trigger', text: 'price reaches the stop' },
      { mark: 'sell', text: 'sells at market' },
    ],
    facts: [
      'Sell stop under your entry: caps a loss',
      'Buy stop above the price: catches a breakout',
      'Once it fires it is a market order, so the fill can slip past your stop',
    ],
  },
  'STP LMT': {
    title: 'Stop limit order',
    group: ORDER_TYPE,
    tone: 'stop',
    summary: [
      'Waits for your ',
      { strong: 'stop' },
      ', then becomes a ',
      { strong: 'limit', tone: 'limit' },
      ' order: it never fills worse than your limit.',
    ],
    caption: 'Example: sell stop limit',
    legend: [
      { mark: 'trigger', text: 'price reaches the stop' },
      { mark: 'sell', text: 'fills at the limit or better' },
    ],
    facts: [
      'Two prices: the stop wakes it up, the limit caps the fill',
      'No bad fill in a sudden drop',
      'If the price jumps past your limit it may not fill at all, and you stay in the trade',
    ],
  },
  TRAIL: {
    title: 'Trailing stop order',
    group: ORDER_TYPE,
    tone: 'stop',
    summary: [
      'A stop that ',
      { strong: 'follows the price up' },
      ' by your Trail $ and never moves back down.',
    ],
    caption: 'Example: sell trailing stop',
    legend: [
      { mark: 'trigger', text: 'price falls Trail $ from its high' },
      { mark: 'sell', text: 'sells at market' },
    ],
    facts: [
      'Sell trail: the stop sits Trail $ under the highest price since you placed it',
      'Locks in more gain as the stock runs',
      'Once it fires it is a market order, so the fill can slip',
    ],
  },
};
