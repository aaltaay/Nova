/**
 * Hidden sellers and buyers on the Level 2 ladder (ADR 033 amendment, 2026-09-30). Pure: the book watcher's
 * words (bookWatch.ts folds them from the depth socket) go in; each side's marks and outlined rows come out.
 * A mark says what traded at a price that held beyond the most the book ever showed there -- one reserve
 * (iceberg) order and several orders refilling the price look the same. A description, never a detection:
 * the watcher decides (backend/book_watch/hidden.py); nothing here infers one.
 */
import {
  L2_HIDDEN_NOTE,
  L2_HIDDEN_READ_BUYER,
  L2_HIDDEN_READ_SELLER,
  L2_HIDDEN_STALE_MS,
  L2_PULL_MARK_SHOW_MS,
} from '../constants';
import {
  markPrice,
  markShares,
  markWhole,
  opacityAt,
  priceKey,
  type BookSide,
  type BookWatchState,
  type HeldHidden,
  type PulledHere,
  type PullMark,
} from './bookWatch';
import { markerPlace } from './depthMarkers';
import type { DepthLevel } from './types';

const WHO: Record<BookSide, string> = { ask: 'Hidden seller', bid: 'Hidden buyer' };
/** How a stretch ended, on its chip. `faded`: the prints there stopped, and the price held. */
const END_CHIP: Record<string, string> = { broke: 'broke', faded: 'held', moved: 'moved', auction: 'cross', reset: 'reset' };

function endLine(h: HeldHidden): string {
  const p = markPrice(h.price);
  switch (h.state) {
    case 'holding':
      return `It still holds: nothing has traded through ${p}.`;
    case 'broke':
      return `Then a print went through ${p}.`;
    case 'faded':
      return `Then the prints there stopped, and ${p} held.`;
    case 'moved':
      return h.side === 'ask' ? 'Then the offer came down.' : 'Then the bid went up.';
    case 'auction':
      return 'A cross print ended it.';
    default:
      return 'The book restarted.';
  }
}

/** The hover for a hidden seller or buyer: what traded against what showed, how it stands, and what it has meant. */
export function hiddenTip(h: HeldHidden): { title: string; tip: string } {
  const lines = [
    `${markWhole(h.printed)} traded at ${markPrice(h.price)} over ${Math.round(h.heldSec)} s; the book never showed more than ${markWhole(h.shownMax)} there.`,
    endLine(h),
  ];
  if (h.refills > 0) lines.push(`The size shown there came back ${h.refills} time${h.refills === 1 ? '' : 's'}.`);
  lines.push(h.side === 'ask' ? L2_HIDDEN_READ_SELLER : L2_HIDDEN_READ_BUYER, L2_HIDDEN_NOTE);
  return { title: `${WHO[h.side]} at ${markPrice(h.price)}: ${markWhole(h.hidden)} beyond what it showed`, tip: lines.join('\n') };
}

/** 1 while it holds and the watcher still speaks of it; after it ended, fading like a pull mark; 0 when gone. */
function visibility(h: HeldHidden, nowMs: number): number {
  const age = nowMs - h.atMs;
  if (h.hidden <= 0 || age < 0) return 0; // the book later showed as much: nothing hidden any more
  if (h.state === 'holding') return age <= L2_HIDDEN_STALE_MS ? 1 : 0;
  return age < L2_PULL_MARK_SHOW_MS ? opacityAt(age) : 0;
}

/** One side's hidden marks, placed after the rows at their price (depthMarkers.markerPlace, like every mark). */
export function hiddenMarks(state: BookWatchState | null, side: BookSide, rows: readonly DepthLevel[], nowMs: number): PullMark[] {
  if (!state) return [];
  const out: PullMark[] = [];
  for (const h of state.hidden) {
    const opacity = h.side === side ? visibility(h, nowMs) : 0;
    if (opacity <= 0) continue;
    const place = markerPlace(side, rows, h.price);
    const end = h.state === 'holding' ? ' hidden' : ` · ${END_CHIP[h.state] ?? h.state}`;
    out.push({
      id: `${side}-hidden-${h.id}`,
      kind: 'hidden',
      before: place.before,
      beyond: place.beyond,
      opacity,
      label: `◆ ${markShares(h.hidden)}${end}${place.beyond ? ' ↓' : ''}`,
      ...hiddenTip(h),
    });
  }
  return out.sort((a, b) => a.before - b.before);
}

/** The shown prices where a hidden seller or buyer holds now, by price key: the ladder outlines those rows. */
export function hiddenHere(state: BookWatchState | null, side: BookSide, rows: readonly DepthLevel[], nowMs: number): Map<string, PulledHere> {
  const out = new Map<string, PulledHere>();
  if (!state) return out;
  const shown = new Set(rows.map(r => priceKey(r.price)));
  for (const h of state.hidden) {
    if (h.side !== side || h.state !== 'holding' || visibility(h, nowMs) <= 0) continue;
    const key = priceKey(h.price);
    if (shown.has(key)) out.set(key, { count: 1, ...hiddenTip(h) });
  }
  return out;
}
