/**
 * @vitest-environment jsdom
 *
 * The one Bots page (ADR 044, approved mockup v8): the answer line ("Can Nova buy right now?"), the Bot
 * card -- the one switch, Freeze all orders, the sleeve -- and the page shell. The strategies, the Level 2
 * lines, Tickers today and the last row have their own file (BotsPageCards.test.tsx).
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { resetHotListForTests } from '../hot_list';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BotsPage } from './BotsPage';
import { BOT_SWITCH_LIVE_WHY } from './botSwitch';
import {
  botsFetchRouter,
  openGates,
  refusal,
  session,
  strategySession,
  triggersView,
  type BotsFetchOpts,
} from './botsPageFixtures';
import { shortProofView } from './shortProofFixtures';

const ibkrStatus = {
  connected: true,
  spend_status: 'paper_armed',
  spend_locked_reason: null as string | null,
  trading_allowed: true as boolean,
  trading_allowed_reason: null as string | null,
  armed: true as boolean,
  lastSuccessAt: 1 as number | null,
  stale: false,
};
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ibkrStatus }));
// The padlock is the backend latch (ADR 018): this status's `armed` is the one answer.
vi.mock('../ibkr/ticketUnlock', () => ({
  readTicketSessionUnlocked: () => ibkrStatus.armed === true,
  subscribeTicketSessionUnlock: () => () => {},
  unlockNeedsPin: () => true,
  livePinMissing: () => false,
  unlockTicketSession: async () => ({ ok: true, code: null, message: null }),
  lockTicketSession: async () => ({ ok: true, code: null, message: null }),
}));
const openStockView = vi.fn();
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ openStockView, traderLiveTabs: ['GRML'], selectedSymbol: null, ibkrMode: 'paper' }),
}));
// The real PIN field (input-otp) needs layout APIs jsdom lacks; the dialog opening is what is tested.
vi.mock('../ibkr/TradingPinDialog', () => ({
  TradingPinDialog: ({ open }: { open: boolean }) => (open ? <div role="dialog">PIN</div> : null),
}));
const confirmApp = vi.fn(async () => true);
vi.mock('../ux/appDialogApi', () => ({ confirmApp: (...args: unknown[]) => confirmApp(...(args as [])) }));

/** 2026-09-30 09:42 ET. */
const AT_0942 = Date.UTC(2026, 8, 30, 13, 42) / 1000;

beforeEach(() => {
  ibkrStatus.armed = true;
  ibkrStatus.lastSuccessAt = 1;
  ibkrStatus.trading_allowed = true;
  ibkrStatus.trading_allowed_reason = null;
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  resetHotListForTests();
});

afterEach(() => {
  cleanup();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  resetHotListForTests();
  vi.unstubAllGlobals();
  localStorage.clear();
  openStockView.mockReset();
  confirmApp.mockClear();
});

function mockFetch(opts: BotsFetchOpts = {}) {
  const fetchMock = vi.fn(botsFetchRouter(opts));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function flush() {
  for (let i = 0; i < 6; i += 1) await Promise.resolve();
}

async function renderPage() {
  await act(async () => {
    render(<BotsPage />);
    await flush();
  });
  await act(async () => { await flush(); });
}

const called = (fetchMock: ReturnType<typeof mockFetch>, part: string, method?: string) =>
  fetchMock.mock.calls.some(([url, init]) => String(url).includes(part)
    && (!method || (init as RequestInit | undefined)?.method === method));

const switchBodies = (fetchMock: ReturnType<typeof mockFetch>) =>
  fetchMock.mock.calls.filter(([url]) => String(url).includes('/session/switch'))
    .map(([, init]) => String((init as RequestInit | undefined)?.body ?? ''));

async function press(testId: string) {
  await act(async () => { fireEvent.click(screen.getByTestId(testId)); await flush(); });
  await act(async () => { await flush(); });
}

describe('Can Nova buy right now? (ADR 044)', () => {
  it('says No for every ticker while the Bot is off, with each stock-wide reason and its fix', async () => {
    mockFetch({ session: session() });
    await renderPage();
    expect(screen.getByTestId('bots-answer-headline').textContent).toBe('No, on any ticker:');
    expect(screen.getByTestId('bots-answer-bot').textContent).toMatch(/^the Bot is off: Off\. The strategies at Eyes or On still alert you\.Turn on…$/);
    // A strategy is at On: with the Bot off the switch is the reason, said once -- not "no strategy at On".
    expect(screen.queryByTestId('bots-answer-setups')).toBeNull();
    expect(screen.queryByTestId('bots-answer-window')).toBeNull();
    // The level gate is the switch itself: said once, as "the Bot is off".
    expect(screen.queryByTestId('bots-answer-level')).toBeNull();
    expect(screen.getByTestId('bots-answer-chip-venue').className).toContain('is-ok');
  });

  it('says no strategy is at On when none is, with its fix', async () => {
    mockFetch({ session: session({ setup_levels: { first_pullback: 1, bull_flag: 1, flat_top_breakout: 0, red_to_green: 0 },
      setups: [{ id: 'first_pullback', scanner: true, level: 1, effective: 1 }, { id: 'bull_flag', scanner: true, level: 1, effective: 1 }] }) });
    await renderPage();
    expect(screen.getByTestId('bots-answer-setups').textContent).toBe('No strategy is at On: set one to On on its card.Set one to On');
  });

  it('names the tickers Nova would buy at their next go trigger', async () => {
    const view = triggersView();
    const tickers = view.tickers as Record<string, unknown>[];
    tickers[0] = { ...tickers[0], now: { cells: {}, answer: 'yes', reasons: [] } };
    mockFetch({ session: strategySession({ bot_on: true, active: true, ready: true }), triggers: view });
    await renderPage();
    expect(screen.getByTestId('bots-answer-headline').textContent).toBe('Yes, on GRML: at the next go trigger');
    expect(screen.queryByTestId('bots-answer-bot')).toBeNull();
  });

  it('offers the padlock from a locked padlock, and says the all-stop in full', async () => {
    ibkrStatus.armed = false;
    mockFetch({ session: strategySession({
      bot_on: true, active: true,
      gates: openGates({ padlock: { ok: false, detail: { reason: null } }, day_lock: { ok: false, detail: { venue: 'paper' } } }),
      day_lock: { active: true, until: '2026-10-01T04:00:00-04:00', tripped_at: AT_0942, pnl: -212.4, venue: 'paper' },
    }) });
    await renderPage();
    expect(screen.getByTestId('bots-answer-day_lock').textContent).toBe('All-stop fired at 09:42 ET at −$212.40: bot and '
      + 'manual buys on Paper are locked until 04:00 ET on Oct 1. Flatten and cancel still work.');
    expect(screen.getByTestId('bots-answer-chip-day_lock').className).toContain('is-no');
    expect(screen.getByTestId('bots-answer-chip-padlock').className).toContain('is-no');
    await press('bots-answer-fix-padlock');
    expect(screen.getByRole('dialog')).toBeTruthy();
  });
});

describe('the Bot switch (ADR 044)', () => {
  it('turns on with one press -- no dial, no Activate -- and off again', async () => {
    const fetchMock = mockFetch({ session: strategySession() });
    await renderPage();
    const sw = screen.getByTestId('bots-switch');
    expect(sw.getAttribute('aria-checked')).toBe('false');
    expect(screen.queryByTestId('bots-activate')).toBeNull();
    expect(screen.queryByTestId('bots-level-2')).toBeNull();
    await press('bots-switch');
    expect(switchBodies(fetchMock)).toEqual(['{"on":true}']);
    expect(screen.getByTestId('bots-switch').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('bots-switch-why').textContent).toMatch(/^On for Paper\./);
    await press('bots-switch');
    expect(switchBodies(fetchMock)).toEqual(['{"on":true}', '{"on":false}']);
    expect(called(fetchMock, '/session/arm')).toBe(false);
    expect(confirmApp).not.toHaveBeenCalled();
  });

  it('is locked on Live with the reason, and never presses', async () => {
    const fetchMock = mockFetch({ session: strategySession({ level_venue: 'live' }) });
    await renderPage();
    const sw = screen.getByTestId('bots-switch') as HTMLButtonElement;
    expect(sw.disabled).toBe(true);
    expect(sw.getAttribute('data-why')).toBe(BOT_SWITCH_LIVE_WHY);
    await press('bots-switch');
    expect(switchBodies(fetchMock)).toEqual([]);
  });

  it('after the bot trip, asks in words, and sends reenable only after a yes', async () => {
    const fetchMock = mockFetch({ session: strategySession({ soft_breaker: { fired: true, at: AT_0942, pnl: -52.1, until: null } }) });
    await renderPage();
    expect(screen.getByTestId('bots-switch-why').textContent).toBe('Off since the bot trip at 09:42 ET. It lifts at 04:00.');
    confirmApp.mockImplementationOnce(async () => false);
    await press('bots-switch');
    expect(String(JSON.stringify(confirmApp.mock.calls[0])))
      .toMatch(/The bot trip fired at 09:42 ET when the day's P&L hit −\$52\.10\. Turn the bot back on for the rest of today\?/);
    expect(switchBodies(fetchMock)).toEqual([]);
    await press('bots-switch');
    expect(switchBodies(fetchMock)).toEqual(['{"on":true,"reenable":true}']);
  });

  it('shows the backend\'s refusal in its own words', async () => {
    mockFetch({ session: strategySession(), onSwitch: () => refusal(409, 'BOT_PADLOCK_LOCKED', 'The padlock is locked -- unlock it first') });
    await renderPage();
    await press('bots-switch');
    expect(screen.getByTestId('bots-error').textContent).toBe('The padlock is locked — unlock it first');
    expect(screen.getByTestId('bots-switch').getAttribute('aria-checked')).toBe('false');
  });

  it('says why the backend turned it off, and why an on Bot is not trading now', async () => {
    mockFetch({ session: strategySession({ deactivated: { at: AT_0942, reason: 'restart', text: 'Not active -- the backend restarted' } }) });
    await renderPage();
    expect(screen.getByTestId('bots-switch-why').textContent).toBe('Turned off at 09:42 ET — the backend restarted.');
    cleanup();
    _resetBotSessionPollerForTests();
    mockFetch({ session: strategySession({ bot_on: true, active: true, ready: false, ready_reason: 'every bot window is closed' }) });
    await renderPage();
    expect(screen.getByTestId('bots-switch-why').textContent).toBe('On for Paper. One bot for both sides: each strategy at On trades its own side. Not trading now — every bot window is closed.');
  });

  it('shows the bot\'s own trade', async () => {
    mockFetch({ session: strategySession({ bot_on: true, active: true, trade: {
      setup_id: 'g1', setup_type: 'first_pullback', symbol: 'GRML', venue: 'paper', state: 'open', qty: 1,
      trigger: 8.72, entry_planned: 8.73, stop: 8.52, target1: 8.92, risk: 0.21, entry_fill_price: 8.73,
    } as never }) });
    await renderPage();
    expect(screen.getByTestId('bots-trade').textContent).toBe('In GRML ▲ long (first pullback) · 1 @ 8.73 · stop 8.52 · target 8.92');
  });

  it('offers the API key field when a write needs the key', async () => {
    mockFetch({ session: strategySession(), onSwitch: () => ({ ok: false, status: 401, json: async () => ({ detail: 'Invalid or missing X-Nova-Api-Key' }) }) });
    await renderPage();
    await press('bots-switch');
    expect(screen.getByTestId('bots-error').textContent).toMatch(/Need Nova API key/i);
    expect(screen.getByTestId('bots-api-key')).toBeTruthy();
  });

  it('never turns the Bot off from the page when the padlock reads locked: the backend does', async () => {
    ibkrStatus.armed = false;
    const fetchMock = mockFetch({ session: strategySession({ bot_on: true, active: true }) });
    await renderPage();
    expect(switchBodies(fetchMock)).toEqual([]);
    expect(called(fetchMock, '/session/disarm')).toBe(false);
  });
});

describe('Freeze all orders (ADR 044)', () => {
  it('freezes every order, says what it cancelled on each venue, then offers Unfreeze', async () => {
    const fetchMock = mockFetch({ killSweep: [
      { venue: 'paper', cancelled: [101, 102], failed: [], error: null },
      { venue: 'sim', cancelled: [], failed: [], error: null },
      { venue: 'live', cancelled: [], failed: [], error: 'Gateway disconnected: Live orders were not swept' },
    ] });
    await renderPage();
    const card = within(screen.getByTestId('bots-freeze'));
    const trip = card.getByTestId('bots-kill-trip');
    expect(trip.textContent).toMatch(/Freeze all orders/);
    await act(async () => { fireEvent.click(trip); await flush(); });
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(called(fetchMock, '/kill-switch', 'POST')).toBe(true);
    expect(screen.getByTestId('bots-kill-sweep-paper').textContent).toBe('Paper: cancelled 2 orders (#101, #102)');
    expect(screen.getByTestId('bots-kill-sweep-live').textContent).toBe('Live: Gateway disconnected: Live orders were not swept');
    expect(screen.getByTestId('bots-kill-reset').textContent).toMatch(/Unfreeze orders/);
    await act(async () => { fireEvent.click(screen.getByTestId('bots-kill-reset')); await flush(); });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/kill-switch/reset'))).toBe(true);
  });
});

describe('the Live short proof (ADR 048 step 6)', () => {
  it('lists the operator\'s steps on the Bot card, under Freeze all orders, each ticked from what Nova sees', async () => {
    const fetchMock = mockFetch();
    await renderPage();
    expect(called(fetchMock, '/short-proof')).toBe(true);
    const proof = screen.getByTestId('bots-short-proof');
    expect(within(screen.getByTestId('bots-bot-card')).getByTestId('bots-short-proof')).toBe(proof);
    expect(screen.getByTestId('bots-freeze').compareDocumentPosition(proof) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
    expect(screen.getByTestId('bots-proof-count').textContent).toBe('0 of 7 days and drills');
    expect(proof.getAttribute('data-complete')).toBe('false');
    const step = (id: string) => screen.getByTestId(`bots-proof-step-${id}`);
    expect(step('margin_account').getAttribute('data-ok')).toBe('true');
    expect(step('margin_account').textContent).toContain('✓');
    expect(step('drill_freeze').getAttribute('data-ok')).toBe('false');
    expect(step('drill_freeze').textContent).toContain('✗Freeze all orders with a short open');
    // Only the operator can judge a Paper day or set the switch: the step says "you".
    expect(step('paper_days').textContent).toContain('you');
    expect(step('live_key').textContent).toContain('you');
    expect(step('practice_reset').textContent).not.toContain('you');
    // A step not done says what to do, and whether the door reads it.
    const tip = step('drill_freeze').getAttribute('data-tip') ?? '';
    expect(tip).toContain('To do: Run the freeze all orders with a short open drill on Paper.');
    expect(tip).toContain('The execution door refuses every Live short until this step is done.');
    expect(step('practice_reset').getAttribute('data-tip')).toContain('Shown for you: the door does not read this step.');
  });

  it('says so when the proof is complete', async () => {
    mockFetch({ shortProof: shortProofView({ complete: true, done: 7 }) });
    await renderPage();
    expect(screen.getByTestId('bots-proof-count').textContent).toBe('7 of 7 days and drills');
    expect(screen.getByTestId('bots-short-proof').textContent).toContain('The Paper days and the drills are done.');
  });

  it('says why when the backend has no proof, never a checklist that reads done', async () => {
    const router = botsFetchRouter();
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => (String(url).includes('/short-proof')
      ? { ok: false, status: 404, json: async () => ({ detail: 'Not Found' }) }
      : router(url, init))));
    await renderPage();
    expect(screen.getByTestId('bots-proof-error').textContent)
      .toBe('The Live short proof could not be read: This backend has no Live short proof yet: reload the backend after the update.');
    expect(screen.queryByTestId('bots-proof-count')).toBeNull();
  });
});

describe('the page', () => {
  it('lays the sections out in the approved order, with nothing of the old hero', async () => {
    mockFetch();
    await renderPage();
    const order = ['bots-answer', 'bots-bot-card', 'bots-strategies', 'bots-lines', 'bots-tickers', 'bots-today', 'bots-activity']
      .map(id => screen.getByTestId(id));
    for (let i = 1; i < order.length; i += 1) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    expect(within(screen.getByTestId('bots-bot-card')).getByTestId('bots-risk')).toBeTruthy();
    expect(screen.queryByTestId('bots-hero')).toBeNull();
    expect(screen.queryByTestId('bots-symbols')).toBeNull();
    expect(screen.getByTestId('bots-venue').textContent).toMatch(/Paper.*Nova Paper — fake money on the live feed/);
  });

  it('credits the playbook to the operator\'s own course material, by no vendor name', async () => {
    mockFetch();
    await renderPage();
    const head = screen.getByTestId('bots-strategies').querySelector('h3');
    expect(head?.textContent).toBe('Strategies from your course material');
  });
});
