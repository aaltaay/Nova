/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { HistoricalReplayPanel } from './HistoricalReplayPanel';
import { API_BASE_URL } from '../constants';
import { SIM_HISTORY_POLL_MS } from './simConstants';
import { SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), openStockView: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ openStockView: mocks.openStockView }) }));

const job = (status: string) => ({
  id: `job-${status}`, symbol: 'IMCC', date: '2026-09-18', start: '04:00', end: '09:30',
  kind: 'trades', status, count: 1200, pages: 2, error: null,
});
const response = (body: unknown, ok = true) => ({ ok, json: async () => body });
const endpoint = `${API_BASE_URL}/api/sim/history`;
const spec = { symbol: 'AAPL', date: '2026-09-04', start: '08:00', end: '10:00' };

beforeEach(() => {
  mocks.fetch.mockReset().mockResolvedValue(response({ jobs: [], default_date: '2026-09-04' }));
  mocks.openStockView.mockReset();
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

async function mount() {
  let view!: ReturnType<typeof render>;
  await act(async () => { view = render(<HistoricalReplayPanel />); });
  return view;
}
function chooseWindow() {
  fireEvent.change(screen.getByLabelText('Historical ticker'), { target: { value: ' aapl ' } });
  fireEvent.change(screen.getByLabelText('From'), { target: { value: spec.start } });
  fireEvent.change(screen.getByLabelText('To'), { target: { value: spec.end } });
}
async function click(name: string | RegExp) {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name })); });
}
function expectPost(path: string, body: unknown) {
  expect(mocks.fetch).toHaveBeenLastCalledWith(`${endpoint}${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
}

it('an unexpected list body leaves the panel mounted', async () => {
  mocks.fetch.mockResolvedValue(response({}));
  await mount();
  expect(screen.getByText('Historical replay')).toBeTruthy();
  expect(screen.getByRole('list', { name: 'Historical downloads' }).children).toHaveLength(0);
});

it('uses the API default date, visible-label names and per-job action names', async () => {
  mocks.fetch.mockResolvedValue(response({
    jobs: [job('pause_requested'), job('running'), job('paused')], default_date: '2026-09-04',
  }));
  await mount();
  expect((screen.getByLabelText('Date') as HTMLInputElement).value).toBe('2026-09-04');
  expect((screen.getByLabelText('From') as HTMLInputElement).value).toBe('04:00');
  expect((screen.getByLabelText('To') as HTMLInputElement).value).toBe('20:00');
  const pausing = screen.getByRole('button', { name: 'Pausing download: IMCC 2026-09-18 04:00–09:30 trades' });
  expect((pausing as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('button', { name: 'Pause download: IMCC 2026-09-18 04:00–09:30 trades' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Resume download: IMCC 2026-09-18 04:00–09:30 trades' })).toBeTruthy();
  expect(screen.getAllByRole('button', { name: /^Use this window: IMCC/ })).toHaveLength(3);
});

it('loads the chosen window, opens its normalized ticker and refreshes the replay clock', async () => {
  await mount();
  chooseWindow();
  const scrub = vi.fn();
  window.addEventListener(SIM_CLOCK_SCRUB_EVENT, scrub);
  try {
    await click('Load replay');
    expectPost('/select', spec);
    expect(mocks.openStockView).toHaveBeenCalledExactlyOnceWith('AAPL');
    expect(scrub).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status').textContent).toContain('Loaded AAPL');
  } finally { window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, scrub); }
});

it.each([['Download candles', 'bars'], ['Download trades', 'trades']])(
  '%s posts the selected window and data kind without changing the open ticker', async (button, kind) => {
    await mount();
    chooseWindow();
    await click(button);
    expectPost('', { ...spec, kind });
    expect(mocks.openStockView).not.toHaveBeenCalled();
  },
);

it.each([['running', 'Pause', 'pause'], ['paused', 'Resume', 'resume']])(
  '%s jobs send the matching control request', async (status, label, action) => {
    mocks.fetch.mockResolvedValue(response({ jobs: [job(status)] }));
    await mount();
    await click(new RegExp(`^${label} download:`));
    expectPost(`/job-${status}/${action}`, {});
  },
);

it('uses a saved window and keeps the selected date across subsequent polls', async () => {
  vi.useFakeTimers();
  mocks.fetch.mockResolvedValue(response({ jobs: [job('complete')], default_date: '2026-09-04' }));
  await mount();
  await click(/^Use this window:/);
  await act(async () => { await vi.advanceTimersByTimeAsync(SIM_HISTORY_POLL_MS); });
  await click('Load replay');
  expectPost('/select', { symbol: 'IMCC', date: '2026-09-18', start: '04:00', end: '09:30' });
  expect(screen.queryByRole('button', { name: /^Resume download:/ })).toBeNull();
});

it.each([
  ['server detail', () => Promise.resolve(response({ detail: 'No data for that window' }, false)), 'No data for that window'],
  ['structured detail', () => Promise.resolve(response({ detail: [{ msg: 'invalid' }] }, false)), 'Historical replay request failed'],
  ['network failure', () => Promise.reject(new Error('Network unavailable')), 'Network unavailable'],
] as const)('surfaces %s and allows a successful retry', async (_name, fail, message) => {
  await mount();
  chooseWindow();
  mocks.fetch.mockImplementationOnce(fail);
  await click('Load replay');
  expect(screen.getByRole('alert').textContent).toBe(message);
  expect(mocks.openStockView).not.toHaveBeenCalled();
  expect((screen.getByRole('button', { name: 'Load replay' }) as HTMLButtonElement).disabled).toBe(false);
  await click('Load replay');
  expect(screen.queryByRole('alert')).toBeNull();
  expect(mocks.openStockView).toHaveBeenCalledExactlyOnceWith('AAPL');
});

it('polls after a transient failure and cancels the interval on unmount', async () => {
  vi.useFakeTimers();
  mocks.fetch.mockRejectedValueOnce(new Error('temporary disconnect'));
  const view = await mount();
  expect(mocks.fetch).toHaveBeenCalledTimes(1);
  mocks.fetch.mockResolvedValue(response({ jobs: [job('complete')] }));
  await act(async () => { await vi.advanceTimersByTimeAsync(SIM_HISTORY_POLL_MS); });
  expect(mocks.fetch).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('list', { name: 'Historical downloads' }).children).toHaveLength(1);
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
  await act(async () => { await vi.advanceTimersByTimeAsync(SIM_HISTORY_POLL_MS * 3); });
  expect(mocks.fetch).toHaveBeenCalledTimes(2);
});

it('prevents duplicate load requests while pending and releases the button after failure', async () => {
  await mount();
  chooseWindow();
  let reject!: (reason: Error) => void;
  mocks.fetch.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  const button = screen.getByRole('button', { name: 'Load replay' });
  fireEvent.click(button);
  expect((button as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(button);
  expect(mocks.fetch).toHaveBeenCalledTimes(2); // Initial list + one load.
  await act(async () => { reject(new Error('Load interrupted')); });
  expect(screen.getByRole('alert').textContent).toBe('Load interrupted');
  expect((button as HTMLButtonElement).disabled).toBe(false);
  expect(mocks.openStockView).not.toHaveBeenCalled();
});
