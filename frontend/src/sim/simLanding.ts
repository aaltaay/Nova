/**
 * Land the Sim on a stock-day, step by step, for a caller outside a Sim panel (ADR 050: an agent's
 * show and move). The same requests the Day picker, the tab prompt's Load from files and the transport
 * make, through the same serialized lane and with the same events, so every panel follows as if the
 * operator had clicked: day -> the symbol's Trader tab -> the window from the Massive files (waiting
 * for its import) -> the playhead, paused. A window over the Sim's print or quote cap is tried again
 * with the plan's narrower windows.
 */
import { historicalStatus } from './historicalStatusStore';
import { MASSIVE_SOURCE, type HistoricalJob, type HistoricalSelection } from './historicalTypes';
import { replayPost, replayRequest } from './replayRequest';
import { simClockResource } from './simClockResource';
import { cancelPendingSimSeek, emitSimClockScrub } from './simClockEvents';
import type { SimClockState } from './simClockTypes';
import { parseHistoricalStatus } from './simPayloadParse';
import { serializeSimSessionMutation } from './simSessionMutations';

export interface LandingWindow { start: string; end: string; start_ts: number; end_ts: number }
export interface SimLandingPlan {
  symbol: string;
  date: string;
  window: LandingWindow;
  fallback_windows: LandingWindow[];
  /** Epoch seconds the playhead parks at, paused. */
  park_ts: number;
}
export interface SimMovePlan {
  symbol: string;
  date: string;
  target_ts: number | null;
  paused: boolean | null;
  /** Start of the window loaded when the plan was made (epoch seconds). */
  loaded_start_ts: number;
  /** A window to load first, when the target is outside the loaded one. */
  window: LandingWindow | null;
  fallback_windows: LandingWindow[];
}
export interface LandingHooks {
  /** Say what is happening; resolves false when the caller must stop (the command was cancelled). */
  step: (step: string, text: string) => Promise<boolean>;
  /** Open (or bring forward) the symbol's Trader tab in this window. */
  openTab: (symbol: string) => void;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}
export interface Landed { symbol: string; date: string; window: LandingWindow | null; clock: SimClockState | null }

/** The caller asked to stop (a newer command replaced this one): nothing more is done. */
export class LandingStopped extends Error {}

const IMPORT_POLL_MS = 1000;
const IMPORT_TIMEOUT_MS = 20 * 60_000;
const BUSY_WAIT_MS = 2000;
const BUSY_TIMEOUT_MS = 10 * 60_000;
const TOO_BIG = /narrow the window|more than a replay holds|exceeds/i;
const IMPORT_BUSY = /another massive import is running/i;

const defaultSleep = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms));

async function post<T>(path: string, body: unknown, failure: string): Promise<T> {
  return serializeSimSessionMutation(path, () => replayRequest<T>(path, replayPost(body), failure));
}

/** POST /api/sim/clock, published to every Sim panel as a scrub (what the transport does). */
export async function simPostClock(body: object, failure = 'Could not move the Sim'): Promise<SimClockState | null> {
  cancelPendingSimSeek();
  simClockResource.suspend();
  try {
    const next = await post<SimClockState>('/clock', body, failure);
    simClockResource.setData(next);
    const parsed = simClockResource.getSnapshot().data;
    emitSimClockScrub({ symbol: parsed?.replay_symbol ?? undefined, minute: parsed?.minute_from_open ?? 0 });
    return parsed ?? null;
  } finally {
    simClockResource.resume();
  }
}

/** POST /api/sim/history/select, published as the Load buttons do (`selectHistoricalReplay`). */
export async function simSelectWindow(symbol: string, date: string, window: LandingWindow): Promise<HistoricalSelection> {
  cancelPendingSimSeek();
  const spec = { symbol, date, start: window.start, end: window.end, source: MASSIVE_SOURCE };
  const selected = await post<HistoricalSelection>('/history/select', spec, 'Could not load the window');
  const data = historicalStatus.getSnapshot().data;
  historicalStatus.invalidate({ ...data, jobs: Array.isArray(data?.jobs) ? data.jobs : [], selection: selected });
  emitSimClockScrub();
  return selected;
}

async function readJobs(): Promise<HistoricalJob[]> {
  const raw = await replayRequest<unknown>('/history', {}, 'Could not read the imports');
  return parseHistoricalStatus(raw).jobs;
}

function jobFor(jobs: HistoricalJob[], symbol: string, date: string, window: LandingWindow, jobId?: string | null) {
  return jobs.find(job => (jobId && job.id === jobId)
    || (job.source === MASSIVE_SOURCE && job.symbol === symbol && job.date === date
        && job.start === window.start && job.end === window.end));
}

const pct = (job: HistoricalJob) => (typeof job.progress_pct === 'number' ? `${Math.round(job.progress_pct)}%` : '');

async function stepOrStop(hooks: LandingHooks, step: string, text: string): Promise<void> {
  if (!(await hooks.step(step, text))) throw new LandingStopped(text);
}

/** Select the window; when another import holds the files, wait for it (it is one at a time). */
async function selectWhenFree(plan: { symbol: string; date: string }, window: LandingWindow, hooks: LandingHooks) {
  const sleep = hooks.sleep ?? defaultSleep;
  const now = hooks.now ?? Date.now;
  const started = now();
  for (;;) {
    try {
      return await simSelectWindow(plan.symbol, plan.date, window);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (!IMPORT_BUSY.test(message) || now() - started > BUSY_TIMEOUT_MS) throw error;
      await stepOrStop(hooks, 'load', 'Waiting for another import from the files to finish');
      await sleep(BUSY_WAIT_MS);
    }
  }
}

type WindowResult = { ok: true; window: LandingWindow } | { ok: false; tooBig: boolean; error: string };

/** Load one window from the files and wait until its import is in; a window too busy to hold says so. */
async function loadWindow(plan: { symbol: string; date: string }, window: LandingWindow, hooks: LandingHooks): Promise<WindowResult> {
  const sleep = hooks.sleep ?? defaultSleep;
  const now = hooks.now ?? Date.now;
  const label = `${window.start}-${window.end} ET`;
  await stepOrStop(hooks, 'load', `Loading ${plan.symbol} ${label} from the files`);
  let selected: HistoricalSelection;
  try {
    selected = await selectWhenFree(plan, window, hooks);
  } catch (error) {
    if (error instanceof LandingStopped) throw error;
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, tooBig: TOO_BIG.test(message), error: message };
  }
  if (selected.download_status === 'complete') return { ok: true, window };
  const started = now();
  for (;;) {
    const job = jobFor(await readJobs(), plan.symbol, plan.date, window, selected.job_id);
    if (job?.status === 'complete') {
      await simSelectWindow(plan.symbol, plan.date, window);   // the same window again: the playhead stays
      return { ok: true, window };
    }
    if (job && ['failed', 'paused', 'interrupted'].includes(job.status)) {
      const message = job.error || `the import ${job.status}`;
      return { ok: false, tooBig: TOO_BIG.test(message), error: message };
    }
    if (now() - started > IMPORT_TIMEOUT_MS) return { ok: false, tooBig: false, error: 'the import took too long' };
    await stepOrStop(hooks, 'load', `Loading ${plan.symbol} ${label} from the files ${job ? pct(job) : ''}`.trim());
    await sleep(IMPORT_POLL_MS);
  }
}

/** The first of the windows that loads, else the reason the last one did not. */
async function loadFirst(plan: { symbol: string; date: string }, windows: LandingWindow[], hooks: LandingHooks): Promise<LandingWindow> {
  let last = 'nothing to load';
  for (const [i, window] of windows.entries()) {
    const result = await loadWindow(plan, window, hooks);
    if (result.ok) return result.window;
    last = result.error;
    if (!result.tooBig || i === windows.length - 1) break;
    await stepOrStop(hooks, 'load', `Too many prints in ${window.start}-${window.end}: trying a narrower window`);
  }
  throw new Error(last);
}

/** Park the playhead (paused) at `ts` inside the window that starts at `startTs`. */
async function park(symbol: string, startTs: number, ts: number, paused: boolean | null = true): Promise<SimClockState | null> {
  if (paused !== null) await simPostClock({ paused }, 'Could not pause the Sim');
  return simPostClock({ second_from_open: Math.max(0, ts - startTs), symbol }, 'Could not move the playhead');
}

export async function landSim(plan: SimLandingPlan, hooks: LandingHooks): Promise<Landed> {
  await stepOrStop(hooks, 'day', `Moving the Sim to ${plan.date}`);
  await simPostClock({ session_date: plan.date }, 'Could not move the Sim to that day');
  await stepOrStop(hooks, 'tab', `Opening ${plan.symbol}`);
  hooks.openTab(plan.symbol);
  const window = await loadFirst(plan, [plan.window, ...plan.fallback_windows], hooks);
  await stepOrStop(hooks, 'park', 'Parking the playhead');
  const clock = await park(plan.symbol, window.start_ts, plan.park_ts);
  return { symbol: plan.symbol, date: plan.date, window, clock };
}

export async function moveSim(plan: SimMovePlan, hooks: LandingHooks): Promise<Landed> {
  let startTs = plan.loaded_start_ts;
  let window: LandingWindow | null = null;
  if (plan.window) {
    window = await loadFirst(plan, [plan.window, ...plan.fallback_windows], hooks);
    startTs = window.start_ts;
  }
  if (plan.target_ts == null) {
    const clock = plan.paused === null ? null : await simPostClock({ paused: plan.paused }, 'Could not change playback');
    return { symbol: plan.symbol, date: plan.date, window, clock };
  }
  await stepOrStop(hooks, 'park', 'Moving the playhead');
  const clock = await park(plan.symbol, startTs, plan.target_ts, plan.paused ?? (window ? true : null));
  return { symbol: plan.symbol, date: plan.date, window, clock };
}
