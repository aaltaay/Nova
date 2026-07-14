import {
  L2_DAS_TIER_ASK,
  L2_DAS_TIER_BID,
  TICKER_TRADE_DEPTH_LEVELS,
} from '../constants';
import type { DepthLevel } from './types';

/** Assign a DAS color-group index: same price → same tier; next price → next color. */
export function assignPriceTiers(levels: DepthLevel[]): number[] {
  const tiers: number[] = [];
  let tier = 0;
  let prev: number | null = null;
  for (const level of levels) {
    if (prev != null && level.price !== prev) tier += 1;
    tiers.push(tier);
    prev = level.price;
  }
  return tiers;
}

export function tierBackground(side: 'bid' | 'ask', tierIndex: number): string {
  const palette = side === 'bid' ? L2_DAS_TIER_BID : L2_DAS_TIER_ASK;
  return palette[tierIndex % palette.length] ?? palette[0];
}

/** Pad/truncate each side to a fixed montage height so columns stay aligned. */
export function padLevels(levels: DepthLevel[], rows = TICKER_TRADE_DEPTH_LEVELS): (DepthLevel | null)[] {
  const sliced = levels.slice(0, rows);
  const out: (DepthLevel | null)[] = [...sliced];
  while (out.length < rows) out.push(null);
  return out;
}

export function maxSize(levels: DepthLevel[]): number {
  let max = 0;
  for (const l of levels) {
    if (l.size > max) max = l.size;
  }
  return max;
}
