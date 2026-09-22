/**
 * What the Account page can state on Live from IBKR's own order rows (QA W17,
 * 2026-09-22). Live has no practice history, so "Fills 0 · No fills in this
 * range" and "Commissions today —" sat beside three filled IBKR orders whose
 * commissions the drawer listed. IBKR's session orders carry each order's
 * filled size, average fill price and CommissionReport sum: the Fills tab
 * shows one row per filled order at that average, and commissions today add
 * up what IBKR reported -- a dash while a filled order still has no report,
 * never a guess. Pure.
 */
import type { IbkrOrder } from '../ibkr/types';
import { plausiblePrice } from '../ibkr/orderDisplay';
import { uniqueOrders } from '../ibkr/orderIdentity';
import type { HistoryFill } from './accountHistoryTypes';

const finite = (n: number | null | undefined): number | null =>
  typeof n !== 'number' || !Number.isFinite(n) ? null : n;

/** An order IBKR reports as (at least partly) filled, with a real average price. */
export function liveFilled(order: IbkrOrder): boolean {
  const qty = finite(order.filled_qty);
  return qty != null && qty > 0 && plausiblePrice(order.avg_fill_price) != null;
}

/**
 * Commissions today on Live: the CommissionReport sums on the session's
 * filled orders. Zero when nothing filled; null while any filled order has
 * no report yet, so the row never understates the day's costs.
 */
export function liveCommissionsToday(orders: readonly IbkrOrder[]): number | null {
  let total = 0;
  for (const order of uniqueOrders([...orders])) {
    const commission = finite(order.commission);
    if (liveFilled(order) && commission == null) return null;
    if (commission != null) total += Math.abs(commission);
  }
  return total;
}

/** One Fills-tab row, whichever account answered. */
export interface AccountFillRow {
  key: string;
  ts: number | null;
  orderId: number;
  symbol: string;
  side: 'BUY' | 'SELL';
  qty: number;
  price: number;
  commission: number | null;
  fees: number | null;
  source: string | null;
  botId: string | null;
  /** Nova's practice broker priced it (the est chip); an IBKR fill is not an estimate. */
  estimated: boolean;
}

function isoSeconds(iso: string | null | undefined): number | null {
  const ms = iso ? Date.parse(iso) : Number.NaN;
  return Number.isFinite(ms) ? ms / 1000 : null;
}

/** Practice Fills rows: every fill the ledger history holds, each an estimate. */
export function practiceFillRows(fills: readonly HistoryFill[]): AccountFillRow[] {
  return fills
    .map((f, index) => ({
      key: `practice-${f.order_id}-${f.ts}-${index}`,
      ts: f.ts,
      orderId: f.order_id,
      symbol: f.symbol,
      side: f.side,
      qty: f.qty,
      price: f.price,
      commission: f.commission,
      fees: f.fees,
      source: f.source,
      botId: f.bot_id,
      estimated: true,
    }))
    .sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0));
}

/** Live Fills rows: one per filled order at IBKR's average fill price, newest first. */
export function liveFillRows(orders: readonly IbkrOrder[]): AccountFillRow[] {
  return uniqueOrders([...orders])
    .filter(liveFilled)
    .map((order, index) => ({
      key: `live-${order.perm_id ?? order.order_id}-${index}`,
      ts: isoSeconds(order.filled_at ?? order.updated_at ?? order.submitted_at),
      orderId: order.order_id,
      symbol: order.symbol,
      side: order.side,
      qty: finite(order.filled_qty) ?? 0,
      price: plausiblePrice(order.avg_fill_price) ?? 0,
      commission: finite(order.commission),
      fees: null,
      source: order.source === 'ib_recovered' ? 'ibkr' : 'nova',
      botId: null,
      estimated: false,
    }))
    .sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0));
}
