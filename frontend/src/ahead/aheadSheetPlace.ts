/**
 * Where the Ahead panel opens (ADR 065): never over the 1-minute pane it explains. The 1-minute pane publishes, per
 * symbol, its own span and its zone's (client pixels). When the chart grid has room beside that pane -- the desk's
 * 2x2 grid, the 1-minute pane its bottom-right one -- the panel slides over the other panes there, below the grid's
 * toolbar. When it has none (the 1-minute pane fills the grid, or is maximised), the panel docks: the chart grid gives
 * up the panel's width on the side away from the zone, so nothing of the chart -- toolbar, candles, zone, chips, price
 * axis -- is under it.
 */
import { useSyncExternalStore } from 'react';

/** The 1-minute pane's span and its zone's (left edge of the zone to the pane's right edge, price axis included). */
export interface KeepClear {
  left: number;
  right: number;
  paneLeft: number;
  paneRight: number;
}

export interface SheetPlace {
  side: 'left' | 'right';
  width: number;
  /** True: the chart grid gives up the panel's width (beside the charts); false: over the other panes. */
  dock: boolean;
}

/** The panel's widest, its widest share of the chart grid (over the panes, docked), its narrowest, its gap. */
export const SHEET_MAX_PX = 520;
export const SHEET_MAX_SHARE = 0.62;
export const SHEET_DOCK_MAX_SHARE = 0.34;
export const SHEET_MIN_PX = 300;
export const SHEET_GAP_PX = 8;

const keeps = new Map<string, KeepClear>();
const listeners = new Set<() => void>();

const near = (a: number, b: number) => Math.abs(a - b) < 1;

/** The 1-minute pane of `symbol` says where it and its zone are (null: no zone on screen). */
export function publishKeepClear(symbol: string, keep: KeepClear | null): void {
  const was = keeps.get(symbol) ?? null;
  if (was === keep || (was && keep && near(was.left, keep.left) && near(was.right, keep.right)
    && near(was.paneLeft, keep.paneLeft) && near(was.paneRight, keep.paneRight))) return;
  if (keep) keeps.set(symbol, keep);
  else keeps.delete(symbol);
  for (const fn of [...listeners]) fn();
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function useKeepClear(symbol: string): KeepClear | null {
  return useSyncExternalStore(subscribe, () => keeps.get(symbol) ?? null);
}

type Span = { left: number; right: number };

/** Where `x` (measured while `dock` squeezes the charts) sits with the whole grid for the charts again. */
function unsqueeze(x: number, grid: Span, dock: SheetPlace | null): number {
  if (!dock?.dock) return x;
  const full = grid.right - grid.left;
  const area = full - dock.width;
  if (area <= 0) return x;
  const areaLeft = dock.side === 'left' ? grid.left + dock.width : grid.left;
  return grid.left + ((x - areaLeft) * full) / area;
}

/**
 * Pure: the side, width and kind of place for the panel over a chart grid spanning `grid` (client pixels). `current`
 * is the place it has now: a dock squeezes the panes it measures, and is undone first so the answer never flips.
 * Room beside the 1-minute pane for the panel's floor: over the other panes on the roomier side, as wide as that room
 * allows. No such room: docked on the side away from the zone. Nothing to keep clear: over the panes on the right.
 */
export function sheetPlace(grid: Span, keep: KeepClear | null, current: SheetPlace | null = null): SheetPlace {
  const full = grid.right - grid.left;
  const usual = Math.max(0, Math.min(SHEET_MAX_PX, full * SHEET_MAX_SHARE));
  if (!keep) return { side: 'right', width: usual, dock: false };
  const u = (x: number) => unsqueeze(x, grid, current);
  const floor = Math.min(SHEET_MIN_PX, usual);
  const besideLeft = u(keep.paneLeft) - grid.left - SHEET_GAP_PX;
  const besideRight = grid.right - u(keep.paneRight) - SHEET_GAP_PX;
  if (Math.max(besideLeft, besideRight) >= floor) {
    const side = besideRight > besideLeft ? 'right' : 'left';
    return { side, width: Math.min(usual, side === 'right' ? besideRight : besideLeft), dock: false };
  }
  const side = grid.right - u(keep.right) > u(keep.left) - grid.left ? 'right' : 'left';
  return { side, width: Math.max(floor, Math.min(usual, full * SHEET_DOCK_MAX_SHARE)), dock: true };
}

/** Two places that put the panel in the same spot. */
export function samePlace(a: SheetPlace | null, b: SheetPlace | null): boolean {
  return a === b || (!!a && !!b && a.side === b.side && a.dock === b.dock && near(a.width, b.width));
}

/** Tests only. */
export function resetKeepClearForTesting(): void {
  keeps.clear();
}
