/** @vitest-environment jsdom */
import { act, useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { publishScannerNavState, resetNavRailStoreForTests, setNavPage } from '../workspace/navRailStore';
import { SimSessionHeader } from './SimSessionHeader';
import { SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), open: vi.fn(), activeSymbol: null as string | null }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ openStockView: mocks.open, activeTraderSymbol: mocks.activeSymbol }),
}));

const clock = {
  sim: true, replay_source: 'capture', replay_date: '2026-09-19',
  replay_symbol: 'AAPL', minute_from_open: 120, minute_max: 960,
};

// Model the visible desk: IMCC is active and AAPL has been closed.
// Any navigation request from the header will reopen and activate AAPL.
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
  mocks.activeSymbol = null;
  mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => ({
    ok: true,
    json: async () => url.endsWith('/history') ? {jobs: []} : url.endsWith('/sessions') ? {
      days: [{ date: '2026-09-19', ticker_count: 2 }],
      tickers_by_day: { '2026-09-19': [
        { symbol: 'AAPL', prints: 100, l2: 10 },
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
  '%s refreshes the clock without reopening AAPL or leaving IMCC', async mode => {
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
    fireEvent.change(screen.getByTestId('sim-replay-ticker'), { target: { value: 'AAPL' } });
  });
  expect(mocks.open).toHaveBeenLastCalledWith('AAPL');
  expect(screen.getByTestId('active').textContent).toBe('AAPL');
  expect(screen.getByTestId('tabs').textContent).toBe('IMCC,AAPL');
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

it('Close replay clears the hidden capture pickers', async () => {
  let source = 'capture';
  mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => ({
    ok: true,
    json: async () => {
      if (url.endsWith('/history')) return { jobs: [] };
      if (url.endsWith('/sessions')) return { days: [{ date: '2026-09-19', ticker_count: 1 }],
        tickers_by_day: { '2026-09-19': [{ symbol: 'IMCC', prints: 10, l2: 1 }] } };
      if (url.endsWith('/api/sim/replay') && init?.method === 'POST') source = 'none';
      if (source === 'historical') return { ...clock, replay_source: 'historical', replay_date: '2026-09-18', replay_symbol: 'IMCC' };
      if (source === 'none') return { ...clock, replay_source: 'none', replay_date: null, replay_symbol: null };
      return { ...clock, replay_symbol: 'IMCC' };
    },
  }));
  await mount();
  expect((screen.getByTestId('sim-replay-ticker') as HTMLSelectElement).value).toBe('IMCC');
  source = 'historical';
  await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Close replay' })); });
  expect(screen.getByTestId('sim-replay-source').textContent).toBe('NO REPLAY');
  expect((screen.getByTestId('sim-replay-day') as HTMLSelectElement).value).toBe('');
  expect((screen.getByTestId('sim-replay-ticker') as HTMLSelectElement).value).toBe('');
});

it('shows the session date the clock is replaying', async () => {
  mocks.fetch.mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => url.endsWith('/history') ? { jobs: [] }
      : url.endsWith('/sessions') ? { days: [], tickers_by_day: {} }
      : { ...clock, replay_source: 'none', session_date: '2026-09-18' },
  }));
  await mount();
  expect(screen.getByTestId('sim-session-date').textContent).toBe('Fri, Sep 18');
});

it('failed capture selection shows an error without opening the rejected ticker, then retries', async () => {
  await mount();
  // POST /api/sim/replay answers the whole clock (C42), a failed selection included.
  mocks.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({
    sim: true, replay_source: 'none', replay_date: null, replay_symbol: null,
    sim_time_et: '2026-09-19T06:00:00-04:00', minute_from_open: 120, minute_max: 960,
    replay_ok: false, replay_error: 'Capture contains no usable prints or quotes',
  }) });
  await act(async () => {
    fireEvent.change(screen.getByTestId('sim-replay-ticker'), { target: { value: 'AAPL' } });
  });
  expect(screen.getByRole('alert').textContent).toContain('no usable prints or quotes');
  expect(screen.getByTestId('sim-replay-source').textContent).toBe('NO REPLAY');
  expect(screen.getByTestId('active').textContent).toBe('IMCC');
  expect(mocks.open).not.toHaveBeenCalled();
  expect((screen.getByTestId('sim-replay-day') as HTMLSelectElement).value).toBe('2026-09-19');
  expect((screen.getByTestId('sim-replay-ticker') as HTMLSelectElement).value).toBe('');
  mocks.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({
    ...clock, sim_time_et: '2026-09-19T06:00:00-04:00', replay_ok: true, replay_error: null,
  }) });
  await act(async () => {
    fireEvent.change(screen.getByTestId('sim-replay-ticker'), { target: { value: 'AAPL' } });
  });
  expect(screen.queryByRole('alert')).toBeNull();
  expect(mocks.open).toHaveBeenCalledWith('AAPL');
});

it('a transport failure reports unconfirmed selection and never navigates', async () => {
  await mount();
  mocks.fetch.mockRejectedValueOnce(new Error('offline'));
  await act(async () => {
    fireEvent.change(screen.getByTestId('sim-replay-ticker'), { target: { value: 'IMCC' } });
  });
  expect(screen.getByRole('alert').textContent).toContain('selection was not confirmed');
  expect(mocks.open).not.toHaveBeenCalled();
});

it('a failed replay remains visible after clock polling', async () => {
  const original = mocks.fetch.getMockImplementation()!;
  mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => url.endsWith('/clock') ? {
    ok: true, json: async () => ({ ...clock, replay_source: 'none', replay_ok: false,
      replay_error: 'Capture playback failed', replay_date: null, replay_symbol: null }),
  } : original(url, init));
  await mount();
  expect(screen.getByRole('alert').textContent).toBe('Capture playback failed');
  await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
  expect(screen.getByRole('alert').textContent).toBe('Capture playback failed');
  expect(mocks.open).not.toHaveBeenCalled();
});

it('empty recordings are visibly disabled in the ticker picker', async () => {
  const original = mocks.fetch.getMockImplementation()!;
  mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => url.endsWith('/sessions') ? {
    ok: true, json: async () => ({ days: [{ date: '2026-09-19', ticker_count: 1 }],
      tickers_by_day: { '2026-09-19': [{ symbol: 'EMPTY', prints: 0, l2: 0,
        empty: true, usable: false, unavailable_reason: 'No recorded prints or quotes' }] } }),
  } : original(url, init));
  await mount();
  const empty = screen.getByRole('option', { name: 'EMPTY · No recorded prints or quotes' }) as HTMLOptionElement;
  expect(empty.disabled).toBe(true);
});

it('commits one seek on pointer release and describes slider time for screen readers', async () => {
  await mount();
  const slider = screen.getByRole('slider', { name: 'Sim replay time' });
  await act(async () => {
    fireEvent.pointerDown(slider);
    fireEvent.change(slider, { target: { value: '100' } });
    await vi.advanceTimersByTimeAsync(500);
    fireEvent.change(slider, { target: { value: '200' } });
    await vi.advanceTimersByTimeAsync(500);
  });
  expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
  expect(slider.getAttribute('aria-valuetext')).toBe('07:20:00 Eastern');
  await act(async () => fireEvent.pointerUp(slider));
  expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
});
it('refreshes completed captures and never prints the unknown-count sentinel', async () => {
  await mount();
  const original = mocks.fetch.getMockImplementation()!;
  mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => url.endsWith('/sessions') ? responseSessions() : original(url, init));
  function responseSessions() { return { ok: true, json: async () => ({ days: [{ date: '2026-09-19', ticker_count: 1 }],
    tickers_by_day: { '2026-09-19': [{ symbol: 'NEW', prints: -1, l2: 0 }] } }) }; }
  await act(async () => vi.advanceTimersByTimeAsync(15000));
  expect(screen.getByRole('option', { name: /NEW.*data present/ })).toBeTruthy();
  expect(screen.queryByText(/-1p/)).toBeNull();
});

it('retains slider focus and commits the final keyboard step while a prior seek is pending', async () => {
  await mount();
  const original = mocks.fetch.getMockImplementation()!;
  let resolveFirst!: (value: unknown) => void;
  let posts = 0;
  mocks.fetch.mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith('/clock') && init?.method === 'POST' && ++posts === 1) return new Promise(resolve => { resolveFirst = resolve; });
    return original(url, init);
  });
  const slider = screen.getByRole('slider') as HTMLInputElement;
  slider.focus();
  await act(async () => { fireEvent.change(slider, { target: { value: '0' } }); await vi.advanceTimersByTimeAsync(120); });
  expect(slider.disabled).toBe(false); expect(document.activeElement).toBe(slider);
  await act(async () => { fireEvent.change(slider, { target: { value: '1' } }); await vi.advanceTimersByTimeAsync(120); });
  expect(posts).toBe(1);
  await act(async () => resolveFirst({ ok: true, json: async () => ({ ...clock, minute_from_open: 0 }) }));
  expect(posts).toBe(2);
  expect(slider.value).toBe('1');
  expect(mocks.fetch).toHaveBeenCalledWith(expect.stringContaining('/clock'), expect.objectContaining({ body: JSON.stringify({ minute_from_open: 1 }) }));
});

it('Follow wall clock cancels an unsent keyboard seek', async () => {
  await mount();
  fireEvent.change(screen.getByRole('slider'), { target: { value: '240' } });
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Follow wall clock' })));
  await act(async () => vi.advanceTimersByTimeAsync(500));
  const posts = mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
  expect(posts).toHaveLength(1);
  expect(JSON.parse(String(posts[0][1].body))).toEqual({ follow_wall: true });
});

it('Follow wall clock waits for an already-sent seek and replaces the queued next step', async () => {
  await mount();
  const original = mocks.fetch.getMockImplementation()!;
  let resolveFirst!: (value: unknown) => void;
  let posts = 0;
  mocks.fetch.mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith('/clock') && init?.method === 'POST' && ++posts === 1) return new Promise(resolve => { resolveFirst = resolve; });
    return original(url, init);
  });
  const slider = screen.getByRole('slider');
  await act(async () => { fireEvent.change(slider, { target: { value: '240' } }); await vi.advanceTimersByTimeAsync(120); });
  await act(async () => { fireEvent.change(slider, { target: { value: '241' } }); await vi.advanceTimersByTimeAsync(120); });
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Follow wall clock' })));
  expect(posts).toBe(1);
  await act(async () => resolveFirst({ ok: true, json: async () => ({ ...clock, minute_from_open: 240, scrubbed: true }) }));
  await act(async () => vi.advanceTimersByTimeAsync(500));
  const bodies = mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST').map(([, init]) => JSON.parse(String(init.body)));
  expect(bodies).toEqual([{ minute_from_open: 240 }, { follow_wall: true }]);
});

it('Close replay waits for a sent seek and cancels its queued keyboard successor', async () => {
  const original = mocks.fetch.getMockImplementation()!;
  let resolveFirst!: (value: unknown) => void;
  let currentSource = 'historical';
  mocks.fetch.mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith('/clock') && init?.method === 'POST') return new Promise(resolve => { resolveFirst = resolve; });
    if (url.endsWith('/api/sim/replay') && init?.method === 'POST') currentSource = 'none';
    if (url.endsWith('/clock') || url.endsWith('/api/sim/replay')) return Promise.resolve({ ok: true, json: async () => ({ ...clock, replay_source: currentSource }) });
    return original(url, init);
  });
  await mount();
  const slider = screen.getByRole('slider');
  await act(async () => { fireEvent.change(slider, { target: { value: '240' } }); await vi.advanceTimersByTimeAsync(120); });
  await act(async () => { fireEvent.change(slider, { target: { value: '241' } }); await vi.advanceTimersByTimeAsync(120); });
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Close replay' })));
  expect(currentSource).toBe('historical');
  await act(async () => resolveFirst({ ok: true, json: async () => ({ ...clock, replay_source: 'historical', minute_from_open: 240 }) }));
  await act(async () => vi.advanceTimersByTimeAsync(500));
  const paths = mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST').map(([url]) => String(url).split('/').pop());
  expect(paths).toEqual(['clock', 'replay']);
  expect(screen.getByTestId('sim-replay-source').textContent).toBe('NO REPLAY');
});

it('shows how far the loaded window is downloaded on the slider, like a buffered band', async () => {
  const start = Date.parse('2026-09-18T13:15:00Z') / 1000;
  const end = Date.parse('2026-09-18T15:30:00Z') / 1000;
  const selection = { symbol: 'IMCC', date: '2026-09-18', start: '09:15', end: '11:30',
    start_ts: start, end_ts: end, coverage_through: start + (end - start) / 4 };
  mocks.fetch.mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => url.endsWith('/history') ? { jobs: [], selection }
      : url.endsWith('/sessions') ? { days: [], tickers_by_day: {} }
      : { sim: true, replay_source: 'historical', replay_symbol: 'IMCC', minute_from_open: 10, minute_max: 135 },
  }));
  await mount();
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  const band = screen.getByTestId('sim-scrubber-coverage');
  expect(parseFloat(band.style.width)).toBeCloseTo(25);
  expect(band.parentElement?.getAttribute('title')).toMatch(/Trades downloaded: 09:15–09:48 ET/);
});

describe('the live edge (ADR 020 live-edge amendment)', () => {
  it('reads Live edge with a tooltip and LIVE EDGE as the source, never "load a replay"', async () => {
    mocks.fetch.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => url.endsWith('/history') ? { jobs: [] }
        : url.endsWith('/sessions') ? { days: [], tickers_by_day: {} }
        : { sim: true, replay_source: 'none', live_edge: true, session_date: '2026-09-21', minute_from_open: 360, minute_max: 960 },
    }));
    await mount();
    const edge = screen.getByTestId('sim-live-edge');
    expect(edge.textContent).toBe('Live edge');
    expect(edge.getAttribute('title')).toMatch(/Scrub back to replay/);
    expect(screen.getByTestId('sim-replay-source').textContent).toBe('LIVE EDGE');
    expect(screen.getByTestId('sim-replay-empty').textContent).toMatch(/^Live edge: practise on the live feed/);
    expect(screen.queryByRole('button', { name: 'Follow wall clock' })).toBeNull();
  });

  it("following the wall clock off today's session is not the edge, and says so", async () => {
    mocks.fetch.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => url.endsWith('/history') ? { jobs: [] }
        : url.endsWith('/sessions') ? { days: [], tickers_by_day: {} }
        : { sim: true, replay_source: 'none', live_edge: false, session_date: '2026-09-18' },
    }));
    await mount();
    expect(screen.getByTestId('sim-wall-clock').textContent).toBe('Wall clock');
    expect(screen.queryByTestId('sim-live-edge')).toBeNull();
    expect(screen.getByTestId('sim-replay-source').textContent).toBe('NO REPLAY');
  });

  it('a scrub and a pause carry the active tab so leaving the edge can load its recording', async () => {
    mocks.activeSymbol = 'imcc';
    await mount();
    const slider = screen.getByTestId('sim-session-scrubber');
    await act(async () => {
      fireEvent.pointerDown(slider);
      fireEvent.change(slider, { target: { value: '240' } });
      fireEvent.pointerUp(slider);
    });
    expect(mocks.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/sim/clock'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ minute_from_open: 240, symbol: 'IMCC' }) }));
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pause Sim time' })); });
    expect(mocks.fetch).toHaveBeenLastCalledWith(expect.stringContaining('/api/sim/clock'),
      expect.objectContaining({ body: JSON.stringify({ paused: true, symbol: 'imcc' }) }));
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Follow wall clock' })));
    expect(mocks.fetch).toHaveBeenLastCalledWith(expect.stringContaining('/api/sim/clock'),
      expect.objectContaining({ body: JSON.stringify({ follow_wall: true }) }));
  });
});

describe('QA 2026-09-22 batch (fix/qa-sim-replay)', () => {
  afterEach(() => resetNavRailStoreForTests());

  it('rides on the Scanner only -- Records, Account, the Desk and Bots carry no SIM SESSION bar (V41)', async () => {
    await mount();
    expect(screen.getByTestId('sim-session-header')).toBeTruthy();
    for (const page of ['records', 'account', 'desk'] as const) {
      act(() => setNavPage(page));
      expect(screen.queryByTestId('sim-session-header')).toBeNull();
    }
    act(() => setNavPage('dashboard'));
    expect(screen.getByTestId('sim-session-header')).toBeTruthy();
    act(() => publishScannerNavState({ activeTab: 'strategy', railHighlight: 'strategy', counts: {} }));
    expect(screen.queryByTestId('sim-session-header')).toBeNull();
  });

  it('places downloaded coverage on the clock window the slider spans, not the selection window (V10)', async () => {
    // The clock spans the full 04:00-20:00 session while the (stale) selection says 09:15-11:30.
    const start = Date.parse('2026-09-18T13:15:00Z') / 1000;
    const end = Date.parse('2026-09-18T15:30:00Z') / 1000;
    const selection = { symbol: 'IMCC', date: '2026-09-18', start: '09:15', end: '11:30',
      start_ts: start, end_ts: end, coverage_through: start, coverage: [[start, start + 3600]] };
    mocks.fetch.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => url.endsWith('/history') ? { jobs: [], selection }
        : url.endsWith('/sessions') ? { days: [], tickers_by_day: {} }
        : { sim: true, replay_source: 'historical', replay_symbol: 'IMCC', minute_from_open: 10, minute_max: 960,
          session_open_et: '2026-09-18T04:00:00-04:00', session_close_et: '2026-09-18T20:00:00-04:00' },
    }));
    await mount();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const band = screen.getByTestId('sim-scrubber-coverage');
    expect(parseFloat(band.style.left)).toBeCloseTo((5.25 / 16) * 100, 1);
    expect(parseFloat(band.style.width)).toBeCloseTo((1 / 16) * 100, 1);
    expect(screen.getByTestId('sim-session-bound-open').textContent).toBe('04:00');
  });

  it('a malformed segments list or coverage element never replaces the desk (C6)', async () => {
    mocks.fetch.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => url.endsWith('/history') ? { jobs: [], selection: { symbol: 'IMCC', coverage: [null], start_ts: 1, end_ts: 2 } }
        : url.endsWith('/sessions') ? { tickers_by_day: [] }
        : { ...clock, replay_load: { segments: {} } },
    }));
    await mount();
    expect(screen.getByTestId('sim-session-header')).toBeTruthy();
    expect(screen.queryAllByTestId('sim-scrubber-recorded')).toHaveLength(0);
  });

  it('a replay reply without the clock never blanks it -- the clock is kept and re-read (C42)', async () => {
    const full = { ...clock, sim_time_et: '2026-09-19T06:00:00-04:00', minute_from_open: 120 };
    mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => ({
      ok: true,
      json: async () => url.endsWith('/history') ? { jobs: [] }
        : url.endsWith('/sessions') ? { days: [{ date: '2026-09-19', ticker_count: 1 }], tickers_by_day: { '2026-09-19': [{ symbol: 'AAPL', prints: 100, l2: 10 }] } }
        // An older backend's POST /api/sim/replay: the replay fields only.
        : init?.method === 'POST' ? { sim: true, replay_source: 'capture', replay_date: '2026-09-19', replay_symbol: 'AAPL', replay_ok: true }
          : full,
    }));
    await mount();
    expect(screen.getByTestId('sim-session-clock').textContent).toBe('06:00:00 ET');
    const gets = () => mocks.fetch.mock.calls.filter(([url, init]) => String(url).endsWith('/api/sim/clock') && !init?.method).length;
    const before = gets();
    await act(async () => {
      fireEvent.change(screen.getByTestId('sim-replay-ticker'), { target: { value: 'AAPL' } });
    });
    expect(screen.getByTestId('sim-session-clock').textContent).not.toMatch(/--:--:--/);
    expect((screen.getByTestId('sim-session-scrubber') as HTMLInputElement).value).toBe('120');
    expect(gets()).toBeGreaterThan(before);
  });

  it('a capture still loading reads as loading, never as a red failure (C59)', async () => {
    mocks.fetch.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => url.endsWith('/history') ? { jobs: [] }
        : url.endsWith('/sessions') ? { days: [], tickers_by_day: {} }
        : { sim: true, replay_source: 'none', replay_ok: null, replay_loading: true, replay_error: null, minute_max: 960 },
    }));
    await mount();
    expect(screen.getByTestId('sim-replay-loading').textContent).toBe('Loading recording…');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByTestId('sim-replay-empty')).toBeNull();
  });
});
