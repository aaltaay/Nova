/**
 * Plan levels drawn in the Level 2 book (ADR 037): ENTRY, STOP and TARGET as thin separator rows
 * where each price sits among the shown levels. Pure: the book and the markers go in, each side's
 * markers with their place come out. A price deeper than the rows shown goes after them, marked as
 * beyond; nothing is drawn on an empty book.
 */
import type { DepthLevel } from './types';

export interface DepthMarker {
  id: string;
  price: number;
  label: string;
  color: string;
  /** An order stands behind it (a solid line); a plan's level only (dashed). */
  working: boolean;
  /** The side it joins inside the spread: a buy's entry and a stop with the bids, a sell's target with the asks. */
  rests: 'bid' | 'ask';
  /** What it is, on hover. */
  tip: string;
}

export interface PlacedMarker extends DepthMarker {
  /** Drawn before the shown row at this index (the number of rows: after the last one). */
  before: number;
  /** Past every row shown: the price is deeper in the book than the ladder reaches. */
  beyond: boolean;
}

const EPS = 1e-9;

/** Which column a marker belongs in: at or through the ask with the asks, at or under the bid with the
 * bids, and inside the spread where it would rest. Null when the book has no price on either side. */
export function markerSide(m: DepthMarker, bestBid: number | null, bestAsk: number | null): 'bid' | 'ask' | null {
  if (bestBid === null && bestAsk === null) return null;
  if (bestAsk !== null && m.price >= bestAsk - EPS) return 'ask';
  if (bestBid !== null && m.price <= bestBid + EPS) return 'bid';
  return m.rests;
}

/** Split the markers between the two columns of this book. */
export function splitMarkers(
  markers: readonly DepthMarker[],
  bids: readonly DepthLevel[],
  asks: readonly DepthLevel[],
): { bid: DepthMarker[]; ask: DepthMarker[] } {
  const bestBid = bids[0]?.price ?? null;
  const bestAsk = asks[0]?.price ?? null;
  const out: { bid: DepthMarker[]; ask: DepthMarker[] } = { bid: [], ask: [] };
  for (const m of markers) {
    if (!Number.isFinite(m.price)) continue;
    const side = markerSide(m, bestBid, bestAsk);
    if (side) out[side].push(m);
  }
  return out;
}

/**
 * Where each marker goes among one side's shown rows: bids run from the best price down, asks from the
 * best price up, and a marker follows every row at its price or better (a new order joins the back of
 * its price).
 */
export function placeMarkers(side: 'bid' | 'ask', rows: readonly DepthLevel[], markers: readonly DepthMarker[]): PlacedMarker[] {
  const worse = (rowPrice: number, price: number) => (side === 'bid' ? rowPrice < price - EPS : rowPrice > price + EPS);
  const placed = markers.map(m => {
    const at = rows.findIndex(r => worse(r.price, m.price));
    const before = at < 0 ? rows.length : at;
    const last = rows[rows.length - 1];
    const beyond = at < 0 && last !== undefined && Math.abs(last.price - m.price) > EPS;
    return { ...m, before, beyond };
  });
  // Several at one place: in the side's own price order.
  return placed.sort((a, b) => a.before - b.before || (side === 'bid' ? b.price - a.price : a.price - b.price));
}
