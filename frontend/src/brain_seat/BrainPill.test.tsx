/** @vitest-environment jsdom */
/**
 * The brain's pill and its panel (ADR 072, mockup brain-switches v1 sections 1-2): the pill says what the brain is
 * doing in each of its states and carries the brain's On / Off switch, which flips at once through
 * `PUT /api/traders/brain/switch` and says a refused On in Nova's words under the pill. The panel is the mockup's:
 * head, note, Lane, Position, Today, Limits, Reading now, and what Off does.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BrainPill } from './BrainPill';
import { BRAIN_SWITCH_NO_KEY } from './brainSeatApi';
import {
  BRAIN_DONE, BRAIN_HANDED, BRAIN_OFF, BRAIN_WATCHING, brainTrader, tradersAnswer,
} from './brainSeatFixtures';
import { readBrainSeat } from './brainSeatApi';
import { resetBrainSeatForTests, setBrainSeatForTests } from './brainSeatStore';

/** The Settings overlay's door, as the panel finds it; null where no Settings is mounted. */
const settingsApi = vi.hoisted(() => ({ current: null as null | { openSettings: (section?: string) => void } }));
vi.mock('../settings', () => ({ useSettingsOptional: () => settingsApi.current }));

type Trader = Record<string, unknown>;

/** The brain's TRADER the backend serves now; the switch's PUT flips it and answers the GET shape. */
let served: Trader;
const calls: { url: string; method: string; body: string | null }[] = [];

function answer(url: string, init?: RequestInit): Response {
  const method = init?.method ?? 'GET';
  if (url.endsWith('/api/traders/brain/switch') && method === 'PUT') {
    const on = JSON.parse(String(init?.body)).on === true;
    served = on
      ? { ...served, on: true, state: 'watching', text: 'Brain · Watching' }
      : { ...served, on: false, state: 'off', text: 'Brain · Off' };
  }
  return new Response(JSON.stringify(tradersAnswer(served)), { status: 200 });
}

function stubFetch(fn: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? 'GET', body: init?.body == null ? null : String(init.body) });
    return fn(url, init);
  }));
}

beforeEach(() => {
  served = brainTrader();
  settingsApi.current = null;
  calls.length = 0;
  stubFetch(answer);
  resetBrainSeatForTests();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetBrainSeatForTests();
});

/** The pill on that brain; the store's own poll answers the same, so a read never undoes what the test set. */
async function mounted(over: Trader = {}) {
  served = brainTrader(over);
  render(<BrainPill />);
  act(() => setBrainSeatForTests(readBrainSeat(tradersAnswer(served))));
  return screen.findByTestId('brain-pill');
}

const refuses = (status: number, body: unknown) => stubFetch((_url, init) => (init?.method === 'PUT'
  ? new Response(JSON.stringify(body), { status })
  : new Response(JSON.stringify(tradersAnswer(served)), { status: 200 })));

describe("the brain's pill, state by state", () => {
  it('Off (every morning): "Brain · Off", muted, the switch off', async () => {
    const pill = await mounted(BRAIN_OFF);
    expect(pill.textContent).toBe('Brain · Off');
    expect(pill.className).toContain('brain-pill--off');
    expect(pill.dataset.switch).toBe('off');
    expect(screen.getByTestId('brain-switch').getAttribute('aria-checked')).toBe('false');
  });

  it('On, reading: "Brain · Watching SSII"; "Brain · Watching" with no stock', async () => {
    const pill = await mounted(BRAIN_WATCHING);
    expect(pill.textContent).toBe('Brain · Watching SSII');
    expect(pill.className).toContain('brain-pill--on');
    expect(screen.getByTestId('brain-switch').getAttribute('aria-checked')).toBe('true');
    act(() => setBrainSeatForTests(readBrainSeat(tradersAnswer({
      ...BRAIN_WATCHING, symbol: null, lane: { symbol: null, depth: false, tape: false, why: null },
    }))));
    expect(screen.getByTestId('brain-pill').textContent).toBe('Brain · Watching');
  });

  it('On, in a trade: "Brain · In XLAB +$42.00", the P&L green in mono; red when it is down', async () => {
    const pill = await mounted();
    expect(pill.textContent).toBe('Brain · In XLAB +$42.00');
    expect(pill.dataset.state).toBe('in_trade');
    const pnl = pill.querySelector('.brain-num')!;
    expect(pnl.textContent?.trim()).toBe('+$42.00');
    expect(pnl.className).toContain('is-up');
    act(() => setBrainSeatForTests(readBrainSeat(tradersAnswer({
      position: { symbol: 'XLAB', qty: 200, avg_cost: 4.32, mark: 4.2, unrealized_pnl: -24 },
    }))));
    expect(screen.getByTestId('brain-pill').querySelector('.brain-num')!.className).toContain('is-dn');
  });

  it('day stop reached: "Brain · Done for today -$500" in the red done style', async () => {
    const pill = await mounted(BRAIN_DONE);
    expect(pill.textContent).toBe('Brain · Done for today -$500');
    expect(pill.className).toContain('brain-pill--done');
    expect(pill.querySelector('.brain-num')!.className).toContain('is-dn');
    expect(screen.getByTestId('brain-switch').getAttribute('aria-checked')).toBe('false');
  });

  it('Off, you hold its trade: "Brain · Off · XLAB is yours to close" in the amber wait style', async () => {
    const pill = await mounted(BRAIN_HANDED);
    expect(pill.textContent).toBe('Brain · Off · XLAB is yours to close');
    expect(pill.className).toContain('brain-pill--wait');
  });

  it('On with its program not running: says so in the amber wait style, on the pill and in the panel', async () => {
    const pill = await mounted({ ...BRAIN_WATCHING, connected: false });
    expect(pill.textContent).toBe('Brain · On · its program is not running');
    expect(pill.className).toContain('brain-pill--wait');
    expect(screen.getByTestId('brain-pill-open').getAttribute('title')).toMatch(/has not checked in/);
    fireEvent.click(screen.getByTestId('brain-pill-open'));
    expect(screen.getByTestId('brain-panel-title').textContent).toBe('Brain · On · its program is not running');
    expect(screen.getByTestId('brain-panel-not-running').textContent).toMatch(/makes no new trade/);
  });

  it('shows nothing before the desk has read the traders view, and nothing on a backend without one', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
    render(<BrainPill />);
    expect(screen.queryByTestId('brain-pill')).toBeNull();
    cleanup();
    resetBrainSeatForTests();
    stubFetch(() => new Response('{}', { status: 404 }));
    render(<BrainPill />);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(screen.queryByTestId('brain-pill')).toBeNull();
  });

  it('a read that fails before any answer says so on the pill, never "Off"', async () => {
    stubFetch(() => new Response('{}', { status: 500 }));
    render(<BrainPill />);
    const pill = await screen.findByTestId('brain-pill');
    expect(pill.textContent).toBe('Brain · Nova did not answer');
    expect(pill.getAttribute('title')).toBe('The brain: The traders view answered 500.');
    expect(screen.queryByTestId('brain-switch')).toBeNull();
  });

  it('a read that fails later keeps the last words and says why on the pill', async () => {
    const pill = await mounted(BRAIN_WATCHING);
    act(() => setBrainSeatForTests(readBrainSeat(tradersAnswer(served)), 'The traders view answered 502.'));
    expect(pill.textContent).toBe('Brain · Watching SSII');
    expect(screen.getByTestId('brain-pill-open').getAttribute('title')).toBe('The brain: The traders view answered 502.');
    fireEvent.click(screen.getByTestId('brain-pill-open'));
    expect(screen.getByTestId('brain-panel-read-error').textContent).toBe('The traders view answered 502.');
  });

  it('polls the traders view, the one route it reads', async () => {
    await mounted();
    await waitFor(() => expect(calls.some(c => c.url.endsWith('/api/traders') && c.method === 'GET')).toBe(true));
    expect(calls.every(c => c.url.endsWith('/api/traders'))).toBe(true);
  });
});

describe("the brain's switch", () => {
  it('is a switch on the pill and in the panel', async () => {
    await mounted();
    const sw = screen.getByTestId('brain-switch');
    expect(sw.getAttribute('role')).toBe('switch');
    expect(sw.getAttribute('aria-checked')).toBe('true');
    fireEvent.click(screen.getByTestId('brain-pill-open'));
    const big = screen.getByTestId('brain-panel-switch');
    expect(big.getAttribute('role')).toBe('switch');
    expect(big.getAttribute('aria-checked')).toBe('true');
    expect(big.className).toContain('is-big');
  });

  it('turns the brain Off at once, asking nothing, and shows the answer', async () => {
    await mounted();
    fireEvent.click(screen.getByTestId('brain-switch'));
    await waitFor(() => expect(screen.getByTestId('brain-pill').dataset.switch).toBe('off'));
    const put = calls.find(c => c.method === 'PUT');
    expect(put?.url).toMatch(/\/api\/traders\/brain\/switch$/);
    expect(JSON.parse(put?.body ?? '{}')).toEqual({ on: false });
    expect(screen.getByTestId('brain-switch').getAttribute('aria-checked')).toBe('false');
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(calls.filter(c => c.method !== 'GET')).toHaveLength(1);
  });

  it('turns the brain On from the panel too', async () => {
    await mounted(BRAIN_OFF);
    fireEvent.click(screen.getByTestId('brain-pill-open'));
    fireEvent.click(screen.getByTestId('brain-panel-switch'));
    await waitFor(() => expect(screen.getByTestId('brain-panel-switch').getAttribute('aria-checked')).toBe('true'));
    expect(JSON.parse(calls.find(c => c.method === 'PUT')?.body ?? '{}')).toEqual({ on: true });
  });

  it("says a refused On under the pill in Nova's words, and never flips", async () => {
    const words = 'The brain stays Off after 15:55 ET: Nova sells its shares then.';
    await mounted(BRAIN_OFF);
    refuses(409, { detail: { reason: 'TRADER_PAST_FLAT_BY', error: words } });
    fireEvent.click(screen.getByTestId('brain-switch'));
    const why = await screen.findByTestId('brain-pill-why');
    expect(why.textContent).toBe(words);
    expect(why.getAttribute('role')).toBe('alert');
    expect(screen.getByTestId('brain-switch').getAttribute('aria-checked')).toBe('false');
    fireEvent.click(why);
    expect(screen.queryByTestId('brain-pill-why')).toBeNull();
  });

  it.each([
    ['TRADER_LIVE', 'The brain never trades Live.'],
    ['TRADER_DAY_STOP', 'The brain reached its day stop today.'],
    ['TRADER_OPERATOR_ONLY', 'Only you switch the brain On.'],
    ['REMOTE_VIEW_ONLY', 'This device only looks: switch the brain on the desk.'],
  ])('says the %s refusal as the backend wrote it', async (reason, words) => {
    await mounted(BRAIN_OFF);
    refuses(409, { detail: { reason, error: words } });
    fireEvent.click(screen.getByTestId('brain-switch'));
    expect((await screen.findByTestId('brain-pill-why')).textContent).toBe(words);
  });

  it.each([401, 503])("says the desk's API key is missing on a %i", async (status) => {
    await mounted(BRAIN_OFF);
    refuses(status, { detail: 'Not authenticated' });
    fireEvent.click(screen.getByTestId('brain-switch'));
    expect((await screen.findByTestId('brain-pill-why')).textContent).toBe(BRAIN_SWITCH_NO_KEY);
  });

  it('says the refusal inside the panel while it is open', async () => {
    await mounted(BRAIN_OFF);
    refuses(409, { detail: { reason: 'TRADER_LIVE', error: 'The brain never trades Live.' } });
    fireEvent.click(screen.getByTestId('brain-pill-open'));
    fireEvent.click(screen.getByTestId('brain-panel-switch'));
    expect((await screen.findByTestId('brain-panel-why')).textContent).toBe('The brain never trades Live.');
    expect(screen.queryByTestId('brain-pill-why')).toBeNull();
  });
});

describe("the brain's panel", () => {
  async function opened(over: Trader = {}) {
    await mounted(over);
    fireEvent.click(screen.getByTestId('brain-pill-open'));
    return screen.getByTestId('brain-panel');
  }

  it('opens on the words, and closes on Escape and on a press outside', async () => {
    const panel = await opened();
    expect(panel.getAttribute('role')).toBe('dialog');
    expect(screen.getByTestId('brain-pill-open').getAttribute('aria-expanded')).toBe('true');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('brain-panel')).toBeNull();
    fireEvent.click(screen.getByTestId('brain-pill-open'));
    fireEvent.mouseDown(screen.getByTestId('brain-panel'));
    expect(screen.getByTestId('brain-panel')).toBeTruthy();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId('brain-panel')).toBeNull();
  });

  it("heads with the pill's words without the P&L, the venue and lane, and On beside the big switch", async () => {
    const panel = await opened();
    expect(screen.getByTestId('brain-panel-title').textContent).toBe('Brain · In XLAB');
    expect(panel.querySelector('.brain-panel__sub')!.textContent).toBe('Paper · lane 3');
    expect(panel.querySelector('.brain-panel__switch')!.textContent).toBe('On');
  });

  it("says the brain's note under its ET time, and hides the box with no note", async () => {
    await opened();
    const note = screen.getByTestId('brain-panel-note');
    expect(note.querySelector('b')!.textContent).toBe('The brain, 10:41');
    expect(note.textContent).toContain('Held the 4.30 bid three times with buyers lifting 4.32.');
    cleanup();
    resetBrainSeatForTests();
    await opened({ note: null });
    expect(screen.queryByTestId('brain-panel-note')).toBeNull();
  });

  it('lists Lane, Position, Today and Limits as the mockup words them', async () => {
    await opened({ today: { pnl: -120, loss_limit_usd: -500, tripped_at: null } });
    expect(screen.getByTestId('brain-panel-lane').textContent).toBe('LaneLevel 2 + Time & Sales on XLAB');
    expect(screen.getByTestId('brain-panel-position').textContent).toBe('Position200 XLAB at 4.32 · now 4.53');
    const today = screen.getByTestId('brain-panel-today');
    expect(today.textContent).toBe('Today-$120.00day stop -$500');
    expect(today.querySelector('.brain-num')!.className).toContain('is-dn');
    expect((screen.getByTestId('brain-panel-meter').firstElementChild as HTMLElement).style.width).toBe('24%');
    expect(screen.getByTestId('brain-panel-limits').textContent).toBe('Limits1,000 sh · $150 risk · -$500 day · Settings');
  });

  it('its Settings link opens Settings on the loss limits, where each trader has a column', async () => {
    const openSettings = vi.fn();
    settingsApi.current = { openSettings };
    await opened();
    fireEvent.click(screen.getByTestId('brain-panel-settings'));
    expect(openSettings).toHaveBeenCalledWith('loss_limits');
  });

  it('says a lane still waiting for its Level 2, no stock yet, and no position', async () => {
    await opened({ ...BRAIN_WATCHING, lane: { symbol: 'SSII', depth: false, tape: false, why: null } });
    expect(screen.getByTestId('brain-panel-lane').textContent).toBe("LaneWaiting for SSII's Level 2");
    expect(screen.getByTestId('brain-panel-position').textContent).toBe('PositionNone');
    cleanup();
    resetBrainSeatForTests();
    await opened(BRAIN_OFF);
    expect(screen.getByTestId('brain-panel-lane').textContent).toBe('LaneNo stock yet');
    expect((screen.getByTestId('brain-panel-meter').firstElementChild as HTMLElement).style.width).toBe('0%');
  });

  it('lists what it is reading now, its own lane tagged in purple, and hides the list when empty', async () => {
    await opened();
    const reading = screen.getByTestId('brain-panel-reading');
    expect(within(reading).getByText('Reading now')).toBeTruthy();
    const rows = [...reading.querySelectorAll('.brain-panel__read')];
    expect(rows.map(r => r.textContent)).toEqual([
      'XLABFirst pullback, goits lane', 'SSII5-minute flat top, 3 touchesLevel 1', 'RUNRBull flag formingLevel 1',
    ]);
    expect(rows[0].querySelector('b')!.textContent).toBe('XLAB');
    expect(rows[0].querySelector('.brain-panel__tag')!.className).toContain('is-lane');
    expect(rows[1].querySelector('.brain-panel__tag')!.className).not.toContain('is-lane');
    cleanup();
    resetBrainSeatForTests();
    await opened({ reading: [] });
    expect(screen.queryByTestId('brain-panel-reading')).toBeNull();
  });

  it('says what Off does, naming the stock it holds; generic words when it holds nothing', async () => {
    await opened();
    expect(screen.getByTestId('brain-panel-help').textContent).toBe(
      'Off: no new trades. Its working entries are cancelled. XLAB and its stop stay as they are, and XLAB is yours to close.');
    cleanup();
    resetBrainSeatForTests();
    await opened(BRAIN_WATCHING);
    expect(screen.getByTestId('brain-panel-help').textContent).toBe(
      'Off: no new trades. Its working entries are cancelled. Its open trade and its stop stay as they are, and the trade is yours to close.');
  });

  it('Off with a trade handed to you: the position row says it is yours to close, its stop resting', async () => {
    await opened(BRAIN_HANDED);
    expect(screen.getByTestId('brain-panel-title').textContent).toBe('Brain · Off · XLAB is yours to close');
    expect(screen.getByTestId('brain-panel-position').textContent).toBe('Position200 XLAB · yours to close · stop 4.19');
    expect(screen.getByTestId('brain-panel').querySelector('.brain-panel__switch')!.textContent).toBe('Off');
  });
});
