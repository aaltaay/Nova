/**
 * Suggest a typed Nova Action from a DAS command row (Phase G3).
 * Never executes the DAS script — only proposes a mapped intent.
 */

import {
  NOVA_ACTION_DEFAULT_OFFSET_DOLLARS,
  NOVA_ACTION_DEFAULT_SHARES,
  NOVA_ACTION_KIND_LABELS,
  type NovaActionKind,
} from '../constants';
import { DAS_SHORT_NEEDS_PRICE, DAS_SHORT_STOP_NOTE } from '../constantGroups/short_ticket';
import { tokenizeDasCommand } from './dasCommandParser';
import type { NovaActionParams, NovaActionRecord } from './novaActionTypes';
import type { HotkeyRecord } from './types';

export type MapSuggestion =
  | {
    ok: true;
    kind: NovaActionKind;
    params: NovaActionParams;
    name: string;
    /** What the mapping leaves out or changes, said before it is created (a DAS short's stop trigger). */
    note?: string;
  }
  | { ok: false; reason: string };

function parseShareLiteral(value: string | undefined): number | null {
  if (!value) return null;
  const n = Number(value.trim());
  return Number.isFinite(n) && n > 0 ? n : null;
}

function parsePosPercent(value: string | undefined): number | null {
  if (!value) return null;
  const m = value.match(/pos\s*\*\s*(0?\.\d+|\d+(?:\.\d+)?)/i);
  if (!m) return null;
  let pct = Number(m[1]);
  if (!Number.isFinite(pct) || pct <= 0) return null;
  if (pct <= 1) pct *= 100;
  if (pct > 100) return null;
  return Math.round(pct);
}

function priceIsAskOffset(value: string | undefined): boolean {
  return Boolean(value && /ask\s*\+/i.test(value));
}

function priceIsBidOffset(value: string | undefined): boolean {
  return Boolean(value && /bid\s*-/i.test(value));
}

function parseOffsetDollars(value: string | undefined): number {
  if (!value) return NOVA_ACTION_DEFAULT_OFFSET_DOLLARS;
  const m = value.match(/(?:ask|bid)\s*[+-]\s*(\d+(?:\.\d+)?)/i);
  if (!m) return NOVA_ACTION_DEFAULT_OFFSET_DOLLARS;
  const n = Number(m[1]);
  return Number.isFinite(n) && n >= 0 ? n : NOVA_ACTION_DEFAULT_OFFSET_DOLLARS;
}

/** "Bid+0.01" -> 0.01, "Ask-0.02" -> -0.02, "Bid" -> 0; null when the price is not the bid or the ask. */
function parseSignedBookOffset(value: string | undefined): { base: 'bid' | 'ask'; offset: number } | null {
  const m = value?.trim().match(/^(bid|ask)\s*(?:([+-])\s*(\d+(?:\.\d+)?))?$/i);
  if (!m) return null;
  const n = m[3] ? Number(m[3]) : 0;
  if (!Number.isFinite(n)) return null;
  return { base: m[1].toLowerCase() as 'bid' | 'ask', offset: m[2] === '-' ? -n : n };
}

/**
 * A DAS short (`SHORT=Send`, ADR 048): a Short hotkey at the Bid or the Ask plus its offset. Its buy stop is the
 * hotkey's own offset (Settings > Trade's to start): a DAS stop trigger is not run, and the mapping says so.
 */
function suggestDasShort(command: string, shares: number | null, price: string | undefined): MapSuggestion {
  const book = parseSignedBookOffset(price);
  if (!book) return { ok: false, reason: DAS_SHORT_NEEDS_PRICE };
  const kind: NovaActionKind = book.base === 'bid' ? 'short_limit_bid_offset' : 'short_limit_ask_offset';
  return {
    ok: true,
    kind,
    params: { shares: shares ?? NOVA_ACTION_DEFAULT_SHARES, offsetDollars: book.offset },
    name: NOVA_ACTION_KIND_LABELS[kind],
    ...(/triggerorder/i.test(command) ? { note: DAS_SHORT_STOP_NOTE } : {}),
  };
}

/** Infer the best Nova Action kind + params from a DAS command string. */
export function suggestNovaActionFromDas(command: string): MapSuggestion {
  const tokens = tokenizeDasCommand(command);
  if (tokens.length === 0) {
    return { ok: false, reason: 'Command is empty' };
  }

  const shortSend = tokens.some(
    (t) => (t.kind === 'action' || t.kind === 'assignment')
      && t.name.toUpperCase() === 'SHORT'
      && (!t.value || t.value.toUpperCase() === 'SEND'),
  );
  if (shortSend) {
    const shareTok = tokens.find((t) => t.kind === 'assignment' && t.name.toUpperCase() === 'SHARE');
    const priceTok = tokens.find((t) => t.kind === 'assignment' && t.name.toUpperCase() === 'PRICE');
    return suggestDasShort(command, parseShareLiteral(shareTok?.value), priceTok?.value);
  }

  // Reject complex OTO scripts before any BUY/SELL heuristic (TriggerOrder=... is not a token.kind).
  const rawLower = command.toLowerCase();
  if (
    rawLower.includes('triggerorder')
    || tokens.some((t) => t.kind === 'trigger' || t.name.toUpperCase() === 'TRIGGERORDER')
  ) {
    return {
      ok: false,
      reason: 'OTO / TriggerOrder needs backend support — cannot map yet',
    };
  }

  const hasCancel = tokens.some((t) => t.kind === 'cancel');
  if (hasCancel) {
    return {
      ok: true,
      kind: 'cancel_symbol',
      params: {},
      name: NOVA_ACTION_KIND_LABELS.cancel_symbol,
    };
  }

  const shareTok = tokens.find(
    (t) => t.kind === 'assignment' && t.name.toUpperCase() === 'SHARE',
  );
  const priceTok = tokens.find(
    (t) => t.kind === 'assignment' && t.name.toUpperCase() === 'PRICE',
  );
  const buySend = tokens.some(
    (t) => t.kind === 'action'
      && t.name.toUpperCase() === 'BUY'
      && (t.value?.toUpperCase() === 'SEND' || !t.value),
  );
  const sellSend = tokens.some(
    (t) => t.kind === 'action'
      && t.name.toUpperCase() === 'SELL'
      && (t.value?.toUpperCase() === 'SEND' || !t.value),
  );
  // Also accept BUY=Send / SELL=Send as assignment-style in some exports
  const buyAssign = tokens.some(
    (t) => t.kind === 'assignment'
      && t.name.toUpperCase() === 'BUY'
      && t.value?.toUpperCase() === 'SEND',
  );
  const sellAssign = tokens.some(
    (t) => t.kind === 'assignment'
      && t.name.toUpperCase() === 'SELL'
      && t.value?.toUpperCase() === 'SEND',
  );
  const isBuy = buySend || buyAssign;
  const isSell = sellSend || sellAssign;

  const shareVal = shareTok?.value ?? '';
  const posPct = parsePosPercent(shareVal);
  const shareLit = parseShareLiteral(shareVal);
  const isFullPos = /^\s*pos\s*$/i.test(shareVal);

  if (isSell && (isFullPos || /^pos$/i.test(shareVal.trim()))) {
    return {
      ok: true,
      kind: 'exit_pos',
      params: {},
      name: NOVA_ACTION_KIND_LABELS.exit_pos,
    };
  }
  // A BUY of the whole position is DAS's cover (ADR 048): at Ask + offset, else all of it at market.
  if (isBuy && isFullPos) {
    const kind: NovaActionKind = priceIsAskOffset(priceTok?.value) ? 'cover_limit_ask_offset' : 'cover_pos';
    return {
      ok: true,
      kind,
      params: kind === 'cover_limit_ask_offset' ? { offsetDollars: parseOffsetDollars(priceTok?.value) } : {},
      name: NOVA_ACTION_KIND_LABELS[kind],
    };
  }
  if ((isSell || isBuy) && posPct != null) {
    return {
      ok: true,
      kind: 'exit_pos_pct',
      params: { percent: posPct },
      name: `Exit ${posPct}%`,
    };
  }

  if (isBuy && priceIsAskOffset(priceTok?.value)) {
    return {
      ok: true,
      kind: 'buy_limit_ask_offset',
      params: {
        shares: shareLit ?? NOVA_ACTION_DEFAULT_SHARES,
        offsetDollars: parseOffsetDollars(priceTok?.value),
      },
      name: NOVA_ACTION_KIND_LABELS.buy_limit_ask_offset,
    };
  }
  if (isSell && priceIsAskOffset(priceTok?.value)) {
    return {
      ok: true,
      kind: 'sell_limit_ask_offset',
      params: {
        shares: shareLit ?? NOVA_ACTION_DEFAULT_SHARES,
        offsetDollars: parseOffsetDollars(priceTok?.value),
      },
      name: NOVA_ACTION_KIND_LABELS.sell_limit_ask_offset,
    };
  }
  if (isSell && priceIsBidOffset(priceTok?.value)) {
    return {
      ok: true,
      kind: 'sell_limit_bid_offset',
      params: {
        shares: shareLit ?? NOVA_ACTION_DEFAULT_SHARES,
        offsetDollars: parseOffsetDollars(priceTok?.value),
      },
      name: NOVA_ACTION_KIND_LABELS.sell_limit_bid_offset,
    };
  }

  return {
    ok: false,
    reason: 'No matching Nova Action for this DAS command',
  };
}

let _mapIdSeq = 0;

export function resetMapIdSeqForTests(): void {
  _mapIdSeq = 0;
}

/** Build a new NovaActionRecord from a DAS HotkeyRecord (suggestion must be ok). */
export function buildMappedNovaAction(
  record: HotkeyRecord,
  suggestion: Extract<MapSuggestion, { ok: true }>,
): NovaActionRecord {
  _mapIdSeq += 1;
  return {
    id: `mapped_${record.id}_${_mapIdSeq}`,
    name: record.name || suggestion.name,
    kind: suggestion.kind,
    key: { ...record.key },
    params: { ...suggestion.params },
    enabled: false,
    showButton: false,
  };
}
