/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { HistoricalReplayPanel } from './HistoricalReplayPanel';
import { API_BASE_URL } from '../constants';
import { SIM_HISTORY_IDLE_POLL_MS, SIM_HISTORY_POLL_MS, SIM_REQUEST_TIMEOUT_MS } from './simConstants';
import { SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';
import type { HistoricalJob, HistoricalSelection } from './historicalTypes';
const mocks = vi.hoisted(() => ({ fetch: vi.fn(), openStockView: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ openStockView: mocks.openStockView }) }));
const response = (body: unknown, ok = true) => ({ ok, json: async () => body });
const endpoint = `${API_BASE_URL}/api/sim/history`;
const spec = { symbol: 'AAPL', date: '2026-09-04', start: '08:00', end: '10:00' };
let jobs: HistoricalJob[];
let selection: HistoricalSelection | null;
const job = (status: string): HistoricalJob => ({ id: `job-${status}`, symbol: 'IMCC', date: '2026-09-18', start: '04:00', end: '09:30', kind: 'trades', status, count: 1200, pages: 2, error: null });
beforeEach(() => {
  jobs = []; selection = null;
  mocks.fetch.mockReset().mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (url.endsWith('/select')) selection = { ...JSON.parse(String(init.body)), coverage_through: 1770000000, trade_count: 0, download_status: 'missing' };
      return response(selection ?? {});
    }
    return response({ jobs, selection, default_date: '2026-09-04' });
  });
  mocks.openStockView.mockReset();
});
afterEach(() => { cleanup(); vi.useRealTimers(); });
async function click(name: string | RegExp) { await act(async () => fireEvent.click(screen.getByRole('button', { name }))); }
async function mount(open = true) {
  let view!: ReturnType<typeof render>;
  await act(async () => { view = render(<HistoricalReplayPanel />); });
  if (open) await click('Historical replay');
  return view;
}
function chooseWindow() {
  fireEvent.change(screen.getByLabelText('Historical ticker'), { target: { value: ' aapl ' } });
  fireEvent.change(screen.getByLabelText('From'), { target: { value: spec.start } });
  fireEvent.change(screen.getByLabelText('To'), { target: { value: spec.end } });
}
function expectPost(path: string, body: unknown) {
  expect(mocks.fetch).toHaveBeenCalledWith(`${endpoint}${path}`, expect.objectContaining({
    method: 'POST', body: JSON.stringify(body), signal: expect.any(AbortSignal),
  }));
}
it('a malformed jobs body stays mounted and reports an empty list', async () => {
  mocks.fetch.mockResolvedValue(response({ jobs: {} }));
  await mount();
  expect(screen.getByRole('list', { name: 'Historical downloads' }).children).toHaveLength(0);
});
it('uses API defaults and independently named job controls', async () => {
  jobs = [job('pause_requested'), job('running'), job('paused')];
  await mount();
  expect((screen.getByLabelText('Date') as HTMLInputElement).value).toBe('2026-09-04');
  expect((screen.getByRole('button', { name: /^Pausing download:/ }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('button', { name: /^Pausing download:/ }).getAttribute('data-why'))
    .toBe('Pause asked -- the download stops before its next page');
  // No ticker typed yet: every window action says so instead of doing nothing.
  for (const name of ['Load replay', 'Download candles', 'Download trades']) {
    expect(screen.getByRole('button', { name }).getAttribute('data-why')).toBe('Type a ticker first');
  }
  expect(screen.getByRole('button', { name: /^Pause download:/ })).toBeTruthy();
  expect(screen.getByRole('button', { name: /^Resume download:/ })).toBeTruthy();
  expect(screen.getAllByRole('button', { name: /^Use this window:/ })).toHaveLength(3);
});
it('loads, closes, restores trigger focus and describes missing trades truthfully', async () => {
  await mount(); chooseWindow();
  const scrub = vi.fn(); window.addEventListener(SIM_CLOCK_SCRUB_EVENT, scrub);
  try {
    await click('Load replay');
    expectPost('/select', spec);
    expect(mocks.openStockView).toHaveBeenCalledExactlyOnceWith('AAPL');
    expect(scrub).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByText(/Selected: AAPL .* · no trades downloaded/)).toBeTruthy();
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Historical replay' }));
    await click('Historical replay');
    fireEvent.change(screen.getByLabelText('Historical ticker'), { target: { value: 'SPY' } });
    expect(screen.getByText(/Selected: AAPL/)).toBeTruthy();
    expect(screen.queryByText(/^Loaded/)).toBeNull();
  } finally { window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, scrub); }
});
it.each([['Download candles', 'bars'], ['Download trades', 'trades']])('%s posts without changing the ticker', async (button, kind) => {
  await mount(); chooseWindow(); await click(button);
  expectPost('', { ...spec, kind }); expect(mocks.openStockView).not.toHaveBeenCalled();
});
it.each([['running', 'Pause', 'pause'], ['paused', 'Resume', 'resume']])('%s jobs use the matching operation', async (status, label, action) => {
  jobs = [job(status)]; await mount(); await click(new RegExp(`^${label} download:`));
  expectPost(`/job-${status}/${action}`, {});
});
it('keeps user-picked dates across polling', async () => {
  vi.useFakeTimers(); jobs = [job('complete')]; await mount(); await click(/^Use this window:/);
  await act(async () => vi.advanceTimersByTimeAsync(SIM_HISTORY_POLL_MS));
  expect((screen.getByLabelText('Date') as HTMLInputElement).value).toBe('2026-09-18');
});
it.each([
  [() => Promise.resolve(response({ detail: 'No data for that window' }, false)), 'No data for that window'],
  [() => Promise.resolve({ ok: false, status: 502, json: async () => { throw new SyntaxError('bad html'); } }), 'Historical replay request failed (502)'],
  [() => Promise.reject(new TypeError('Failed to fetch')), 'Could not reach Nova'],
] as const)('surfaces useful errors and allows retry', async (failure, message) => {
  await mount(); chooseWindow(); mocks.fetch.mockImplementationOnce(failure); await click('Load replay');
  expect(screen.getByRole('alert').textContent).toContain(message);
  expect(mocks.openStockView).not.toHaveBeenCalled();
  await click('Load replay'); expect(mocks.openStockView).toHaveBeenCalledWith('AAPL');
});
it('keeps independent actions usable and releases a hung action at its deadline', async () => {
  vi.useFakeTimers(); jobs = [job('running')]; await mount(); chooseWindow();
  mocks.fetch.mockImplementationOnce((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
    init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
  }));
  await click(/^Pause download:/);
  expect((screen.getByRole('button', { name: 'Load replay' }) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.getByRole('button', { name: 'Load replay' }).hasAttribute('data-why')).toBe(false);
  expect((screen.getByRole('button', { name: 'Download trades' }) as HTMLButtonElement).disabled).toBe(false);
  expect((screen.getByRole('button', { name: /^Pause download:/ }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('button', { name: /^Pause download:/ }).getAttribute('data-why'))
    .toBe('Pause download sent -- waiting for Nova to answer');
  await act(async () => vi.advanceTimersByTimeAsync(SIM_REQUEST_TIMEOUT_MS));
  expect(screen.getByRole('alert').textContent).toContain('did not respond in time');
  expect((screen.getByRole('button', { name: /^Pause download:/ }) as HTMLButtonElement).disabled).toBe(false);
});
it('shows progress and stalled jobs outside the closed popup and exposes resume', async () => {
  jobs = [{ ...job('running'), progress_pct: 42, downloaded_through: 1770000000, stale: true, age_seconds: 120 }];
  await mount(false);
  expect(screen.getByRole('status').textContent).toContain('IMCC Stalled');
  expect(screen.getByRole('status').textContent).toContain('42%');
  await click('Historical replay');
  expect(screen.getByRole('progressbar').getAttribute('value')).toBe('42');
  expect(screen.getByText(/No checkpoint for 2m/)).toBeTruthy();
  expect(screen.getByRole('button', { name: /^Resume download:/ })).toBeTruthy();
});
it('backs off closed idle polling and cancels requests on unmount', async () => {
  vi.useFakeTimers(); const view = await mount(false);
  await act(async () => vi.advanceTimersByTimeAsync(SIM_HISTORY_IDLE_POLL_MS - 1));
  expect(mocks.fetch).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTimeAsync(1)); expect(mocks.fetch).toHaveBeenCalledTimes(2);
  view.unmount(); await act(async () => vi.advanceTimersByTimeAsync(SIM_HISTORY_IDLE_POLL_MS * 2));
  expect(mocks.fetch).toHaveBeenCalledTimes(2); expect(vi.getTimerCount()).toBe(0);
});
it('validates time order before making a request', async () => {
  await mount(); chooseWindow();
  fireEvent.change(screen.getByLabelText('To'), { target: { value: '07:00' } });
  await click('Load replay');
  expect(screen.getByRole('alert').textContent).toContain('start before end');
  expect(mocks.fetch.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
});
it('Escape dismisses the portal and closed polling remains available', async () => {
  await mount();
  expect(within(screen.getByRole('dialog')).getByLabelText('Historical ticker')).toBeTruthy();
  await act(async () => fireEvent.keyDown(document, { key: 'Escape' }));
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('keeps the current download visible ahead of an older failure', async () => {
  jobs = [{ ...job('failed'), symbol: 'OLD', error: 'Gateway offline' }, { ...job('running'), progress_pct: 25, eta_seconds: 120 }];
  await mount(false);
  expect(screen.getByRole('status').textContent).toBe('IMCC running 25% · 2m left');
});
