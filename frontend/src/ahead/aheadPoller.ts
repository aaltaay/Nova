/**
 * One Ahead poller per symbol (ADR 065), shared by every pane that shows it and counted like the Sim clock's poll
 * (`sim/simClockResource.ts`): the first holder starts it, the last one stops it and drops the symbol's answer.
 *
 * When it asks: at once when a holder arrives; when the desk minute rolls over (the playhead's minute on a replay),
 * `AHEAD_MINUTE_SETTLE_MS` later so the candle that closed is in Nova's store; while the backend is reading a minute,
 * after its `retry_ms` (at most `AHEAD_PENDING_MAX_TRIES` quick asks in a row); every `AHEAD_SLOW_RETRY_MS` while
 * the forecaster is warming, offline, quiet, refusing or absent. A `ready` answer for the current minute is not asked
 * again; one for an older minute is asked `AHEAD_STALE_READY_MAX_TRIES` times (the store may be a moment late), then
 * not until the next minute (a thin stock with no trade in the minute that closed has nothing newer). Nothing is asked while the window is hidden; each read has its own AbortController.
 *
 * A Sim scrub for the symbol drops its answer, cancels the read in flight and asks at once. For a while after a scrub
 * an answer made more than `AHEAD_REWIND_SLACK_SEC` after the playhead is from before the rewind and is dropped
 * (never at other times: in forward play the desk's playhead lags the backend's).
 */
import { matchesSimClockScrub, SIM_CLOCK_SCRUB_EVENT } from '../sim';
import { fetchAhead, type AheadFetch } from './aheadApi';
import {
  AHEAD_BEAT_MS,
  AHEAD_MINUTE_SETTLE_MS,
  AHEAD_PENDING_MAX_TRIES,
  AHEAD_PENDING_RETRY_MS,
  AHEAD_REWIND_SLACK_SEC,
  AHEAD_SCRUB_FENCE_MS,
  AHEAD_SLOW_RETRY_MS,
  AHEAD_STALE_READY_MAX_TRIES,
  AHEAD_STEP_SEC,
  AHEAD_WORDS,
} from './aheadConstants';
import { aheadHeldOf, clearAhead, publishAhead } from './aheadStore';
import type { AheadAnswer } from './aheadTypes';

interface Poller {
  sym: string;
  refs: number;
  timer: ReturnType<typeof setInterval> | null;
  ctrl: AbortController | null;
  gen: number;
  /** Wall-clock ms of the next ask; Infinity waits for the minute to roll over. */
  dueAt: number;
  /** Quick asks in a row. */
  tries: number;
  lastMinute: number | null;
  /** Wall-clock ms until which the after-a-scrub check runs. */
  fenceUntil: number;
}

const pollers = new Map<string, Poller>();
/** The replay's playhead (epoch seconds) on a replay desk; null: the desk clock is the wall clock. */
let deskPlayhead: number | null = null;

const key = (sym: string) => sym.trim().toUpperCase();

export function setAheadDeskPlayhead(playheadSec: number | null): void {
  deskPlayhead = playheadSec;
}

function deskNow(): number {
  return deskPlayhead ?? Date.now() / 1000;
}

function hidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

/** The answer is for the minute the desk is in (its forecast starts at the forming candle). */
function current(a: AheadAnswer): boolean {
  const minuteStart = Math.floor(deskNow() / AHEAD_STEP_SEC) * AHEAD_STEP_SEC;
  return a.as_of !== null && a.as_of >= minuteStart;
}

function newerThanPlayhead(a: AheadAnswer | null, p: Poller, now: number): boolean {
  return a !== null && deskPlayhead !== null && now < p.fenceUntil && a.generated_at > deskPlayhead + AHEAD_REWIND_SLACK_SEC;
}

function quickOrSlow(p: Poller, quickMs: number, now: number): void {
  p.tries += 1;
  p.dueAt = now + (p.tries < AHEAD_PENDING_MAX_TRIES ? quickMs : AHEAD_SLOW_RETRY_MS);
}

function settle(p: Poller, res: AheadFetch): void {
  const now = Date.now();
  if (res.answer === null) {
    publishAhead(p.sym, { answer: null, problem: res.problem });
    p.tries = 0;
    p.dueAt = now + AHEAD_SLOW_RETRY_MS;
    return;
  }
  const a = res.answer;
  if (newerThanPlayhead(a, p, now)) {
    quickOrSlow(p, AHEAD_PENDING_RETRY_MS, now);
    return;
  }
  publishAhead(p.sym, { answer: a, problem: null });
  if (a.ai.state === 'pending') {
    quickOrSlow(p, a.ai.retry_ms ?? AHEAD_PENDING_RETRY_MS, now);
  } else if (a.ai.state === 'ready' && !current(a)) {
    // The backend has not seen the candle that just closed: its store is a moment late, or no trade printed in that
    // minute (then no newer candle comes until one does). A few quick asks, then the next minute.
    p.tries += 1;
    p.dueAt = p.tries < AHEAD_STALE_READY_MAX_TRIES ? now + AHEAD_PENDING_RETRY_MS : Infinity;
  } else if (a.ai.state === 'ready') {
    p.tries = 0;
    p.dueAt = Infinity;
  } else {
    p.tries = 0;
    p.dueAt = now + AHEAD_SLOW_RETRY_MS;
  }
}

function ask(p: Poller): void {
  p.gen += 1;
  const gen = p.gen;
  const ctrl = new AbortController();
  p.ctrl = ctrl;
  fetchAhead(p.sym, ctrl.signal)
    .then((res) => {
      if (gen !== p.gen) return;
      p.ctrl = null;
      settle(p, res);
    })
    .catch((err: unknown) => {
      if (gen !== p.gen || ctrl.signal.aborted) return;
      p.ctrl = null;
      console.warn('Ahead: the read for %s failed', p.sym, err);
      settle(p, { answer: null, problem: AHEAD_WORDS.readFailed });
    });
}

function beat(p: Poller): void {
  if (hidden()) return;
  const now = Date.now();
  const minute = Math.floor(deskNow() / AHEAD_STEP_SEC);
  if (p.lastMinute !== null && minute !== p.lastMinute) {
    p.dueAt = Math.min(p.dueAt, now + AHEAD_MINUTE_SETTLE_MS);
    p.tries = 0;
  }
  p.lastMinute = minute;
  if (newerThanPlayhead(aheadHeldOf(p.sym).answer, p, now)) {
    clearAhead(p.sym);
    p.dueAt = Math.min(p.dueAt, now);
  }
  if (p.ctrl === null && now >= p.dueAt) ask(p);
}

function cancel(p: Poller): void {
  p.gen += 1;
  p.ctrl?.abort();
  p.ctrl = null;
}

function onScrub(event: Event): void {
  const now = Date.now();
  for (const p of pollers.values()) {
    if (!matchesSimClockScrub(event, p.sym)) continue;
    cancel(p);
    clearAhead(p.sym);
    p.tries = 0;
    p.dueAt = now;
    p.fenceUntil = now + AHEAD_SCRUB_FENCE_MS;
    beat(p);
  }
}

/** Hold the symbol's poller; the returned function lets go (the last holder stops it and drops its answer). */
export function acquireAheadPoller(sym: string): () => void {
  const k = key(sym);
  let p = pollers.get(k);
  if (!p) {
    if (pollers.size === 0 && typeof window !== 'undefined') window.addEventListener(SIM_CLOCK_SCRUB_EVENT, onScrub);
    const fresh: Poller = {
      sym: k, refs: 0, timer: null, ctrl: null, gen: 0, dueAt: Date.now(), tries: 0, lastMinute: null, fenceUntil: 0,
    };
    fresh.timer = setInterval(() => beat(fresh), AHEAD_BEAT_MS);
    pollers.set(k, fresh);
    p = fresh;
    beat(fresh);
  }
  p.refs += 1;
  const held = p;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    held.refs -= 1;
    if (held.refs > 0) return;
    if (held.timer !== null) clearInterval(held.timer);
    cancel(held);
    pollers.delete(k);
    clearAhead(k);
    if (pollers.size === 0 && typeof window !== 'undefined') window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, onScrub);
  };
}

/** Tests only: how many holders a symbol's poller has (0: none running). */
export function aheadPollerRefs(sym: string): number {
  return pollers.get(key(sym))?.refs ?? 0;
}
