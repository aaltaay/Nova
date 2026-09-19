/** @vitest-environment jsdom */
import { act, useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SimSessionHeader } from './SimSessionHeader';
import { SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), open: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ openStockView: mocks.open }),
}));

const clock = {
  sim: true, replay_source: 'capture', replay_date: '2026-09-19',
  replay_symbol: 'SIM1', minute_from_open: 120, minute_max: 960,
};

// Model the visible desk: IMCC is active and SIM1 has been closed.
// Any navigation request from the header will reopen and activate SIM1.
function Desk() {
  const [tabs, setTabs] = useState(['IMCC']);
  const [active, setActive] = useState('IMCC');
  mocks.open.mockImplementation((symbol: string) => {
    setTabs(old => old.includes(symbol) ? old : [...old, symbol]);
    setActive(symbol);
  });
  return <>
    <output data-testid="tabs">{tabs.join(',')}</output>
    <output data-testid="active">{active}</output>
    <SimSessionHeader active />
  </>;
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.open.mockReset();
  mocks.fetch.mockReset();
  mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => ({
    ok: true,
    json: async () => url.endsWith('/history') ? {jobs: []} : url.endsWith('/sessions') ? {
      days: [{ date: '2026-09-19', ticker_count: 2 }],
      tickers_by_day: { '2026-09-19': [
        { symbol: 'SIM1', prints: 100, l2: 10 },
        { symbol: 'IMCC', prints: 100, l2: 10 },
      ] },
    } : { ...clock, ...(init?.body ? JSON.parse(String(init.body)) : {}) },
  }));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

async function mount() {
  await act(async () => { render(<Desk />); });
}

it.each(['pointer release', 'debounced change'])(
  '%s refreshes the clock without reopening SIM1 or leaving IMCC', async mode => {
    await mount();
    const refresh = vi.fn();
    window.addEventListener(SIM_CLOCK_SCRUB_EVENT, refresh);
    try {
      const slider = screen.getByTestId('sim-session-scrubber');
      await act(async () => {
        if (mode === 'pointer release') fireEvent.pointerDown(slider);
        fireEvent.change(slider, { target: { value: '240' } });
        if (mode === 'pointer release') fireEvent.pointerUp(slider);
        else await vi.advanceTimersByTimeAsync(120);
      });
      expect(mocks.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/sim/clock'),
        expect.objectContaining({ method: 'POST', body: JSON.stringify({ minute_from_open: 240 }) }));
      expect(refresh).toHaveBeenCalledTimes(1);
      expect((slider as HTMLInputElement).value).toBe('240');
      expect(screen.getByTestId('active').textContent).toBe('IMCC');
      expect(screen.getByTestId('tabs').textContent).toBe('IMCC');
      expect(mocks.open).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, refresh);
    }
  },
);

it('an explicit ticker pick still opens and activates the chosen replay tab', async () => {
  await mount();
  await act(async () => {
    fireEvent.change(screen.getByTestId('sim-replay-ticker'), { target: { value: 'IMCC' } });
  });
  await act(async () => {
    fireEvent.change(screen.getByTestId('sim-replay-ticker'), { target: { value: 'SIM1' } });
  });
  expect(mocks.open).toHaveBeenLastCalledWith('SIM1');
  expect(screen.getByTestId('active').textContent).toBe('SIM1');
  expect(screen.getByTestId('tabs').textContent).toBe('IMCC,SIM1');
});

it('one button switches between Pause and Play without navigating', async () => {
  await mount();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pause Sim time' })); });
  expect(mocks.fetch).toHaveBeenLastCalledWith(expect.stringContaining('/api/sim/clock'),
    expect.objectContaining({ body: JSON.stringify({ paused: true }) }));
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Play Sim time' })); });
  expect(screen.getByRole('button', { name: 'Pause Sim time' })).toBeTruthy();
  expect(mocks.fetch).toHaveBeenLastCalledWith(expect.stringContaining('/api/sim/clock'),
    expect.objectContaining({ body: JSON.stringify({ paused: false }) }));
  expect(mocks.open).not.toHaveBeenCalled();
});

it('failed pause remains visibly playing and surfaces an error', async () => {
  await mount();
  mocks.fetch.mockResolvedValueOnce({ ok: false });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pause Sim time' })); });
  expect(screen.getByRole('alert').textContent).toContain('Could not change Sim playback');
  expect(screen.getByRole('button', { name: 'Pause Sim time' })).toBeTruthy();
});

it('playback controls are absent when Sim is inactive', () => {
  render(<SimSessionHeader active={false} />);
  expect(screen.queryByRole('button', { name: 'Pause Sim time' })).toBeNull();
});


it('defaults to the extended-hours session slider', async () => {
  await mount();
  expect(screen.getByText('04:00')).toBeTruthy();
  expect(screen.getByText('20:00')).toBeTruthy();
  expect((screen.getByTestId('sim-session-scrubber') as HTMLInputElement).max).toBe('960');
});

it('Return to SIM1 clears the hidden capture pickers', async () => {
  let source = 'capture';
  mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => ({
    ok: true,
    json: async () => {
      if (url.endsWith('/history')) return { jobs: [] };
      if (url.endsWith('/sessions')) return { days: [{ date: '2026-09-19', ticker_count: 1 }],
        tickers_by_day: { '2026-09-19': [{ symbol: 'IMCC', prints: 10, l2: 1 }] } };
      if (url.endsWith('/api/sim/replay') && init?.method === 'POST') source = 'synthetic';
      if (source === 'historical') return { ...clock, replay_source: 'historical', replay_date: '2026-09-18', replay_symbol: 'IMCC' };
      if (source === 'synthetic') return { ...clock, replay_source: 'synthetic', replay_date: null, replay_symbol: null };
      return { ...clock, replay_symbol: 'IMCC' };
    },
  }));
  await mount();
  expect((screen.getByTestId('sim-replay-ticker') as HTMLSelectElement).value).toBe('IMCC');
  source = 'historical';
  await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Return to SIM1' })); });
  expect(screen.getByTestId('sim-replay-source').textContent).toBe('SIM1');
  expect((screen.getByTestId('sim-replay-day') as HTMLSelectElement).value).toBe('');
  expect((screen.getByTestId('sim-replay-ticker') as HTMLSelectElement).value).toBe('');
});
