/**
 * Ledger table rows from the history payload: every fill with its cash
 * movement and the balance after it, the 04:00 ET rollovers, the starting
 * cash and the resets that archived earlier ledgers. Pure; newest first.
 *
 * The balance after a fill is the equity point the backend published for
 * that event (`equity[].cash`), never a running sum -- a bounded range holds
 * only part of the ledger, so a client-side sum would be a guess.
 */
import type { EquityPoint, HistoryFill, PracticeHistory } from './accountHistoryTypes';

export type LedgerRowKind = 'fill' | 'rollover' | 'start' | 'reset';

export interface LedgerRow {
  key: string;
  kind: LedgerRowKind;
  ts: number;
  fill: HistoryFill | null;
  /** Cash movement (signed); null for rows that move no money. */
  amount: number | null;
  /** Cash after the event; null when the payload does not carry it. */
  balance: number | null;
  /** Reset rows: the archived file and its realized. */
  archive: { file: string; realized: number } | null;
}

/** Signed cash movement of a fill: price x qty, less commission and fees. */
export function fillCashMovement(fill: HistoryFill): number {
  const gross = fill.qty * fill.price;
  const costs = fill.commission + fill.fees;
  return fill.side === 'BUY' ? -(gross + costs) : gross - costs;
}

/** Epoch seconds of an ISO timestamp, or null. */
export function isoToTs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

function inRange(ts: number | null, rangeStart: number | null): boolean {
  return ts != null && (rangeStart == null || ts >= rangeStart);
}

export function ledgerRows(history: PracticeHistory): LedgerRow[] {
  const rows: LedgerRow[] = [];
  const pointsByTs = new Map<number, EquityPoint[]>();
  for (const point of history.equity) {
    const list = pointsByTs.get(point.ts) ?? [];
    list.push(point);
    pointsByTs.set(point.ts, list);
  }
  const consumed = new Set<EquityPoint>();
  history.fills.forEach((fill, index) => {
    const point = pointsByTs.get(fill.ts)?.find((p) => !consumed.has(p)) ?? null;
    if (point) consumed.add(point);
    rows.push({
      key: `fill-${fill.order_id}-${fill.ts}-${index}`,
      kind: 'fill',
      ts: fill.ts,
      fill,
      amount: fillCashMovement(fill),
      balance: point?.cash ?? null,
      archive: null,
    });
  });
  history.equity.forEach((point, index) => {
    if (consumed.has(point)) return;
    rows.push({
      key: `rollover-${point.ts}-${index}`,
      kind: 'rollover',
      ts: point.ts,
      fill: null,
      amount: null,
      balance: point.cash,
      archive: null,
    });
  });
  const openedTs = isoToTs(history.ledger_opened_at);
  if (inRange(openedTs, history.range_start)) {
    rows.push({
      key: `start-${openedTs}`,
      kind: 'start',
      ts: openedTs as number,
      fill: null,
      amount: history.starting_cash,
      balance: history.starting_cash,
      archive: null,
    });
  }
  history.archives.forEach((archive, index) => {
    const closedTs = isoToTs(archive.closed_at);
    if (!inRange(closedTs, history.range_start)) return;
    rows.push({
      key: `reset-${archive.file}-${index}`,
      kind: 'reset',
      ts: closedTs as number,
      fill: null,
      amount: null,
      balance: null,
      archive: { file: archive.file, realized: archive.realized },
    });
  });
  const order: Record<LedgerRowKind, number> = { fill: 0, rollover: 1, start: 2, reset: 3 };
  return rows.sort((a, b) => b.ts - a.ts || order[a.kind] - order[b.kind]);
}
