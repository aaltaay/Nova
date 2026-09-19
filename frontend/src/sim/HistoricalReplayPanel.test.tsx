/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { HistoricalReplayPanel } from './HistoricalReplayPanel';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ openStockView: vi.fn() }) }));

const job = (status: string) => ({
  id: `job-${status}`, symbol: 'IMCC', date: '2026-09-18', start: '04:00', end: '09:30',
  kind: 'trades', status, count: 1200, pages: 2, error: null,
});

function respond(body: unknown) {
  mocks.fetch.mockResolvedValue({ ok: true, json: async () => body });
}

beforeEach(() => { mocks.fetch.mockReset(); });
afterEach(() => { cleanup(); });

async function mount() {
  await act(async () => { render(<HistoricalReplayPanel />); });
}

it('an unexpected list body leaves the panel mounted', async () => {
  respond({});
  await mount();
  expect(screen.getByText('Historical replay')).toBeTruthy();
  expect(screen.getByRole('list', { name: 'Historical downloads' }).children).toHaveLength(0);
});

it('uses the API default date, visible-label names and per-job action names', async () => {
  respond({ jobs: [job('pause_requested'), job('running'), job('paused')], default_date: '2026-09-04' });
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
