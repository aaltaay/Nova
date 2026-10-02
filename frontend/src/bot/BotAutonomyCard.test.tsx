/**
 * @vitest-environment jsdom
 *
 * The Trader rail's bot card (ADR 043): the one Bot switch for this venue, the same rules as the Bots
 * page -- off always goes, on is locked with the reason on Live, after the bot trip it asks first -- with
 * why it is off and a way to the Bots page. No master dial, no Activate, no bot list here.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { getNavPage, resetNavRailStoreForTests } from '../workspace/navRailStore';
import { BotAutonomyCard } from './BotAutonomyCard';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BOT_SWITCH_LIVE_WHY } from './botSwitch';
import { botsFetchRouter, strategySession } from './botsPageFixtures';
import type { BotSession } from './types';

const confirmApp = vi.fn(async () => true);
vi.mock('../ux/appDialogApi', () => ({ confirmApp: (...args: unknown[]) => confirmApp(...(args as [])) }));
const workspace = vi.hoisted(() => ({ traderViewActive: true, showScannerView: vi.fn() }));
vi.mock('../workspace/WorkspaceContext', () => ({ useWorkspace: () => workspace }));

const posts: { href: string; method: string; body: string }[] = [];

function mockFetch(current: BotSession) {
  const route = botsFetchRouter({ session: current });
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (init?.method && init.method !== 'GET') posts.push({ href, method: init.method, body: String(init.body ?? '') });
    return route(href, init);
  }));
}

async function mount() {
  await act(async () => {
    render(<BotAutonomyCard />);
    for (let i = 0; i < 6; i += 1) await Promise.resolve();
  });
}

async function click(testId: string) {
  await act(async () => {
    fireEvent.click(screen.getByTestId(testId));
    for (let i = 0; i < 6; i += 1) await Promise.resolve();
  });
}

const switches = () => posts.filter(p => p.href.includes('/session/switch')).map(p => p.body);

beforeEach(() => {
  posts.length = 0;
  confirmApp.mockClear();
  resetNavRailStoreForTests();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
});

afterEach(() => {
  cleanup();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  vi.unstubAllGlobals();
  localStorage.clear();
  workspace.showScannerView.mockReset();
});

describe('BotAutonomyCard', () => {
  it('reads OFF with why, and no master dial, Activate or bot list', async () => {
    mockFetch(strategySession({ deactivated: { at: null, reason: 'padlock', text: null } }));
    await mount();
    expect(screen.getByTestId('bot-card-state').textContent).toBe('OFF');
    expect(screen.getByTestId('bot-card-reason').textContent).toBe('Turned off — the padlock was locked.');
    expect(screen.getByTestId('bot-card-switch').getAttribute('aria-checked')).toBe('false');
    expect(screen.queryByTestId('bot-card-level')).toBeNull();
    expect(screen.queryByTestId('bot-card-activate')).toBeNull();
    expect(screen.queryByTestId('bot-arm-allowlist-toggle')).toBeNull();
  });

  it('turns the Bot on and off with the one switch', async () => {
    mockFetch(strategySession());
    await mount();
    await click('bot-card-switch');
    expect(switches()).toEqual(['{"on":true}']);
    expect(screen.getByTestId('bot-card-state').textContent).toBe('ON · 1 strategy On');
    await click('bot-card-switch');
    expect(switches()).toEqual(['{"on":true}', '{"on":false}']);
    expect(posts.some(p => p.href.includes('/session/arm'))).toBe(false);
  });

  it('is locked on Live with the reason', async () => {
    mockFetch(strategySession({ level_venue: 'live' }));
    await mount();
    const sw = screen.getByTestId('bot-card-switch') as HTMLButtonElement;
    expect(sw.disabled).toBe(true);
    expect(sw.getAttribute('data-why')).toBe(BOT_SWITCH_LIVE_WHY);
  });

  it('after the bot trip, asks first and sends reenable only on a yes', async () => {
    mockFetch(strategySession({ soft_breaker: { fired: true, at: null, pnl: -51, until: null } }));
    await mount();
    confirmApp.mockImplementationOnce(async () => false);
    await click('bot-card-switch');
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(switches()).toEqual([]);
    await click('bot-card-switch');
    expect(switches()).toEqual(['{"on":true,"reenable":true}']);
  });

  it('opens the Bots page from the Trader', async () => {
    mockFetch(strategySession());
    await mount();
    await click('bot-card-open');
    expect(workspace.showScannerView).toHaveBeenCalledTimes(1);
    expect(getNavPage()).toBe('bots');
  });
});
