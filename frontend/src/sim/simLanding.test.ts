/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LandingStopped, landSim, moveSim, type LandingHooks, type SimLandingPlan } from './simLanding';
import { SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));

const DAY = '2026-09-25';
const W = { start: '09:00', end: '11:15', start_ts: 1_790_341_200, end_ts: 1_790_349_300 };
const NARROW = { start: '09:00', end: '10:00', start_ts: 1_790_341_200, end_ts: 1_790_344_800 };
const PLAN: SimLandingPlan = { symbol: 'MSGY', date: DAY, window: W, fallback_windows: [NARROW], park_ts: W.start_ts + 1740 };

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const refuse = (detail: string) => ({ ok: false, status: 422, json: async () => ({ detail }) });

let posts: Array<{ path: string; body: Record<string, unknown> }>;
let selects: number;
let polls: number;
let script: { firstSelect?: () => unknown; jobs?: (n: number) => unknown[] };

function hooks(over: Partial<LandingHooks> = {}): LandingHooks & { steps: string[]; tabs: string[] } {
  const steps: string[] = [];
  const tabs: string[] = [];
  return {
    steps, tabs,
    step: async (_name, text) => { steps.push(text); return true; },
    openTab: symbol => { tabs.push(symbol); },
    sleep: async () => {},
    ...over,
  };
}

beforeEach(() => {
  posts = [];
  selects = 0;
  polls = 0;
  script = {};
  mocks.fetch.mockReset().mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.replace(/^.*?\/api\/sim/, '');
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      posts.push({ path, body });
      if (path === '/history/select') {
        selects += 1;
        if (selects === 1 && script.firstSelect) return script.firstSelect();
        const complete = selects > 1 || !script.jobs;
        return ok({ ...body, coverage_through: 0, download_status: complete ? 'complete' : 'running', job_id: 'j1' });
      }
      if ('second_from_open' in body) {
        return ok({ sim: true, session_date: DAY, paused: true, sim_time_et: '2026-09-25T09:29:00-04:00' });
      }
      return ok({ sim: true, session_date: DAY, paused: true, minute_from_open: 0 });
    }
    polls += 1;
    return ok({ jobs: script.jobs ? script.jobs(polls) : [] });
  });
});
afterEach(() => vi.restoreAllMocks());

const job = (status: string, progress: number) => ({
  id: 'j1', kind: 'trades', status, count: null, pages: null, error: null, progress_pct: progress,
  symbol: 'MSGY', date: DAY, start: W.start, end: W.end, source: 'massive',
});

describe('landSim', () => {
  it('moves the day, opens the tab, waits for the import, re-selects and parks paused at the plan', async () => {
    script.jobs = n => [job(n < 2 ? 'running' : 'complete', n < 2 ? 40 : 100)];
    const scrubs = vi.fn();
    window.addEventListener(SIM_CLOCK_SCRUB_EVENT, scrubs);
    const h = hooks();
    const landed = await landSim(PLAN, h);
    window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, scrubs);
    expect(posts.map(p => p.path)).toEqual(['/clock', '/history/select', '/history/select', '/clock', '/clock']);
    expect(posts[0].body).toEqual({ session_date: DAY });
    expect(posts[1].body).toMatchObject({ symbol: 'MSGY', date: DAY, start: '09:00', end: '11:15', source: 'massive' });
    expect(posts[3].body).toEqual({ paused: true });
    expect(posts[4].body).toEqual({ second_from_open: 1740, symbol: 'MSGY' });
    expect(h.tabs).toEqual(['MSGY']);
    expect(h.steps.some(s => s.endsWith('40%'))).toBe(true);
    expect(landed.window).toEqual(W);
    expect(landed.clock?.sim_time_et).toContain('09:29:00');
    expect(scrubs).toHaveBeenCalled();
  });

  it('a window over the print cap is tried again narrower', async () => {
    script.firstSelect = () => refuse('Replay exceeds 500,000 prints; narrow the window');
    const h = hooks();
    const landed = await landSim(PLAN, h);
    const loads = posts.filter(p => p.path === '/history/select').map(p => `${p.body.start}-${p.body.end}`);
    expect(loads).toEqual(['09:00-11:15', '09:00-10:00']);
    expect(landed.window).toEqual(NARROW);
    expect(h.steps.some(s => s.startsWith('Too many prints'))).toBe(true);
  });

  it('waits while another import holds the files, then loads', async () => {
    script.firstSelect = () => refuse('Another Massive import is running');
    const h = hooks();
    await landSim(PLAN, h);
    expect(posts.filter(p => p.path === '/history/select')).toHaveLength(2);
    expect(h.steps).toContain('Waiting for another import from the files to finish');
  });

  it('a failed import is the error, and a step answered false stops it', async () => {
    script.jobs = () => [{ ...job('failed', 10), error: 'MSGY trades file unreadable' }];
    await expect(landSim(PLAN, hooks())).rejects.toThrow('MSGY trades file unreadable');
    const stopping = hooks({ step: async (name: string) => name !== 'load' });
    await expect(landSim(PLAN, stopping)).rejects.toBeInstanceOf(LandingStopped);
  });
});

describe('moveSim', () => {
  it('moves inside the loaded window without loading, and pauses only when asked', async () => {
    const landed = await moveSim({ symbol: 'MSGY', date: DAY, target_ts: W.start_ts + 600, paused: null,
      loaded_start_ts: W.start_ts, window: null, fallback_windows: [] }, hooks());
    expect(posts).toEqual([{ path: '/clock', body: { second_from_open: 600, symbol: 'MSGY' } }]);
    expect(landed.window).toBeNull();
    posts = [];
    await moveSim({ symbol: 'MSGY', date: DAY, target_ts: null, paused: false, loaded_start_ts: W.start_ts,
      window: null, fallback_windows: [] }, hooks());
    expect(posts).toEqual([{ path: '/clock', body: { paused: false } }]);
  });
});
