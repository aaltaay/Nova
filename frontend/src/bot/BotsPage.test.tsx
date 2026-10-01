/**
 * @vitest-environment jsdom
 *
 * The Bots page (approved mockup v4, ADR 042): the hero -- state and why, the master
 * level, every gate as a chip in two groups whose link opens it, one Activate and the
 * kill switch -- and the page shell. The cards have their own file (BotsPageCards.test.tsx).
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BotsPage } from './BotsPage';
import {
  botsFetchRouter,
  gates,
  openGates,
  refusal,
  session,
  strategySession,
  type BotsFetchOpts,
} from './botsPageFixtures';

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
});

afterEach(() => {
  cleanup();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
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
  for (let i = 0; i < 4; i += 1) await Promise.resolve();
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

const armBody = (fetchMock: ReturnType<typeof mockFetch>) =>
  String((fetchMock.mock.calls.find(([url]) => String(url).includes('/session/arm'))?.[1] as RequestInit | undefined)?.body ?? '');

describe('Bots page hero (ADR 042)', () => {
  it('draws every gate as a chip in two groups -- what Activate needs, what each order meets', async () => {
    mockFetch({ session: strategySession(), dayPnl: -9.54 });
    await renderPage();
    const activate = within(screen.getByTestId('bots-gates-activate'));
    const fire = within(screen.getByTestId('bots-gates-fire'));
    expect(activate.getByTestId('bots-gate-venue').textContent).toMatch(/Venue Paper/);
    expect(activate.getByTestId('bots-gate-setups').textContent).toMatch(/At Strategy · First pullback/);
    expect(activate.getByTestId('bots-gate-bot_trip').textContent).toMatch(/Bot trip clear \(−\$9\.54 \/ −\$50\)/);
    expect(fire.getByTestId('bots-gate-depth_lines').textContent).toMatch(/Depth line held · GRML · IBKR allows 3 — open IMCC Level 2/);
    expect(fire.getByTestId('bots-gate-window').textContent).toMatch(/Bot window open · First pullback 07:00–10:00/);
    expect(fire.getByTestId('bots-gate-daily_cap').textContent).toMatch(/Nova entries 0 \/ 1 today/);
    // Every chip explains itself.
    const chipText = screen.getByTestId('bots-gate-level').querySelector('.bots-gate__text');
    expect(chipText?.getAttribute('data-tip')).toMatch(/master level/);
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Not active');
    expect(screen.getByTestId('bots-hero-sentence').textContent).toBe('Strategy on Paper: the bot may trade GO triggers of '
      + 'First pullback on its 2 stocks set to Bot once you press Activate. Until then they propose like Eyes.');
    expect(screen.getByTestId('bots-hero-stocks').textContent)
      .toBe('2 stocks set to Bot · risk $20 a trade · max 1 share · $50 budget · 1 Nova entry a day');
    expect(screen.getByTestId('bots-activate-hint').textContent).toBe('Every Activate gate is open.');
  });

  it('the dial is the master ceiling: what each level lets any setup do on this venue', async () => {
    mockFetch({ session: session({ level: 0 }) });
    await renderPage();
    expect(screen.getByTestId('bots-hero').textContent).toMatch(/Master level · the most any setup may do on Paper/);
    expect(screen.getByTestId('bots-level-0').textContent).toMatch(/Nothing proposes or trades · every scanner scores in silence/);
    expect(screen.getByTestId('bots-level-1').textContent).toMatch(/Setups may propose · you place/);
    expect(screen.getByTestId('bots-level-2').textContent).toMatch(/Setups at Strategy may trade after Activate \(Paper, Sim\)/);
    expect(screen.getByTestId('bots-hero').textContent).not.toMatch(/chosen setup|Bot is in control/);
  });

  it('locks Activate with every closed Activate gate\'s reason, and never presses it', async () => {
    const fetchMock = mockFetch({ session: session() });
    await renderPage();
    const activate = screen.getByTestId('bots-activate') as HTMLButtonElement;
    expect(activate.disabled).toBe(true);
    expect(activate.getAttribute('data-why')).toBe('The master level is Eyes: choose Strategy on the dial first. '
      + 'No setup is at Strategy: set a setup card\'s own switch to Strategy.');
    expect(screen.getByTestId('bots-activate-hint').textContent).toMatch(/^Can't Activate yet: The master level is Eyes/);
    await act(async () => { fireEvent.click(activate); await flush(); });
    expect(called(fetchMock, '/session/arm')).toBe(false);
  });

  it('locks Activate on Live: bot trading there is not built', async () => {
    mockFetch({ session: strategySession({ gates: openGates({ venue: { ok: false, detail: { venue: 'live' } } }) }) });
    await renderPage();
    const activate = screen.getByTestId('bots-activate') as HTMLButtonElement;
    expect(activate.disabled).toBe(true);
    expect(activate.getAttribute('data-why')).toMatch(/Live trading by a bot is not built/);
    expect(screen.getByTestId('bots-gate-venue').textContent).toMatch(/Live — the bot does not trade here/);
  });

  it('Activate sends no reenable when the bot trip has not fired', async () => {
    const fetchMock = mockFetch({ session: strategySession() });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-activate')); await flush(); });
    expect(armBody(fetchMock)).toBe('{}');
    expect(confirmApp).not.toHaveBeenCalled();
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Active');
    expect(screen.getByTestId('bots-stop')).toBeTruthy();
  });

  it('after a bot trip, Activate asks in words, and sends reenable only after a yes', async () => {
    const trip = openGates({ bot_trip: { ok: false, detail: { fired_at: AT_0942, pnl: -52.1, until: null } } });
    const fetchMock = mockFetch({ session: strategySession({ gates: trip }) });
    await renderPage();
    const activate = screen.getByTestId('bots-activate') as HTMLButtonElement;
    expect(activate.disabled).toBe(false);
    expect(activate.textContent).toMatch(/Activate · re-enable/);
    expect(screen.getByTestId('bots-gate-bot_trip').textContent).toMatch(/Bot trip fired 09:42 ET \(−\$52\.10\)/);
    confirmApp.mockImplementationOnce(async () => false);
    await act(async () => { fireEvent.click(activate); await flush(); });
    expect(String(JSON.stringify(confirmApp.mock.calls[0]))).toMatch(/The bot trip fired at 09:42 ET \(P&L −\$52\.10\)\. Activate re-enables the bot for today\./);
    expect(called(fetchMock, '/session/arm')).toBe(false);
    await act(async () => { fireEvent.click(screen.getByTestId('bots-activate')); await flush(); });
    expect(armBody(fetchMock)).toBe('{"reenable":true}');
  });

  it('shows the backend\'s refusal of Activate in its own words', async () => {
    mockFetch({ session: strategySession(), onArm: () => refusal(409, 'BOT_PADLOCK_LOCKED', 'The padlock is locked -- unlock it before Activate') });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-activate')); await flush(); });
    expect(screen.getByTestId('bots-error').textContent).toBe('The padlock is locked — unlock it before Activate');
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Not active');
  });

  it('choosing Strategy is a PATCH of the level, never an Activate', async () => {
    const fetchMock = mockFetch({ onPatch: body => session({ level: Number(body.level) as 0 | 1 | 2 }) });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-level-2')); await flush(); await flush(); });
    expect(called(fetchMock, '/session/arm')).toBe(false);
    const patchCall = fetchMock.mock.calls.find(([, init]) => init && (init as RequestInit).method === 'PATCH');
    expect(String((patchCall?.[1] as RequestInit).body)).toBe('{"level":2}');
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Not active');
    expect(screen.getByTestId('bots-level-2').getAttribute('aria-checked')).toBe('true');
  });

  it('says why the backend turned the bot off', async () => {
    mockFetch({ session: strategySession({ deactivated: { at: AT_0942, reason: 'restart', text: 'Not active -- the backend restarted' } }) });
    await renderPage();
    expect(screen.getByTestId('bots-hero-deactivated').textContent).toBe('Turned off at 09:42 ET — the backend restarted');
  });

  it('an active bot that would not trade now says why, and never "live" on Paper', async () => {
    mockFetch({ session: strategySession({ active: true, armed: true, ready: false, ready_reason: 'every bot window is closed' }) });
    await renderPage();
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Active');
    expect(screen.getByTestId('bots-hero-not-ready').textContent).toBe('Not trading now — every bot window is closed');
    expect(screen.getByTestId('bots-hero').textContent).not.toMatch(/\blive\b/i);
    expect(screen.getByTestId('bots-hero').className).not.toContain('bots-hero--trading');
  });

  it('shows an active bot that trades: Active, Deactivate, no second switch', async () => {
    mockFetch({ session: strategySession({ active: true, armed: true, ready: true }) });
    await renderPage();
    expect(screen.getByTestId('bots-hero').className).toContain('bots-hero--trading');
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Active');
    expect(screen.queryByTestId('bots-in-control')).toBeNull();
    expect(screen.queryByTestId('bots-activate')).toBeNull();
    expect(screen.getByTestId('bots-stop')).toBeTruthy();
  });

  it('opens a missing Level 2 in a pinned Trader tab straight from the gate chip', async () => {
    mockFetch({ session: strategySession() });
    await renderPage();
    fireEvent.click(screen.getByTestId('bots-gate-action-open_l2-IMCC'));
    expect(openStockView).toHaveBeenCalledWith('IMCC', { pin: true });
  });

  it('offers the padlock PIN from a locked padlock gate', async () => {
    ibkrStatus.armed = false;
    mockFetch({ session: strategySession({ gates: openGates({ padlock: { ok: false, detail: { reason: 'Desk is disarmed -- arm trading in this session before placing' } } }) }) });
    await renderPage();
    const chip = screen.getByTestId('bots-gate-padlock');
    expect(chip.textContent).toMatch(/Padlock locked — unlock padlock/);
    await act(async () => { fireEvent.click(within(chip).getByText('unlock padlock')); await flush(); });
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('never stops the bot from the page when the padlock reads locked: the backend does', async () => {
    ibkrStatus.armed = false;
    const fetchMock = mockFetch({ session: strategySession({ active: true, armed: true }) });
    await renderPage();
    await act(async () => { await flush(); });
    expect(called(fetchMock, '/session/disarm')).toBe(false);
  });

  it('says the API is too old instead of claiming every gate is open', async () => {
    const stale = strategySession();
    delete stale.gates;
    mockFetch({ session: stale });
    await renderPage();
    expect(screen.getByTestId('bots-gates-unreported').textContent).toMatch(/older than the Bots page/);
    expect(screen.getByTestId('bots-hero-sentence').textContent).not.toMatch(/every gate is open/);
  });

  it('surfaces a failed level change and offers the API key field', async () => {
    mockFetch({
      session: session({ level: 0 }),
      onPatch: () => ({ ok: false, status: 401, json: async () => ({ detail: 'Invalid or missing X-Nova-Api-Key' }) }),
    });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-level-1')); await flush(); });
    expect(screen.getByTestId('bots-level-0').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('bots-error').textContent).toMatch(/Need Nova API key/i);
    expect(screen.getByTestId('bots-api-key')).toBeTruthy();
  });

  it('trips the kill switch, says what it swept on each venue, then offers the reset', async () => {
    const fetchMock = mockFetch({ killSweep: [
      { venue: 'paper', cancelled: [101, 102], failed: [], error: null },
      { venue: 'sim', cancelled: [], failed: [], error: null },
      { venue: 'live', cancelled: [], failed: [], error: 'Gateway disconnected: Live orders were not swept' },
    ] });
    await renderPage();
    const trip = screen.getByTestId('bots-kill-trip');
    expect(trip.textContent).toMatch(/Cancels every working order on every venue and refuses every new order on every venue, a sell included, until you reset it\. It does not sell positions; Flatten and cancels still work\./);
    await act(async () => { fireEvent.click(trip); await flush(); });
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(called(fetchMock, '/kill-switch', 'POST')).toBe(true);
    expect(screen.getByTestId('bots-kill-sweep-paper').textContent).toBe('Paper: cancelled 2 orders (#101, #102)');
    expect(screen.getByTestId('bots-kill-sweep-sim').textContent).toBe('Sim: nothing was working');
    expect(screen.getByTestId('bots-kill-sweep-live').textContent).toBe('Live: Gateway disconnected: Live orders were not swept');
    expect(screen.getByTestId('bots-kill-reset')).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-kill-reset')); await flush(); });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/kill-switch/reset'))).toBe(true);
    expect(screen.getByTestId('bots-kill-trip')).toBeTruthy();
  });

  it('shows the day lock on its venue until 04:00 ET, and the venue', async () => {
    mockFetch({ session: session({ day_lock: { active: true, until: '2026-10-01T04:00:00-04:00', tripped_at: AT_0942, pnl: -212.4, venue: 'paper' } }) });
    await renderPage();
    expect(screen.getByTestId('bots-day-lock-banner').textContent)
      .toBe('All-stop fired at 09:42 ET at −$212.40: bot and manual buys on Paper are locked until 04:00 ET on Oct 1. Flatten and cancel still work.');
    expect(screen.getByTestId('bots-venue').textContent).toMatch(/Paper.*Nova Paper — fake money on the live feed/);
  });

  it('credits the playbook to the operator\'s own course material, by no vendor name', async () => {
    mockFetch();
    await renderPage();
    const head = screen.getByTestId('bots-strategies').querySelector('h3');
    expect(head?.textContent).toBe('Strategies from your course material');
  });

  it('counts the gates a session reports, without the retired read-out gate', async () => {
    mockFetch({ session: session({ gates: gates() }) });
    await renderPage();
    expect(screen.queryByTestId('bots-gate-readout')).toBeNull();
    expect(screen.getAllByTestId(/^bots-gate-[a-z_]+$/)).toHaveLength(13);
  });
});
