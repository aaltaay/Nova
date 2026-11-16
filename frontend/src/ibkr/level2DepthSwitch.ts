/**
 * The Level 2 depth chart (operator ask, 2026-11-13, mockup v1: "build it as shown ... behind a right-click
 * switch"): the switch, and the sums the chart draws. Off until the operator turns it on, one choice for every
 * ladder and window, kept between restarts in `nova.level2.depthChart` (a prefStore envelope).
 *
 * Display only. It adds up the rows the Level 2 already shows -- nothing beyond them is drawn or guessed --
 * and touches no feed, mark or order.
 */
import { useSyncExternalStore } from 'react';
import { L2_DEPTH_CHART_STORAGE_KEY } from '../constants';
import { parseBoolFlag, readPref, writePref } from '../utils/prefStore';
import type { DepthLevel } from './types';

/** One price on a side, the inside first: what rests there and what rests from the inside out to it. */
export interface DepthStep {
  price: number;
  size: number;
  shares: number;
  dollars: number;
}

/** A side's rows (one per venue, best first) as one step per price, summed outward from the inside. */
export function depthSteps(levels: readonly DepthLevel[]): DepthStep[] {
  const at = new Map<number, number>();
  for (const level of levels) {
    if (!Number.isFinite(level.price) || !(level.size > 0)) continue;
    at.set(level.price, (at.get(level.price) ?? 0) + level.size);
  }
  let shares = 0;
  let dollars = 0;
  return [...at].map(([price, size]) => {
    shares += size;
    dollars += size * price;
    return { price, size, shares, dollars };
  });
}

/** Dollars in three figures: $940, $53.2K, $1.08M. */
export function depthDollars(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${Math.round(value)}`;
}

function load(): boolean {
  if (typeof localStorage === 'undefined') return false;
  return readPref(L2_DEPTH_CHART_STORAGE_KEY, false, parseBoolFlag);
}

let on = load();
const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key !== L2_DEPTH_CHART_STORAGE_KEY) return;
    on = load();
    emit();
  });
}

export function readLevel2DepthChart(): boolean {
  return on;
}

export function setLevel2DepthChart(next: boolean): void {
  if (next === on) return;
  on = next;
  if (typeof localStorage !== 'undefined') writePref(L2_DEPTH_CHART_STORAGE_KEY, on);
  emit();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

export function useLevel2DepthChart(): boolean {
  return useSyncExternalStore(subscribe, readLevel2DepthChart, readLevel2DepthChart);
}

/** Tests only: read storage again as a fresh window would. */
export function reloadLevel2DepthChartForTesting(): void {
  on = load();
  emit();
}
