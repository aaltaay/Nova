/**
 * Which events on the hot list become a toast (ADR 044 amendment, operator ask 2026-10-12: "i get alot of stupid
 * toast notifications ... the way we have it codded is no good"). Pure: an event, what the desk knows at that
 * moment and the gate's memory in; a verdict and the next memory out.
 *
 * - A star toasts; an auto star toasts once, when it joins the list, and is held back after that.
 * - Running Up never toasts. A setup toasts from armed up; forming is held back.
 * - Nothing toasts outside the trading window.
 * - After a toast a stock's HOD Momo alerts are quiet for WATCH_TOAST_QUIET_MS: one that comes while its toast is
 *   still on screen folds into it, otherwise it is held back. A setup moving up a stage always comes through
 *   (setupClimbs announces each stage once) and starts the quiet period again.
 *
 * A name not on the list is ignored, never counted. The memory is the trading day's.
 */
import type { WatchSetupStage } from './types';
import { WATCH_TOAST_QUIET_MS } from './watchListConstants';

export type ToastHow = 'star' | 'auto' | null;

export type ToastCandidate =
  | { kind: 'hod'; symbol: string; runningUp: boolean }
  | { kind: 'setup'; symbol: string; stage: WatchSetupStage }
  | { kind: 'join'; symbol: string };

/** Why a listed name's event raised no toast. */
export type HeldReason = 'running_up' | 'auto_star' | 'forming' | 'quiet' | 'outside_window';

export type GateVerdict =
  | { verdict: 'raise' }
  | { verdict: 'fold' }
  | { verdict: 'hold'; reason: HeldReason }
  | { verdict: 'ignore' };

export interface GateContext {
  nowMs: number;
  /** The trading day at `nowMs` ("YYYY-MM-DD", from 04:00 ET). */
  day: string;
  inWindow: boolean;
  /** How the symbol is on the hot list now; null when it is not. */
  how: ToastHow;
  /** A toast for the symbol is on screen now. */
  onScreen: boolean;
}

export interface GateMemory {
  day: string;
  /** Symbol -> when its last toast was raised (ms). */
  lastToast: ReadonlyMap<string, number>;
  /** Auto stars whose join was announced (or held) today. */
  joined: ReadonlySet<string>;
}

function fresh(day: string): GateMemory {
  return { day, lastToast: new Map(), joined: new Set() };
}

function raised(memory: GateMemory, symbol: string, nowMs: number, joined = false): GateMemory {
  return {
    day: memory.day,
    lastToast: new Map(memory.lastToast).set(symbol, nowMs),
    joined: joined ? new Set(memory.joined).add(symbol) : memory.joined,
  };
}

function hold(memory: GateMemory, reason: HeldReason): { verdict: GateVerdict; memory: GateMemory } {
  return { verdict: { verdict: 'hold', reason }, memory };
}

/** Pure: what `event` does, given `ctx` and the memory so far (null: nothing yet). */
export function gateToast(
  prior: GateMemory | null,
  event: ToastCandidate,
  ctx: GateContext,
): { verdict: GateVerdict; memory: GateMemory } {
  const memory = prior && prior.day === ctx.day ? prior : fresh(ctx.day);
  const symbol = event.symbol.trim().toUpperCase();
  if (!symbol || ctx.how === null) return { verdict: { verdict: 'ignore' }, memory };

  if (event.kind === 'join') {
    // A star (one starred, or made one) has nothing to join; each auto star joins once a day.
    if (ctx.how !== 'auto' || memory.joined.has(symbol)) return { verdict: { verdict: 'ignore' }, memory };
    if (!ctx.inWindow) {
      return hold({ ...memory, joined: new Set(memory.joined).add(symbol) }, 'outside_window');
    }
    return { verdict: { verdict: 'raise' }, memory: raised(memory, symbol, ctx.nowMs, true) };
  }
  if (ctx.how === 'auto') return hold(memory, 'auto_star');
  if (event.kind === 'hod' && event.runningUp) return hold(memory, 'running_up');
  if (event.kind === 'setup' && event.stage === 'forming') return hold(memory, 'forming');
  if (!ctx.inWindow) return hold(memory, 'outside_window');
  if (event.kind === 'setup') return { verdict: { verdict: 'raise' }, memory: raised(memory, symbol, ctx.nowMs) };

  const last = memory.lastToast.get(symbol);
  if (last !== undefined && ctx.nowMs - last < WATCH_TOAST_QUIET_MS) {
    return ctx.onScreen ? { verdict: { verdict: 'fold' }, memory } : hold(memory, 'quiet');
  }
  return { verdict: { verdict: 'raise' }, memory: raised(memory, symbol, ctx.nowMs) };
}
