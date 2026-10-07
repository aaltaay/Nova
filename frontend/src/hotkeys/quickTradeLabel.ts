/**
 * Quick Trades as one row of icon-labelled buttons (approved redesign,
 * 2026-09-21): the short label under each icon is built from the action's
 * kind and params, so it can never drift from what the action does; the full
 * name stays the tooltip. Colour by kind lets the operator find Flatten under
 * stress: buys green, sells red, protective exits amber, cancels muted.
 */
import {
  QUICK_TRADES_SELL_ALL_LABEL,
  QUICK_TRADES_SHORT_LABELS,
} from '../constantGroups/trader_chrome';
import type { NovaActionKind } from '../constants';
import type { NovaActionParams } from './novaActionTypes';

export type QuickTradeTone = 'buy' | 'sell' | 'short' | 'protective' | 'cancel';

export function quickTradeTone(kind: NovaActionKind): QuickTradeTone {
  switch (kind) {
    case 'cancel_symbol':
    case 'cancel_all_orders':
    case 'clip_toggle':
    case 'clip_save_last':
      return 'cancel';
    case 'cancel_and_exit':
    case 'exit_pos':
    case 'exit_pos_pct':
    case 'cover_pos':
      return 'protective';
    case 'buy_market':
    case 'buy_limit_ask_offset':
    case 'cover_limit_ask_offset':
      return 'buy';
    // A short is orange and its label always says SS (ADR 048): never the colour alone.
    case 'short_limit_bid_offset':
    case 'short_limit_ask_offset':
      return 'short';
    default:
      return 'sell';
  }
}

function cents(offsetDollars: number | undefined): string {
  if (offsetDollars == null || !Number.isFinite(offsetDollars)) return '';
  return String(Math.round(offsetDollars * 100));
}

/** "+1", "−5", "" for a signed offset in cents (a short's price may sit either side of the bid or ask). */
function signedCents(offsetDollars: number | undefined): string {
  if (offsetDollars == null || !Number.isFinite(offsetDollars)) return '';
  const c = Math.round(offsetDollars * 100);
  if (c === 0) return '';
  return c > 0 ? `+${c}` : `−${Math.abs(c)}`;
}

export function quickTradeShortLabel(
  kind: NovaActionKind,
  params: NovaActionParams,
): string {
  if (kind === 'sell_pos_pct_ask' && params.percent === 100) {
    return QUICK_TRADES_SELL_ALL_LABEL;
  }
  const template: string = QUICK_TRADES_SHORT_LABELS[kind];
  return template
    .replace('{n}', params.shares != null ? String(params.shares) : '')
    .replace('{p}', params.percent != null ? String(params.percent) : '')
    .replace('{c}', cents(params.offsetDollars))
    .replace('{s}', signedCents(params.offsetDollars))
    .replace(/\s+/g, ' ')
    .trim();
}

/** One piece of a short label, and whether a space separates it from the piece before. */
export interface QuickTradeLabelPiece {
  text: string;
  spaced: boolean;
}

/**
 * The short label cut where it may wrap (QA D14): at its spaces and after a
 * "+" that joins two words ("Cxl+Flat" -> "Cxl+" / "Flat") -- never inside a
 * word, which read "Cxl+Fl / at" and "Flatte / n" in the rail. "Ask+5" stays
 * whole: "+5" is an amount, not a second word.
 */
export function quickTradeLabelPieces(label: string): QuickTradeLabelPiece[] {
  const pieces: QuickTradeLabelPiece[] = [];
  label.split(' ').filter(Boolean).forEach((word, wordIndex) => {
    word.split(/(?<=\+)(?=\p{L})/u).forEach((text, partIndex) => {
      pieces.push({ text, spaced: wordIndex > 0 && partIndex === 0 });
    });
  });
  return pieces;
}
