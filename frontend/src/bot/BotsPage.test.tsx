/**
 * @vitest-environment jsdom
 *
 * The Bots page (approved mockup v4, ADR 027): the hero -- state, level,
 * every gate as a chip whose link opens it, Activate and the kill switch --
 * and the page shell. The cards have their own file (BotsPageCards.test.tsx).
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BotsPage } from './BotsPage';
import { botsFetchRouter, CLOSED_READOUT, gates, session, type BotsFetchOpts } from './botsPageFixtures';

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

describe('Bots page hero (approved mockup v4)', () => {
  it('draws every gate as a chip, closed ones with the link that opens them', async () => {
    mockFetch({ session: session({ level: 2, gates: gates({ level: { ok: true, detail: { level: 2 } } }) }), dayPnl: -9.54 });
    await renderPage();
    const readout = screen.getByTestId('bots-gate-readout');
    expect(readout.className).toContain('is-closed');
    expect(readout.textContent).toMatch(/Read-out 12 \/ 50 — first pullback not proven yet/);
    expect(screen.getByTestId('bots-gate-depth_lines').textContent).toMatch(/Depth lines 1 \/ 2 held — open IMCC Level 2/);
    expect(screen.getByTestId('bots-gate-depth_lines').className).toContain('is-fire');
    expect(screen.getByTestId('bots-gate-window').textContent).toMatch(/Window 07:00–10:00 · 0 \/ 1 trade today/);
    expect(screen.getByTestId('bots-gate-bot_trip').textContent).toMatch(/Bot trip clear \(−\$9\.54 \/ −\$50\)/);
    expect(screen.getByTestId('bots-gate-level').className).toContain('is-ok');
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Not active');
    expect(screen.getByTestId('bots-hero-sentence').textContent)
      .toBe('Strategy is chosen, but the bot can\'t fire yet: 2 of 9 gates are closed. Until then it proposes like Eyes.');
    expect(screen.getByTestId('bots-hero-playing').textContent).toBe('Playing First pullback · 2 symbols · max 1 share · $50 budget');
  });

  it('says what each level lets a connected bot do, and that Strategy does not place a proposal yet', async () => {
    mockFetch({ session: session({ level: 0 }) });
    await renderPage();
    expect(screen.getByTestId('bots-level-0').textContent).toMatch(/Bot API dark · the setup scanner still watches and proposes/);
    expect(screen.getByTestId('bots-level-1').textContent).toMatch(/connected bot may watch and propose · you place/);
    const strategy = screen.getByTestId('bots-level-2');
    expect(strategy.textContent).toMatch(/automatic placing from a proposal is not built yet/);
    expect(strategy.getAttribute('aria-label')).toMatch(/^L2 Strategy: .*not built yet/);
    expect(screen.getByTestId('bots-hero').textContent).not.toMatch(/no watching|on its own/);
  });

  it('opens a missing Level 2 in a pinned Trader tab straight from the gate chip', async () => {
    mockFetch({ session: session({ level: 2 }) });
    await renderPage();
    fireEvent.click(screen.getByTestId('bots-gate-action-open_l2-IMCC'));
    expect(openStockView).toHaveBeenCalledWith('IMCC', { pin: true });
  });

  it('offers the padlock PIN from a disarmed desk gate', async () => {
    ibkrStatus.armed = false;
    mockFetch({ session: session({ level: 1, gates: gates({
      desk_armed: { ok: false, detail: { reason: 'Desk is disarmed -- arm trading in this session before placing' } },
    }) }) });
    await renderPage();
    const chip = screen.getByTestId('bots-gate-desk_armed');
    expect(chip.textContent).toMatch(/Desk disarmed — unlock padlock/);
    await act(async () => { fireEvent.click(within(chip).getByText('unlock padlock')); await flush(); });
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('says the API is too old instead of claiming every gate is open', async () => {
    const stale = session({ level: 2 });
    delete stale.gates;
    delete stale.readout;
    mockFetch({ session: stale });
    await renderPage();
    expect(screen.getByTestId('bots-gates-unreported').textContent).toMatch(/older than the Bots page/);
    expect(screen.getByTestId('bots-hero-sentence').textContent).not.toMatch(/every gate is open/);
    expect(screen.getByTestId('bots-readout').textContent).toMatch(/not reported by this API/);
  });

  it('refuses Activate at Strategy until the read-out passes, and names what it waits on', async () => {
    const fetchMock = mockFetch({ session: session({ level: 2, gates: gates({ level: { ok: true, detail: { level: 2 } } }) }) });
    await renderPage();
    const activate = screen.getByTestId('bots-activate') as HTMLButtonElement;
    expect(activate.disabled).toBe(true);
    expect(activate.getAttribute('data-why')).toMatch(/12 of 50 go setups triggered/);
    expect(screen.getByTestId('bots-activate-hint').textContent).toBe('Activate waits on: read-out');
    await act(async () => { fireEvent.click(activate); await flush(); });
    expect(called(fetchMock, '/session/arm')).toBe(false);
  });

  it('choosing Strategy activates first and patches with the desk token', async () => {
    const fetchMock = mockFetch({ onPatch: body => session({ level: Number(body.level) as 0 | 1 | 2, armed: false }) });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-level-2')); await flush(); await flush(); });
    expect(called(fetchMock, '/session/arm')).toBe(true);
    const patchCall = fetchMock.mock.calls.find(([, init]) => init && (init as RequestInit).method === 'PATCH');
    const headers = new Headers((patchCall?.[1] as RequestInit).headers);
    expect(headers.get('X-Nova-Desk-Arm')).toBe('desk-token-1');
    expect(String((patchCall?.[1] as RequestInit).body)).toContain('"level":2');
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Not active');
    expect(screen.getByTestId('bots-level-2').getAttribute('aria-checked')).toBe('true');
  });

  it('says why Strategy cannot be chosen while the padlock is locked, instead of doing nothing', async () => {
    ibkrStatus.armed = false;
    const fetchMock = mockFetch();
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-level-2')); await flush(); });
    expect(called(fetchMock, '/session/arm')).toBe(false);
    expect(screen.getByTestId('bots-error').textContent).toMatch(/Unlock the padlock first/);
  });

  it('shows a live bot: Active, Deactivate, in control', async () => {
    mockFetch({ session: session({
      level: 2, armed: true, has_desk_arm: true, live_fire_ready: true, brain_alive: true,
      readout: { ...CLOSED_READOUT, state: 'passed', passed: true },
    }) });
    await renderPage();
    expect(screen.getByTestId('bots-hero').className).toContain('bots-hero--live');
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Active');
    expect((screen.getByTestId('bots-in-control') as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByTestId('bots-activate')).toBeNull();
    expect(screen.getByTestId('bots-stop')).toBeTruthy();
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

  it('disarms when armed while the padlock is locked', async () => {
    ibkrStatus.armed = false;
    const fetchMock = mockFetch({ session: session({ level: 2, armed: true, has_desk_arm: true }) });
    await renderPage();
    await act(async () => { await flush(); });
    expect(called(fetchMock, '/session/disarm')).toBe(true);
  });

  it('never stops the bot on a status this window has not read yet (a bot may have armed the desk)', async () => {
    ibkrStatus.armed = false;
    ibkrStatus.lastSuccessAt = null;
    const fetchMock = mockFetch({ session: session({ level: 2, armed: true, has_desk_arm: true }) });
    await renderPage();
    await act(async () => { await flush(); });
    expect(called(fetchMock, '/session/disarm')).toBe(false);
  });

  it('trips the kill switch from the hero, then offers the reset on the button and the chip', async () => {
    const fetchMock = mockFetch();
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-kill-trip')); await flush(); });
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(called(fetchMock, '/kill-switch', 'POST')).toBe(true);
    expect(screen.getByTestId('bots-kill-reset')).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-kill-reset')); await flush(); });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/kill-switch/reset'))).toBe(true);
    expect(screen.getByTestId('bots-kill-trip')).toBeTruthy();
  });

  it('shows the day lock banner and the venue', async () => {
    mockFetch({ session: session({ day_lock_active: true, hard_lock_until_date: '2026-09-18' }) });
    await renderPage();
    expect(screen.getByRole('alert').textContent).toMatch(/−\$200 day lock/);
    expect(screen.getByTestId('bots-venue').textContent).toMatch(/Paper.*Nova Paper — fake money on the live feed/);
  });

  it('credits the playbook to the operator\'s own course material, by no vendor name', async () => {
    mockFetch();
    await renderPage();
    const head = screen.getByTestId('bots-strategies').querySelector('h3');
    expect(head?.textContent).toBe('Strategies from your course material');
  });
});
