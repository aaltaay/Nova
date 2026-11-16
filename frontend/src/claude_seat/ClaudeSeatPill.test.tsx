/** @vitest-environment jsdom */
/**
 * The Claude pill and its panel (ADR 068; ADR 072, mockup brain-switches v1): the pill says what Claude is doing and
 * carries Claude's On / Off switch, which flips at once through `PUT /api/traders/claude/switch` and says a refused
 * On in Nova's words under the pill. Take Claude's line, Give it back and Stop Claude are gone.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ClaudeSeatPill } from './ClaudeSeatPill';
import { resetClaudeSeatForTests, setClaudeSeatForTests } from './claudeSeatStore';
import { seatStatus } from './claudeSeatFixtures';
import { CLAUDE_SWITCH_OFF_HELP } from './claudeSeatWords';
import type { ClaudeSeatStatus } from './types';

let served: ClaudeSeatStatus;
const calls: { url: string; method: string; body: string | null }[] = [];
const OFF = { on: false, at: null, can_turn_on: true, why_not_on: null };

function answer(url: string, init?: RequestInit): Response {
  const method = init?.method ?? 'GET';
  if (url.endsWith('/api/traders/claude/switch') && method === 'PUT') {
    const on = JSON.parse(String(init?.body)).on === true;
    served = { ...served, switch: { ...OFF, on }, text: on ? served.text : 'Claude · Off' };
    return new Response(JSON.stringify({ schema_version: 1, traders: {} }), { status: 200 });
  }
  return new Response(JSON.stringify(served), { status: 200 });
}

beforeEach(() => {
  served = seatStatus({ events: [] });
  calls.length = 0;
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? 'GET', body: init?.body == null ? null : String(init.body) });
    return answer(url, init);
  }));
  resetClaudeSeatForTests();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetClaudeSeatForTests();
});

/** The pill on `status`; the seat's own poll answers the same, so a read never undoes what the test set. */
async function mounted(status: ClaudeSeatStatus = seatStatus()) {
  served = status;
  render(<ClaudeSeatPill />);
  act(() => setClaudeSeatForTests(status));
  return screen.findByTestId('claude-pill');
}

describe('ClaudeSeatPill', () => {
  it('says what Claude is doing, and opens the panel with its note, rows and reflexes', async () => {
    const pill = await mounted();
    expect(pill.textContent).toContain('Claude · Buy set SMPL 4.39');
    expect(pill.dataset.state).toBe('buy_set');
    fireEvent.click(screen.getByTestId('claude-pill-open'));
    const panel = screen.getByTestId('claude-panel');
    expect(panel.textContent).toContain('SMPL +54% on news');
    expect(panel.textContent).toContain("Level 2 + Time & Sales on SMPL · Claude's lane");
    expect(panel.textContent).toContain('I stop for the day at -$500');
    expect(screen.getByTestId('claude-panel-reflexes').textContent).toContain('4.30 bid drops under 5,000');
  });

  it('says "Claude · Off", muted, on a day the seat was never on', async () => {
    const pill = await mounted(seatStatus({ state: 'off', on: false, events: [], text: 'Claude · Off', switch: OFF }));
    expect(pill.textContent).toContain('Claude · Off');
    expect(pill.dataset.state).toBe('off');
    expect(pill.className).toContain('claude-pill--off');
  });

  it('shows nothing before the desk has read the seat', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<ClaudeSeatPill />);
    expect(screen.queryByTestId('claude-pill')).toBeNull();
  });

  it('carries the switch on the pill, and the panel no Take line, Give back or Stop Claude', async () => {
    await mounted();
    const sw = screen.getByTestId('claude-switch');
    expect(sw.getAttribute('role')).toBe('switch');
    expect(sw.getAttribute('aria-checked')).toBe('true');
    fireEvent.click(screen.getByTestId('claude-pill-open'));
    expect(screen.getByTestId('claude-panel-switch').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('claude-panel-help').textContent).toBe(CLAUDE_SWITCH_OFF_HELP);
    for (const gone of ['claude-take-line', 'claude-give-back', 'claude-stop']) expect(screen.queryByTestId(gone)).toBeNull();
    expect(screen.queryByText(/Take Claude's line|Stop Claude|Give Claude/)).toBeNull();
  });

  it('turns Claude Off at once, asking nothing, and reads the seat again', async () => {
    await mounted();
    fireEvent.click(screen.getByTestId('claude-switch'));
    await waitFor(() => expect(screen.getByTestId('claude-pill').dataset.switch).toBe('off'));
    const put = calls.find(c => c.method === 'PUT');
    expect(put?.url).toMatch(/\/api\/traders\/claude\/switch$/);
    expect(JSON.parse(put?.body ?? '{}')).toEqual({ on: false });
    expect(calls.some(c => c.url.endsWith('/api/agent/trader') && c.method === 'GET')).toBe(true);
    expect(screen.getByTestId('claude-switch').getAttribute('aria-checked')).toBe('false');
    expect(screen.getByTestId('claude-pill').className).toContain('claude-pill--off');
    // Nothing asked, nothing sold: no POST to the seat's retired routes.
    expect(calls.some(c => /yield|give-back|stop-claude/.test(c.url))).toBe(false);
  });

  it('turns Claude On from the panel too', async () => {
    await mounted(seatStatus({ switch: OFF }));
    fireEvent.click(screen.getByTestId('claude-pill-open'));
    fireEvent.click(screen.getByTestId('claude-panel-switch'));
    await waitFor(() => expect(screen.getByTestId('claude-panel-switch').getAttribute('aria-checked')).toBe('true'));
    expect(JSON.parse(calls.find(c => c.method === 'PUT')?.body ?? '{}')).toEqual({ on: true });
  });

  it("says a refused On under the pill in Nova's words, and never flips", async () => {
    const words = 'Claude stays Off after 15:55 ET: Nova sells its shares then.';
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => (init?.method === 'PUT'
      ? new Response(JSON.stringify({ detail: { reason: 'TRADER_PAST_FLAT_BY', error: words } }), { status: 409 })
      : new Response(JSON.stringify(served), { status: 200 }))));
    await mounted(seatStatus({ switch: OFF }));
    fireEvent.click(screen.getByTestId('claude-switch'));
    expect((await screen.findByTestId('claude-pill-why')).textContent).toBe(words);
    expect(screen.getByTestId('claude-switch').getAttribute('aria-checked')).toBe('false');
    fireEvent.click(screen.getByTestId('claude-pill-why'));
    expect(screen.queryByTestId('claude-pill-why')).toBeNull();
  });

  it('says the refusal inside the panel while it is open', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => (init?.method === 'PUT'
      ? new Response(JSON.stringify({ detail: { reason: 'TRADER_LIVE', error: 'Claude never trades Live.' } }), { status: 409 })
      : new Response(JSON.stringify(served), { status: 200 }))));
    await mounted(seatStatus({ switch: OFF }));
    fireEvent.click(screen.getByTestId('claude-pill-open'));
    fireEvent.click(screen.getByTestId('claude-panel-switch'));
    expect((await screen.findByTestId('claude-panel-why')).textContent).toBe('Claude never trades Live.');
    expect(screen.queryByTestId('claude-pill-why')).toBeNull();
  });

  it('draws no switch for a backend from before it', async () => {
    await mounted(seatStatus({ switch: null }));
    expect(screen.queryByTestId('claude-switch')).toBeNull();
  });
});
