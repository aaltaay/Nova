// Single-snapshot Level 2 heuristic badges for the live DepthLadder (Phase F).
// Mirrors the single-snapshot math in backend/l2/features.py (bid_ask_imbalance,
// is_ask_stacked, is_bid_heavy) so the badges shown here match what gets
// recorded/labeled server-side. Display-only — never feeds the executor.
// See Automation-Strategy-Backbone.md section 3.
import { L2_ASK_STACKED_RATIO, L2_BID_HEAVY_RATIO, L2_SPREAD_WIDE_DOLLARS } from '../constants';
import type { DepthBook } from './types';

function totalSize(levels: DepthBook['bids'] | DepthBook['asks']): number {
  return levels.reduce((sum, level) => sum + (level.size || 0), 0);
}

export interface L2Heuristics {
  askStacked: boolean;
  bidHeavy: boolean;
  wideSpread: boolean;
}

export function computeL2Heuristics(book: DepthBook): L2Heuristics {
  const bidTotal = totalSize(book.bids);
  const askTotal = totalSize(book.asks);

  const askStacked = askTotal > 0 && (bidTotal <= 0 || askTotal >= bidTotal * L2_ASK_STACKED_RATIO);
  const bidHeavy = bidTotal > 0 && (askTotal <= 0 || bidTotal >= askTotal * L2_BID_HEAVY_RATIO);

  const bestBid = book.bids[0]?.price;
  const bestAsk = book.asks[0]?.price;
  const wideSpread =
    bestBid != null && bestAsk != null && bestAsk - bestBid >= L2_SPREAD_WIDE_DOLLARS;

  return { askStacked, bidHeavy, wideSpread };
}
