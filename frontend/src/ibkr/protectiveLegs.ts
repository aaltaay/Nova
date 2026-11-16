/**
 * #91 — the manual ticket's optional default take-profit / stop-loss.
 *
 * Pure. Given the Settings offsets and the ticket in front of the operator it
 * answers one question: does this order go out as a plain place, as a bracket
 * (through the same `execution.service.execute`), or not at all?
 *
 * The refusal cases are deliberate. A Market entry while the defaults are on
 * is refused rather than sent without a stop — the whole point of the setting
 * is a stop you cannot forget.
 *
 * Every venue takes the bracket the same way: Live sends it to IBKR, Paper
 * and Sim fill the same shape on the practice broker (#606), so the legs
 * attach whatever venue the desk is on.
 */
import { plainPrice, roundToTick } from '../utils/priceTick';
import {
  TICKET_LEGS_EXIT_NOTE,
  TICKET_LEGS_LIMIT_ONLY_ERROR,
  TICKET_LEGS_NO_PRICE_ERROR,
  TICKET_LEGS_OFFSET_ERROR,
} from '../constantGroups/trade_defaults';
import type { ManualOrderSide, ManualOrderType } from './orderEntry';
import type { TradeDefaultsPrefs } from '../settings';

export type ProtectiveLegsPlan =
  | { kind: 'none'; note: string | null }
  | {
      kind: 'attach';
      takeProfitPrice: number;
      stopLossPrice: number;
      note: string;
    }
  | { kind: 'refuse'; error: string };

export interface ProtectiveLegsInput {
  prefs: TradeDefaultsPrefs;
  side: ManualOrderSide;
  shortEntry: boolean;
  orderType: ManualOrderType;
  limitPrice: number | null;
  /** Broker position in this symbol; negative is short. */
  positionQty: number | null;
}

/** True when this ticket opens exposure rather than reducing it. */
export function isOpeningEntry(
  side: ManualOrderSide,
  shortEntry: boolean,
  positionQty: number | null,
): boolean {
  if (shortEntry) return side === 'SELL';
  if (side !== 'BUY') return false;
  // A BUY while short is a cover, not an entry: legs would re-open the short.
  return !(positionQty != null && positionQty < 0);
}

export function planProtectiveLegs(input: ProtectiveLegsInput): ProtectiveLegsPlan {
  const { prefs } = input;
  if (!prefs.protectiveLegs) return { kind: 'none', note: null };
  if (!isOpeningEntry(input.side, input.shortEntry, input.positionQty)) {
    return { kind: 'none', note: TICKET_LEGS_EXIT_NOTE };
  }
  if (input.orderType !== 'LMT') {
    return { kind: 'refuse', error: TICKET_LEGS_LIMIT_ONLY_ERROR };
  }
  const entry = input.limitPrice;
  if (entry == null || !Number.isFinite(entry) || entry <= 0) {
    return { kind: 'refuse', error: TICKET_LEGS_NO_PRICE_ERROR };
  }
  const up = (pct: number) => roundToTick(entry * (1 + pct / 100));
  const down = (pct: number) => roundToTick(entry * (1 - pct / 100));
  const takeProfitPrice = input.shortEntry
    ? down(prefs.takeProfitPct)
    : up(prefs.takeProfitPct);
  const stopLossPrice = input.shortEntry
    ? up(prefs.stopLossPct)
    : down(prefs.stopLossPct);

  // Rounding can collapse a small offset onto the entry. The backend refuses
  // that geometry (BRACKET_GEOMETRY); say so here instead of sending it.
  const ordered = input.shortEntry
    ? takeProfitPrice < entry && entry < stopLossPrice
    : stopLossPrice < entry && entry < takeProfitPrice;
  if (!ordered || stopLossPrice <= 0 || takeProfitPrice <= 0) {
    return { kind: 'refuse', error: TICKET_LEGS_OFFSET_ERROR };
  }
  return {
    kind: 'attach',
    takeProfitPrice,
    stopLossPrice,
    note:
      `Bracket: take profit $${plainPrice(takeProfitPrice)} · ` +
      `stop loss $${plainPrice(stopLossPrice)}`,
  };
}
