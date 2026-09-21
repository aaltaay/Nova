/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetSimReplayTargetDismissals, SimReplayTargetNotice } from './SimReplayTargetNotice';
import { historicalStatus } from './historicalStatusStore';
import type { HistoricalJob } from './historicalTypes';
import type { SimClockState } from './simClockTypes';

const mocks = vi.hoisted(() => ({
  openStockView: vi.fn(), fetch: vi.fn(), launch: vi.fn(), mode: 'sim' as string,
  // Honest Gateway transport; undefined = unknown (treated as reachable).
  gateway: {} as Record<string, boolean | undefined>,
}));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ openStockView: mocks.openStockView }) }));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: mocks.mode, ...mocks.gateway }) }));
vi.mock('../utils/launchIbGateway', () => ({ launchIbGateway: mocks.launch }));

// useSyncExternalStore requires a STABLE snapshot reference between calls, the
// same contract replayPollResource keeps by publishing one state object. A mock
// that rebuilds the object each read loops forever.
let clockState: { data: SimClockState | null; error: string | null } = { data: null, error: null };
const setClock = (clock: SimClockState | null) => { clockState = { data: clock, error: null }; };
vi.mock('./simClockResource', () => ({
  simClockResource: { subscribe: () => () => {}, getSnapshot: () => clockState },
}));

const WINDOW = { symbol: 'IMCC', date: '2026-09-18', start: '09:15', end: '11:30' };
const job = (over: Partial<HistoricalJob> = {}): HistoricalJob => ({
  id: 'imcc', kind: 'trades', status: 'running', count: 0, pages: 0, error: null, ...WINDOW, ...over,
});
let jobs: HistoricalJob[] = [];
const posts: { url: string; body: unknown }[] = [];
const response = (body: unknown, ok = true) => ({ ok, json: async () => body });

beforeEach(() => {
  // Sunday night ET: Friday's session is finished. Only Date is faked.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-09-21T02:00:00Z'));
  mocks.openStockView.mockReset();
  mocks.launch.mockReset().mockResolvedValue({ ok: true, action: 'launched', message: 'Starting IB Gateway' });
  mocks.mode = 'sim';
  mocks.gateway = {};
  jobs = [];
  posts.length = 0;
  resetSimReplayTargetDismissals();
  setClock(null);
  mocks.fetch.mockReset().mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body));
      posts.push({ url, body });
      if (url.endsWith('/history/select')) return response({ ...body, coverage_through: 0, trade_count: 10 });
      const started = job({ status: jobs.find(j => j.id === 'imcc')?.status === 'complete' ? 'complete' : 'running' });
      jobs = [started, ...jobs.filter(j => j.id !== 'imcc')];
      return response(started);
    }
    return response({ jobs, selection: null, default_date: '2026-09-18' });
  });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

const notice = () => screen.queryByTestId('sim-replay-target-notice');
const body = () => screen.getByTestId('sim-replay-target-body').textContent ?? '';
const action = () => screen.queryByTestId('sim-replay-target-action');
let view: ReturnType<typeof render> | null = null;
async function mount(symbol = 'IMCC') {
  await act(async () => { view = render(<SimReplayTargetNotice symbol={symbol} />); });
}
async function rerender(symbol = 'IMCC') {
  await act(async () => { view!.rerender(<SimReplayTargetNotice symbol={symbol} />); });
}
const GATEWAY_DOWN = { transport_connected: false, preferred_port_reachable: false, alternate_port_reachable: false };
const GATEWAY_UP = { transport_connected: false, preferred_port_reachable: true, alternate_port_reachable: false };
/** Let a zero-delay heal timer fire and its request settle. */
async function tick() {
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
  await act(async () => { await Promise.resolve(); });
}
/** Stand in for the next poll landing. */
async function poll(next: HistoricalJob[]) {
  jobs = next;
  await act(async () => { historicalStatus.invalidate({ jobs: next, selection: null, default_date: '2026-09-18' }); });
}

describe('SimReplayTargetNotice', () => {
  it('renders nothing before the clock is read, and nothing outside Sim', async () => {
    await mount();
    expect(notice()).toBeNull();
    cleanup();
    mocks.mode = 'paper';
    setClock({ sim: true, replay_source: 'historical', replay_symbol: 'SPY' });
    await mount();
    expect(notice()).toBeNull();
    // A Paper/Live Stock View must not poll the replay archive at all.
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it('asks to download and load the stated window, then loads it when the download finishes', async () => {
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    expect(body()).toBe('Download and load IMCC · Fri, Sep 18 · 09:15–11:30 ET?');
    expect(action()?.textContent).toBe('Download');

    await act(async () => { fireEvent.click(action()!); });
    expect(posts[0]).toEqual({ url: expect.stringMatching(/\/api\/sim\/history$/), body: { ...WINDOW, kind: 'trades' } });

    // Before the first page lands: nothing to play yet, and Stop is the action
    // (one download runs at a time, so a long one must be abandonable).
    await poll([job({ progress_pct: 0, count: 0 })]);
    expect(body()).toBe('Downloading IMCC · Fri, Sep 18 · 09:15–11:30 ET -- 0%. It loads as soon as the first prints land.');
    expect(action()?.textContent).toBe('Stop');

    // First page committed: it loads now, not at 100%.
    await poll([job({ progress_pct: 4, eta_seconds: 180, count: 1000 })]);
    expect(posts.at(-1)).toEqual({ url: expect.stringMatching(/\/history\/select$/), body: WINDOW });
  });

  it('Stop pauses the running job and hands back Resume', async () => {
    jobs = [job({ progress_pct: 0, count: 0 })];
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    await act(async () => { fireEvent.click(action()!); });
    expect(posts[0].url).toMatch(/\/history\/imcc\/pause$/);
    await poll([job({ status: 'paused', progress_pct: 11, count: 0 })]);
    expect(body()).toBe('IMCC · Fri, Sep 18 · 09:15–11:30 ET download stopped at 11%.');
    expect(action()?.textContent).toBe('Resume');
  });

  it('loads straight away when the window was already downloaded', async () => {
    jobs = [job({ status: 'complete' })];
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    expect(body()).toBe('IMCC · Fri, Sep 18 · 09:15–11:30 ET is downloaded.');
    await act(async () => { fireEvent.click(action()!); });
    expect(posts).toEqual([{ url: expect.stringMatching(/\/history\/select$/), body: WINDOW }]);
  });

  it('offers Load mid-download without auto-loading a job it never asked for', async () => {
    jobs = [job({ progress_pct: 30, count: 5000 })];
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    expect(body()).toBe('Downloading IMCC · Fri, Sep 18 · 09:15–11:30 ET -- 30%. Load now -- new prints fold in as they land.');
    expect(posts).toEqual([]);
    await act(async () => { fireEvent.click(action()!); });
    expect(posts).toEqual([{ url: expect.stringMatching(/\/history\/select$/), body: WINDOW }]);
  });

  it('does not auto-load a download it never asked for', async () => {
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    await poll([job({ status: 'complete' })]);
    expect(posts).toEqual([]);
    expect(action()?.textContent).toBe('Load');
  });

  it('on another symbol offers both the replayed tab and this one instead', async () => {
    setClock({ sim: true, replay_source: 'historical', replay_symbol: 'SPY', session_date: '2026-09-18' });
    await mount();
    expect(body()).toBe("SPY is loaded, so IMCC won't fill. Download and load IMCC · Fri, Sep 18 · 09:15–11:30 ET instead?");
    fireEvent.click(screen.getByTestId('sim-replay-target-goto'));
    expect(mocks.openStockView).toHaveBeenCalledWith('SPY');
  });

  it('names the window hogging the slot, and Stop it & start this frees it and starts this one', async () => {
    // The live case: a 16-hour 04:00-20:00 job blocking the one-click window.
    jobs = [job({ id: 'old', start: '04:00', end: '20:00', progress_pct: 11 })];
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    expect(body()).toBe('IMCC · Fri, Sep 18 · 04:00–20:00 ET is downloading, and the desk runs one download at a time.');
    expect(action()?.textContent).toBe('Stop it & start this');

    await act(async () => { fireEvent.click(action()!); });
    expect(posts[0].url).toMatch(/\/history\/old\/pause$/);
    await poll([job({ id: 'old', start: '04:00', end: '20:00', status: 'paused' })]);
    expect(posts.at(-1)).toEqual({ url: expect.stringMatching(/\/api\/sim\/history$/), body: { ...WINDOW, kind: 'trades' } });
  });

  it('Gateway down: one click starts Gateway, then downloads and loads by itself', async () => {
    mocks.gateway = GATEWAY_DOWN;
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    expect(body()).toBe("IB Gateway isn't running. Start it and IMCC · Fri, Sep 18 · 09:15–11:30 ET downloads and loads by itself.");
    expect(action()?.textContent).toBe('Start Gateway & download');

    await act(async () => { fireEvent.click(action()!); });
    expect(mocks.launch).toHaveBeenCalledTimes(1);
    expect(body()).toContain('Waiting for IB Gateway');
    expect(action()).toBeNull();
    expect(posts).toEqual([]); // nothing fired at a dark port

    mocks.gateway = GATEWAY_UP;
    await rerender();
    expect(posts[0]).toEqual({ url: expect.stringMatching(/\/api\/sim\/history$/), body: { ...WINDOW, kind: 'trades' } });

    await poll([job({ status: 'complete' })]);
    expect(posts.at(-1)).toEqual({ url: expect.stringMatching(/\/history\/select$/), body: WINDOW });
  });

  it('a failed launch says why and keeps the button', async () => {
    mocks.gateway = GATEWAY_DOWN;
    mocks.launch.mockResolvedValue({ ok: false, message: 'IBC launcher not found' });
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    await act(async () => { fireEvent.click(action()!); });
    expect(screen.getByRole('alert').textContent).toBe('IBC launcher not found');
    expect(action()?.textContent).toBe('Start Gateway & download');
  });

  it('heals a Gateway-unreachable failure once a port answers, then loads the empty desk', async () => {
    // Failed long enough ago that the backend's 16 s retry throttle has passed.
    const failedAt = Date.parse('2026-09-21T02:00:00Z') / 1000 - 60;
    jobs = [job({ status: 'failed', error: 'IB Gateway unreachable (4001: refused; 4002: refused)', updated: failedAt })];
    mocks.gateway = GATEWAY_UP;
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    // The "retrying" copy itself is pinned in simReplayOffer.test.ts; asserting
    // it here races the zero-delay heal timer. What matters is that it retries.
    await tick();
    expect(posts[0]).toEqual({ url: expect.stringMatching(/\/api\/sim\/history$/), body: { ...WINDOW, kind: 'trades' } });

    await poll([job({ status: 'complete' })]);
    expect(posts.at(-1)).toEqual({ url: expect.stringMatching(/\/history\/select$/), body: WINDOW });
  });

  it('IBKR silent behind an open Gateway: retries by itself and offers a reconnect', async () => {
    const failedAt = Date.parse('2026-09-21T02:00:00Z') / 1000 - 90;  // past the 60 s wait
    const silent = 'IBKR did not answer within 45s while identifying IMCC: IB Gateway accepted the connection';
    jobs = [job({ status: 'failed', error: silent, updated: failedAt })];
    mocks.gateway = GATEWAY_UP;                   // the port answers; IBKR behind it does not
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    // Its wording and Reconnect button are pinned in simReplayOffer.test.ts; the
    // retry is already due here, so it fires during mount -- which is the point.
    await tick();
    expect(posts[0]).toEqual({ url: expect.stringMatching(/\/api\/sim\/history$/), body: { ...WINDOW, kind: 'trades' } });
  });

  it('Reconnect Gateway & retry rebuilds the session, then downloads', async () => {
    jobs = [job({ status: 'failed', error: 'IBKR did not answer within 45s while identifying IMCC', updated: Date.parse('2026-09-21T02:00:00Z') / 1000 })];
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    await act(async () => { fireEvent.click(action()!); });
    expect(mocks.launch).toHaveBeenCalledTimes(1);
    expect(posts.at(-1)).toEqual({ url: expect.stringMatching(/\/api\/sim\/history$/), body: { ...WINDOW, kind: 'trades' } });
  });

  it('never auto-retries a failure Gateway being back cannot fix', async () => {
    jobs = [job({ status: 'failed', error: 'Ticker could not be uniquely qualified by IBKR', updated: 1 })];
    mocks.gateway = GATEWAY_UP;
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    await tick();
    expect(posts).toEqual([]);
    expect(action()?.textContent).toBe('Retry');
  });

  it('× hides the prompt for this tab and situation', async () => {
    setClock({ sim: true, replay_source: 'none', session_date: '2026-09-18' });
    await mount();
    await act(async () => { fireEvent.click(screen.getByTestId('sim-replay-target-dismiss')); });
    expect(notice()).toBeNull();
  });

  it('is silent on the replayed tab itself', async () => {
    setClock({ sim: true, replay_source: 'historical', replay_symbol: 'SPY', session_date: '2026-09-18' });
    await mount('SPY');
    expect(notice()).toBeNull();
  });

  it('shows a failed selection as failed', async () => {
    setClock({ sim: true, replay_source: 'none', replay_ok: false, replay_error: 'Capture is empty' });
    await mount('SPY');
    expect(notice()?.textContent).toContain('Capture is empty');
    expect(notice()?.className).toContain('sim-replay-target--failed');
  });
});
