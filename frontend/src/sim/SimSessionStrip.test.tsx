/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SimSessionStrip } from './SimSessionStrip';

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), open: vi.fn(), activeSymbol: 'GRML' as string | null }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ openStockView: mocks.open, activeTraderSymbol: mocks.activeSymbol }),
}));
vi.mock('../workspace', () => ({
  useWorkspace: () => ({ openStockView: mocks.open, activeTraderSymbol: mocks.activeSymbol }),
}));

const session = {
  session_open_et: '2026-09-21T04:00:00-04:00',
  session_close_et: '2026-09-21T20:00:00-04:00',
  session_date: '2026-09-21',
};

const edge = { sim: true, replay_source: 'none', live_edge: true, minute_from_open: 854, minute_max: 960,
  sim_time_et: '2026-09-21T18:14:07-04:00', ...session };

const capture = {
  sim: true, replay_source: 'capture', replay_date: '2026-09-21', replay_symbol: 'GRML', live_edge: false,
  scrubbed: true, minute_from_open: 462, minute_max: 960, sim_time_et: '2026-09-21T11:42:10-04:00', ...session,
  replay_load: {
    l2_total: 1, l2_loaded: 1, l2_decimated: false, malformed_rows: 0, invalid_timestamp_rows: 0, invalid_rows: 0,
    legacy_schema: false,
    segments: [
      { started_et: '2026-09-21T07:30:00-04:00', stopped_et: '2026-09-21T09:48:00-04:00', reason: 'restart' },
      { started_et: '2026-09-21T10:05:00-04:00', stopped_et: null },
    ],
  },
};

let clock: Record<string, unknown> = edge;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
  vi.setSystemTime(new Date('2026-09-21T22:14:07Z'));
  clock = edge;
  mocks.fetch.mockReset();
  mocks.open.mockReset();
  mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => ({
    ok: true,
    json: async () => url.endsWith('/history') ? { jobs: [], selection: null }
      : url.endsWith('/sessions') ? { days: [{ date: '2026-09-21', ticker_count: 1 }], tickers_by_day: { '2026-09-21': [{ symbol: 'GRML', prints: 10, l2: 1 }] } }
      : { ...clock, ...(init?.body ? JSON.parse(String(init.body)) : {}) },
  }));
});

afterEach(() => { cleanup(); vi.useRealTimers(); });

async function mount() { await act(async () => { render(<SimSessionStrip />); }); }
const posts = () => mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')
  .map(([url, init]) => ({ path: String(url).split('/api/sim')[1], body: JSON.parse(String(init.body)) }));

describe('SimSessionStrip', () => {
  it('at the live edge: green pill, no playhead tag, no clock block, the source lives in the menu', async () => {
    await mount();
    expect(screen.getByTestId('sim-live-edge').textContent).toBe('Live edge');
    expect(screen.queryByTestId('sim-strip-playhead-tag')).toBeNull();
    expect(screen.queryByTestId('sim-session-clock')).toBeNull();
    expect(screen.queryByTestId('sim-replay-source')).toBeNull();
    expect(screen.getByTestId('sim-strip-playhead')).toBeTruthy();
    expect((screen.getByTestId('sim-strip-edge') as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-menu')); });
    expect(screen.getByTestId('sim-replay-source').textContent).toBe('LIVE EDGE');
    expect(screen.getByTestId('sim-replay-empty').textContent).toMatch(/^Live edge: practise on the live feed/);
    expect(screen.getByTestId('sim-strip-follow-wall')).toBeTruthy();
    expect(screen.getByTestId('sim-replay-day')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Historical replay' })).toBeTruthy();
  });

  it('off the edge: the band draws the recording and its gap, the tag rides above the playhead, ⏭ follows the wall clock', async () => {
    clock = capture;
    await mount();
    expect(screen.getAllByTestId('sim-strip-seg-recorded')).toHaveLength(2);
    expect(screen.getByTestId('sim-strip-seg-gap').title).toMatch(/cut by a Nova restart/);
    expect(screen.getByTestId('sim-strip-playhead-tag').textContent).toBe('11:42:10');
    expect(screen.getByTestId('sim-strip-replay-state').textContent).toBe('Replay');
    expect(screen.queryByTestId('sim-live-edge')).toBeNull();
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-edge')); });
    expect(posts().at(-1)).toEqual({ path: '/clock', body: { follow_wall: true } });
  });

  it('the transport steps a minute either way and carries the active tab, like a scrub', async () => {
    clock = capture;
    await mount();
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-back')); });
    expect(posts().at(-1)).toEqual({ path: '/clock', body: { minute_from_open: 461, symbol: 'GRML' } });
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-forward')); });
    expect(posts().at(-1)).toEqual({ path: '/clock', body: { minute_from_open: 462, symbol: 'GRML' } });
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-first')); });
    // ⏮ lands on the first recorded second itself (07:30:00 = 3.5 h after the open), not its minute (R22).
    expect(posts().at(-1)).toEqual({ path: '/clock', body: { second_from_open: 12_600, symbol: 'GRML' } });
  });

  it('⏮ reaches a recording that starts mid-minute to the second (R22)', async () => {
    clock = { ...capture, replay_load: { ...capture.replay_load,
      segments: [{ started_et: '2026-09-21T11:46:35.300000-04:00', stopped_et: '2026-09-21T11:47:27-04:00', reason: 'failure' }] } };
    await mount();
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-first')); });
    // 11:46:35.3 from a 04:00 open: 7 h 46 m 36 s, inside the recording, never 11:47:00.
    expect(posts().at(-1)).toEqual({ path: '/clock', body: { second_from_open: 7 * 3600 + 46 * 60 + 36, symbol: 'GRML' } });
  });

  it('a failed replay is a red stretch in the band plus a dismissable chip, never a banner', async () => {
    clock = { ...capture, replay_source: 'none', replay_ok: false, replay_error: 'Capture contains no usable prints' };
    await mount();
    expect(screen.getByTestId('sim-strip-seg-failed').title).toBe('Replay failed: Capture contains no usable prints');
    expect(screen.getByTestId('sim-strip-toast').textContent).toContain('no usable prints');
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Dismiss' })); });
    expect(screen.queryByTestId('sim-strip-toast')).toBeNull();
    expect(screen.getByTestId('sim-strip-seg-failed')).toBeTruthy();
  });

  it('a loaded 09:15-11:30 window is labelled with its own bounds and the ticks that fall in it (V10 / C27)', async () => {
    clock = {
      sim: true, replay_source: 'historical', replay_symbol: 'GRML', replay_date: '2026-09-21', live_edge: false,
      scrubbed: true, minute_from_open: 58, minute_max: 135, sim_time_et: '2026-09-21T10:13:59-04:00',
      session_open_et: '2026-09-21T09:15:00-04:00', session_close_et: '2026-09-21T11:30:00-04:00', session_date: '2026-09-21',
    };
    await mount();
    expect(screen.getByTestId('sim-strip-bound-open').textContent).toBe('09:15');
    expect(screen.getByTestId('sim-strip-bound-close').textContent).toBe('11:30');
    const ticks = screen.getAllByTestId('sim-strip-tick');
    expect(ticks.map(tick => tick.textContent)).toEqual(['09:30']);
    expect(parseFloat(ticks[0].style.left)).toBeCloseTo((15 / 135) * 100, 1);
    expect(parseFloat(screen.getByTestId('sim-strip-playhead').style.left)).toBeCloseTo((58 / 135) * 100, 1);
    expect(screen.getByTestId('sim-strip-band').textContent).not.toMatch(/04:00|20:00|16:00/);
  });

  it('a capture still loading is a neutral pill, never a red failure (C59)', async () => {
    clock = { ...edge, live_edge: false, replay_source: 'none', replay_ok: null, replay_loading: true, replay_error: null };
    await mount();
    expect(screen.getByTestId('sim-strip-replay-loading').textContent).toBe('Loading recording…');
    expect(screen.queryByTestId('sim-strip-seg-failed')).toBeNull();
    expect(screen.queryByTestId('sim-strip-toast')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('a malformed clock or listing never takes the strip down (C6 / C13)', async () => {
    clock = { ...capture, replay_load: { segments: {} }, minute_max: 'x' };
    mocks.fetch.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => url.endsWith('/history') ? { jobs: [{ id: 'j', count: null }], selection: { coverage: [null] } }
        : url.endsWith('/sessions') ? { tickers_by_day: [] }
        : clock,
    }));
    await mount();
    expect(screen.getByTestId('sim-session-strip')).toBeTruthy();
    expect(screen.queryAllByTestId('sim-strip-seg-recorded')).toHaveLength(0);
  });

  it('a locked control says why, and drops its title so the strip title never stacks on it', async () => {
    await mount();
    const edgeButton = screen.getByTestId('sim-strip-edge');
    expect(edgeButton.getAttribute('data-why')).toBe('Already at the live edge');
    expect(edgeButton.getAttribute('title')).toBe('');
    // An open control carries no reason and keeps its own title.
    expect(screen.getByTestId('sim-strip-back').hasAttribute('data-why')).toBe(false);
    expect(screen.getByTestId('sim-strip-back').getAttribute('title')).toBe('Back 1 minute');
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-menu')); });
    expect(screen.getByTestId('sim-strip-follow-wall').getAttribute('data-why')).toBe('Already following the wall clock');
    expect(screen.getByTestId('sim-replay-ticker').getAttribute('data-why')).toBe('Pick a Day first');
  });

  it("off the Sim venue every transport control names the clock's venue", async () => {
    clock = { ...edge, sim: false };
    await mount();
    for (const id of ['sim-strip-first', 'sim-strip-back', 'sim-strip-forward', 'sim-strip-edge', 'sim-strip-day']) {
      const control = screen.getByTestId(id) as HTMLButtonElement;
      expect(control.disabled).toBe(true);
      expect(control.getAttribute('data-why')).toBe("Nova's API is not on the Sim venue -- Sim time cannot move");
    }
    expect(screen.getByRole('button', { name: 'Pause Sim time' }).getAttribute('data-why'))
      .toBe("Nova's API is not on the Sim venue -- Sim time cannot move");
  });

  it('a seek in flight locks the transport with the work it is doing', async () => {
    clock = capture;
    let answer!: (value: unknown) => void;
    const original = mocks.fetch.getMockImplementation()!;
    mocks.fetch.mockImplementation((url: string, init?: RequestInit) => (init?.method === 'POST'
      ? new Promise(resolve => { answer = resolve; }) : original(url, init)));
    await mount();
    await act(async () => { fireEvent.click(screen.getByTestId('sim-strip-back')); });
    expect(screen.getByTestId('sim-strip-forward').getAttribute('data-why')).toBe('Moving the playhead -- wait for Nova to answer');
    await act(async () => { answer({ ok: true, json: async () => capture }); });
    expect(screen.getByTestId('sim-strip-forward').hasAttribute('data-why')).toBe(false);
  });

  it('the scrubber commits one seek on pointer release', async () => {
    clock = capture;
    await mount();
    const slider = screen.getByTestId('sim-session-scrubber');
    await act(async () => {
      fireEvent.pointerDown(slider);
      fireEvent.change(slider, { target: { value: '240' } });
      fireEvent.pointerUp(slider);
    });
    expect(posts()).toEqual([{ path: '/clock', body: { minute_from_open: 240, symbol: 'GRML' } }]);
  });
});
