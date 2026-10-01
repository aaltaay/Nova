/**
 * @vitest-environment jsdom
 *
 * The Trader rail's bot card (ADR 042): the master level, how many setups are at
 * Strategy, the bot's stocks, and Active / Not active with the reason -- never a
 * chosen setup -- with the same Activate rules as the Bots page hero.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { botAllowlistStripLabel } from '../constantGroups/bot';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { BotAutonomyCard } from './BotAutonomyCard';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { botsFetchRouter, openGates, session, strategySession } from './botsPageFixtures';
import type { BotSession } from './types';

const confirmApp = vi.fn(async () => true);
vi.mock('../ux/appDialogApi', () => ({ confirmApp: (...args: unknown[]) => confirmApp(...(args as [])) }));

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
    for (let i = 0; i < 4; i += 1) await Promise.resolve();
  });
}

beforeEach(() => {
  posts.length = 0;
  confirmApp.mockClear();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
});

afterEach(() => {
  cleanup();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('BotAutonomyCard', () => {
  it('shows the master level, how many setups are at Strategy, the bot\'s stocks and why it is not active', async () => {
    mockFetch(strategySession({ deactivated: { at: null, reason: 'padlock', text: null } }));
    await mount();
    expect(screen.getByTestId('bot-card-state').textContent).toBe('Not active');
    expect((screen.getByTestId('bot-card-level') as HTMLSelectElement).value).toBe('2');
    expect(screen.getByTestId('bot-card-at-strategy').textContent).toBe('1 at Strategy');
    expect(screen.getByTestId('bot-card-at-strategy').getAttribute('data-tip')).toMatch(/At Strategy: First pullback/);
    expect(screen.getByTestId('bot-card-reason').textContent).toMatch(/Turned off — the padlock was locked/);
    expect(screen.getByTestId('bot-arm-allowlist-toggle').textContent).toBe(botAllowlistStripLabel(2));
    expect(screen.getByTestId('bot-autonomy-card').textContent).not.toMatch(/First pullback/);
  });

  it('Activate arms through the session arm endpoint; the button then reads Deactivate', async () => {
    mockFetch(strategySession());
    await mount();
    await act(async () => { fireEvent.click(screen.getByTestId('bot-card-activate')); });
    expect(posts.some(p => p.href.includes('/session/arm') && p.method === 'POST')).toBe(true);
    expect(posts.find(p => p.href.includes('/session/arm'))?.body).toBe('{}');
    expect(screen.getByTestId('bot-card-stop')).toBeTruthy();
    expect(screen.getByTestId('bot-card-state').textContent).toBe('Active');
  });

  it('locks Activate below Strategy and says why, and choosing a level never activates', async () => {
    mockFetch(session());
    await mount();
    const activate = screen.getByTestId('bot-card-activate') as HTMLButtonElement;
    expect(activate.disabled).toBe(true);
    expect(activate.getAttribute('data-why')).toMatch(/The master level is Eyes: choose Strategy/);
    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-card-level'), { target: { value: '2' } });
      for (let i = 0; i < 4; i += 1) await Promise.resolve();
    });
    expect(posts.some(p => p.method === 'PATCH' && p.body === '{"level":2}')).toBe(true);
    expect(posts.some(p => p.href.includes('/session/arm'))).toBe(false);
  });

  it('after a bot trip, asks first and sends reenable only on a yes', async () => {
    mockFetch(strategySession({ gates: openGates({ bot_trip: { ok: false, detail: { fired_at: null, pnl: -51, until: null } } }) }));
    await mount();
    confirmApp.mockImplementationOnce(async () => false);
    await act(async () => { fireEvent.click(screen.getByTestId('bot-card-activate')); });
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(posts.some(p => p.href.includes('/session/arm'))).toBe(false);
    await act(async () => { fireEvent.click(screen.getByTestId('bot-card-activate')); });
    expect(posts.find(p => p.href.includes('/session/arm'))?.body).toBe('{"reenable":true}');
  });
});
