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
import { tokenizeDasCommand } from './dasCommandParser';
import type { NovaActionParams, NovaActionRecord } from './novaActionTypes';
import type { HotkeyRecord } from './types';

export type MapSuggestion =
  | {
    ok: true;
    kind: NovaActionKind;
    params: NovaActionParams;
    name: string;
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

/** Infer the best Nova Action kind + params from a DAS command string. */
export function suggestNovaActionFromDas(command: string): MapSuggestion {
  const tokens = tokenizeDasCommand(command);
  if (tokens.length === 0) {
    return { ok: false, reason: 'Command is empty' };
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
