/**
 * @vitest-environment jsdom
 *
 * The bot in the global bar (approved mockup v4): state at a glance on every
 * view, one click to the Bots page.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { getNavPage, resetNavRailStoreForTests } from '../workspace/navRailStore';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { botsFetchRouter, session, type BotsFetchOpts } from './botsPageFixtures';
import { GlobalBarBotPill } from './GlobalBarBotPill';
import { NavRailBotDot } from './NavRailBotDot';

const ibkrStatus = { connected: true, spend_status: 'paper_armed', trading_allowed: true, trading_allowed_reason: null, armed: true };
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
const workspace = vi.hoisted(() => ({ traderViewActive: false, showScannerView: vi.fn() }));
vi.mock('../workspace/WorkspaceContext', () => ({ useWorkspace: () => workspace }));

beforeEach(() => {
  resetNavRailStoreForTests();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
});

afterEach(() => {
  cleanup();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  vi.unstubAllGlobals();
  workspace.traderViewActive = false;
  workspace.showScannerView.mockReset();
});

async function mount(opts: BotsFetchOpts, node = <GlobalBarBotPill />) {
  vi.stubGlobal('fetch', vi.fn(botsFetchRouter(opts)));
  await act(async () => {
    render(node);
    for (let i = 0; i < 6; i += 1) await Promise.resolve();
  });
}

describe('GlobalBarBotPill', () => {
  it('reads "Bot L2 First pullback · Not active" and opens the Bots page', async () => {
    await mount({ session: session({ level: 2 }) });
    const pill = screen.getByTestId('global-bar-bot-pill');
    expect(pill.textContent).toBe('BotL2First pullback· Not active');
    expect(pill.className).toContain('global-bar-bot-pill--idle');
    expect(pill.title).toMatch(/3 of 9 gates closed/);
    fireEvent.click(pill);
    expect(getNavPage()).toBe('bots');
    expect(workspace.showScannerView).not.toHaveBeenCalled();
  });

  it('turns green when the bot is in control, and leaves the Trader to open the page', async () => {
    workspace.traderViewActive = true;
    await mount({ session: session({ level: 2, armed: true, has_desk_arm: true }) });
    const pill = screen.getByTestId('global-bar-bot-pill');
    expect(pill.className).toContain('global-bar-bot-pill--on');
    expect(pill.textContent).toMatch(/Active$/);
    fireEvent.click(pill);
    expect(workspace.showScannerView).toHaveBeenCalledTimes(1);
    expect(getNavPage()).toBe('bots');
  });

  it('shows nothing without a bot session', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({ detail: 'down' }) })));
    await act(async () => {
      render(<GlobalBarBotPill />);
      for (let i = 0; i < 6; i += 1) await Promise.resolve();
    });
    expect(screen.queryByTestId('global-bar-bot-pill')).toBeNull();
  });
});

describe('NavRailBotDot', () => {
  it('is amber while a level is chosen but not active, and absent at Off', async () => {
    await mount({ session: session({ level: 1 }) }, <NavRailBotDot />);
    expect(screen.getByTestId('nav-rail-bots-dot').className).toContain('nav-rail__badge--idle');
    cleanup();
    _resetBotSessionPollerForTests();
    await mount({ session: session({ level: 0 }) }, <NavRailBotDot />);
    expect(screen.queryByTestId('nav-rail-bots-dot')).toBeNull();
  });
});
