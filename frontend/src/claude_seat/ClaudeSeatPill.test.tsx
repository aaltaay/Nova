/** @vitest-environment jsdom */
/**
 * The Claude pill and its panel (ADR 068): the pill says what Claude is doing; the panel's buttons reach the seat's
 * routes -- Stop Claude only after the operator says yes -- and a refusal is said under them. The lines-full box a
 * 3rd Level 2 shows offers Take Claude's line.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ClaudeLinesFullBox } from './ClaudeLinesFullBox';
import { ClaudeSeatPill } from './ClaudeSeatPill';
import { resetClaudeSeatForTests, setClaudeSeatForTests } from './claudeSeatStore';
import { seatStatus } from './claudeSeatFixtures';
import type { ClaudeSeatStatus } from './types';

const confirmAppMock = vi.fn();
vi.mock('../ux', () => ({ confirmApp: (...args: unknown[]) => confirmAppMock(...args) }));

let served: ClaudeSeatStatus;
const calls: { url: string; method: string }[] = [];

beforeEach(() => {
  served = seatStatus({ events: [] });
  calls.length = 0;
  confirmAppMock.mockReset();
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    calls.push({ url, method });
    if (url.endsWith('/stop-claude') && method === 'POST') {
      return new Response(JSON.stringify({ problems: [], status: { ...served, state: 'off', on: false } }), { status: 200 });
    }
    if (url.endsWith('/yield') && method === 'POST') {
      return new Response(JSON.stringify({ ...served, state: 'yielded', yielded: true, text: 'Claude · Paused by you' }),
        { status: 200 });
    }
    return new Response(JSON.stringify(served), { status: 200 });
  }));
  resetClaudeSeatForTests();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetClaudeSeatForTests();
});

describe('ClaudeSeatPill', () => {
  it('says what Claude is doing, and opens the panel with its note, rows and reflexes', async () => {
    render(<ClaudeSeatPill />);
    act(() => setClaudeSeatForTests(seatStatus()));
    const pill = await screen.findByTestId('claude-pill');
    expect(pill.textContent).toContain('Claude · Buy set SMPL 4.39');
    expect(pill.dataset.state).toBe('buy_set');
    fireEvent.click(pill);
    const panel = screen.getByTestId('claude-panel');
    expect(panel.textContent).toContain('SMPL +54% on news');
    expect(panel.textContent).toContain('1 of 3 · you have 2');
    expect(panel.textContent).toContain('I stop for the day at -$500');
    expect(screen.getByTestId('claude-panel-reflexes').textContent).toContain('4.30 bid drops under 5,000');
  });

  it('shows nothing on a day the seat was never on', () => {
    render(<ClaudeSeatPill />);
    act(() => setClaudeSeatForTests(seatStatus({ state: 'off', on: false, events: [] })));
    expect(screen.queryByTestId('claude-pill')).toBeNull();
  });

  it('Take Claude\'s line posts /yield and the pill says Paused by you', async () => {
    render(<ClaudeSeatPill />);
    act(() => setClaudeSeatForTests(seatStatus()));
    fireEvent.click(await screen.findByTestId('claude-pill'));
    fireEvent.click(screen.getByTestId('claude-take-line'));
    await waitFor(() => expect(calls.some(c => c.url.endsWith('/api/agent/trader/yield') && c.method === 'POST')).toBe(true));
    await waitFor(() => expect(screen.getByTestId('claude-pill').textContent).toContain('Paused by you'));
    expect(screen.getByTestId('claude-give-back')).toBeTruthy();
  });

  it('Stop Claude asks first and sends nothing on a no', async () => {
    confirmAppMock.mockResolvedValueOnce(false);
    render(<ClaudeSeatPill />);
    act(() => setClaudeSeatForTests(seatStatus()));
    fireEvent.click(await screen.findByTestId('claude-pill'));
    fireEvent.click(screen.getByTestId('claude-stop'));
    await waitFor(() => expect(confirmAppMock).toHaveBeenCalledTimes(1));
    expect(String(confirmAppMock.mock.calls[0][0].message)).toContain("Sell Claude's shares and stop it?");
    expect(calls.some(c => c.url.endsWith('/stop-claude'))).toBe(false);
  });

  it('Stop Claude posts /stop-claude on a yes', async () => {
    confirmAppMock.mockResolvedValueOnce(true);
    render(<ClaudeSeatPill />);
    act(() => setClaudeSeatForTests(seatStatus()));
    fireEvent.click(await screen.findByTestId('claude-pill'));
    fireEvent.click(screen.getByTestId('claude-stop'));
    await waitFor(() => expect(calls.some(c => c.url.endsWith('/api/agent/trader/stop-claude') && c.method === 'POST'))
      .toBe(true));
  });

  it('says a refused button under it', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => (init?.method === 'POST'
      ? new Response(JSON.stringify({ detail: { reason: 'AGENT_SEAT_OFF', error: "Claude's seat is off" } }), { status: 409 })
      : new Response(JSON.stringify(served), { status: 200 }))));
    render(<ClaudeSeatPill />);
    act(() => setClaudeSeatForTests(seatStatus()));
    fireEvent.click(await screen.findByTestId('claude-pill'));
    fireEvent.click(screen.getByTestId('claude-take-line'));
    expect((await screen.findByTestId('claude-panel-why')).textContent).toBe("Claude's seat is off");
  });
});

describe('ClaudeLinesFullBox', () => {
  it('names whose lines they are and offers Take Claude\'s line', async () => {
    render(<ClaudeLinesFullBox message="All 3 Level 2 lines are in use: SPIK and FLTX are yours, SMPL is Claude's." />);
    act(() => setClaudeSeatForTests(seatStatus()));
    const box = screen.getByTestId('claude-lines-full');
    expect(box.textContent).toContain('All 3 Level 2 lines are in use');
    expect(box.textContent).toContain('SPIK · you');
    expect(box.textContent).toContain('SMPL · Claude');
    fireEvent.click(screen.getByTestId('claude-lines-full-take'));
    await waitFor(() => expect(calls.some(c => c.url.endsWith('/api/agent/trader/yield') && c.method === 'POST')).toBe(true));
  });
});
