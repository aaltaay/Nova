/**
 * @vitest-environment jsdom
 *
 * The Bot switch in the header, beside the padlock (operator decision 2026-10-15): the master key over every bot,
 * ON or OFF at a glance on every view, turned on or off in one press, asking nothing (off sells nothing), with a
 * refusal said under it. And the nav rail's Bots dot.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { getNavPage, resetNavRailStoreForTests } from '../workspace/navRailStore';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BOT_PADLOCK_KEPT_OFF, BOT_PADLOCK_PROMPT_TITLE } from '../constantGroups/bot';
import { botsFetchRouter, openGates, refusal, session, strategySession, type BotsFetchOpts } from './botsPageFixtures';
import { GlobalBarBotKey } from './GlobalBarBotKey';
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
const confirmApp = vi.fn(async () => true);
vi.mock('../ux/appDialogApi', () => ({ confirmApp: (...args: unknown[]) => confirmApp(...(args as [])) }));

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
  confirmApp.mockClear();
});

async function flush() {
  for (let i = 0; i < 6; i += 1) await Promise.resolve();
}

async function mount(opts: BotsFetchOpts, node = <GlobalBarBotKey />) {
  const fetchMock = vi.fn(botsFetchRouter(opts));
  vi.stubGlobal('fetch', fetchMock);
  await act(async () => {
    render(node);
    await flush();
  });
  return fetchMock;
}

async function press(testId: string) {
  await act(async () => { fireEvent.click(screen.getByTestId(testId)); await flush(); });
  await act(async () => { await flush(); });
}

const switchBodies = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.filter(([url]) => String(url).includes('/session/switch'))
    .map(([, init]) => String((init as RequestInit | undefined)?.body ?? ''));

describe('GlobalBarBotKey', () => {
  it('reads "Bot OFF", says why on hover, and turns on in one press without leaving the view', async () => {
    const fetchMock = await mount({ session: strategySession({ deactivated: { at: null, reason: 'restart', text: 'Not active -- the backend restarted' } }) });
    const key = screen.getByTestId('global-bar-bot-key');
    expect(key.getAttribute('role')).toBe('switch');
    expect(key.getAttribute('aria-checked')).toBe('false');
    expect(key.textContent).toBe('BotOFF');
    expect(key.className).toContain('global-bar-bot-key--off');
    expect(key.title).toMatch(/^Bot off on Paper: Turned off — the backend restarted\. Strategies at On: First pullback ▲ long\./);
    expect(key.title).toMatch(/Off, no bot places an order, not even a sell/);
    await press('global-bar-bot-key');
    expect(switchBodies(fetchMock)).toEqual(['{"on":true}']);
    expect(screen.getByTestId('global-bar-bot-key').getAttribute('aria-checked')).toBe('true');
    expect(getNavPage()).toBe('dashboard');                       // a key, not a link: the view stays
  });

  it('turns off in one press and asks nothing: off sells nothing (2026-10-15)', async () => {
    const fetchMock = await mount({ session: strategySession({ bot_on: true, active: true, armed: true, ready: true, has_desk_arm: true }) });
    const key = screen.getByTestId('global-bar-bot-key');
    expect(key.className).toContain('global-bar-bot-key--on');
    expect(key.textContent).toBe('BotON');
    await press('global-bar-bot-key');
    expect(switchBodies(fetchMock)).toEqual(['{"on":false}']);
    expect(confirmApp).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/live-traders'))).toBe(false);
  });

  it('says when the Bot is on but would not trade now', async () => {
    await mount({ session: strategySession({ bot_on: true, active: true, armed: true, ready: false, ready_reason: 'every bot window is closed' }) });
    const key = screen.getByTestId('global-bar-bot-key');
    expect(key.className).toContain('global-bar-bot-key--idle');
    expect(key.title).toMatch(/Not trading now — every bot window is closed/);
  });

  it('says a refusal under the key, in the backend\'s words', async () => {
    await mount({ session: strategySession(), onSwitch: () => refusal(409, 'BOT_NO_SETUP_AT_STRATEGY', 'no strategy is On -- turn one On first') });
    await press('global-bar-bot-key');
    expect(screen.getByTestId('global-bar-bot-key-refused').textContent).toBe('no strategy is On — turn one On first');
    expect(screen.getByTestId('global-bar-bot-key').getAttribute('aria-checked')).toBe('false');
    expect(confirmApp).not.toHaveBeenCalled();
  });

  // Operator decision 2026-10-20: no bot turns on over a locked padlock -- it asks to unlock it first.
  const lockedOnce = (): BotsFetchOpts['onSwitch'] => {
    let calls = 0;
    return (body) => {
      calls += 1;
      return (calls === 1 && body.on === true
        ? refusal(409, 'BOT_PADLOCK_LOCKED', 'the desk padlock is locked') : undefined) as ReturnType<NonNullable<BotsFetchOpts['onSwitch']>>;
    };
  };
  const armBodies = (fetchMock: ReturnType<typeof vi.fn>) =>
    fetchMock.mock.calls.filter(([url]) => String(url).includes('/ibkr/arm'))
      .map(([, init]) => String((init as RequestInit | undefined)?.body ?? ''));

  it('over a locked padlock asks to unlock it; Keep it off leaves the bot off and the padlock locked', async () => {
    confirmApp.mockImplementationOnce(async () => false);
    const fetchMock = await mount({ session: strategySession(), onSwitch: lockedOnce() });
    await press('global-bar-bot-key');
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect((confirmApp.mock.calls[0] as unknown[])[0]).toMatchObject({ title: BOT_PADLOCK_PROMPT_TITLE });
    expect(armBodies(fetchMock)).toEqual([]);
    expect(switchBodies(fetchMock)).toEqual(['{"on":true}']);
    expect(screen.getByTestId('global-bar-bot-key-refused').textContent).toBe(BOT_PADLOCK_KEPT_OFF);
    expect(screen.getByTestId('global-bar-bot-key').getAttribute('aria-checked')).toBe('false');
  });

  it('over a locked padlock, yes unlocks it and turns the bot on', async () => {
    const fetchMock = await mount({ session: strategySession(), onSwitch: lockedOnce() });
    await press('global-bar-bot-key');
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(armBodies(fetchMock)).toEqual(['{"armed":true,"actor":"operator"}']);
    expect(switchBodies(fetchMock)).toEqual(['{"on":true}', '{"on":true}']);
    expect(screen.getByTestId('global-bar-bot-key').getAttribute('aria-checked')).toBe('true');
  });

  it('reads LOCKED, never ON, while it is on but the padlock is locked', async () => {
    await mount({ session: strategySession({ bot_on: true, active: true, armed: true, ready: false,
      gates: openGates({ padlock: { ok: false, detail: { reason: 'Desk is disarmed' } } }) }) });
    const key = screen.getByTestId('global-bar-bot-key');
    expect(key.textContent).toBe('BotLOCKED');
    expect(key.className).toContain('global-bar-bot-key--locked');
    expect(key.title).toMatch(/The padlock is locked: no bot places an order/);
  });

  it('shows nothing without a bot session', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({ detail: 'down' }) })));
    await act(async () => {
      render(<GlobalBarBotKey />);
      await flush();
    });
    expect(screen.queryByTestId('global-bar-bot-key')).toBeNull();
  });
});

describe('NavRailBotDot', () => {
  it('is amber while the Bot is on but not trading now, and absent while it is off', async () => {
    await mount({ session: strategySession({ bot_on: true, active: true, ready: false }) }, <NavRailBotDot />);
    expect(screen.getByTestId('nav-rail-bots-dot').className).toContain('nav-rail__badge--idle');
    cleanup();
    _resetBotSessionPollerForTests();
    await mount({ session: session({ level: 1 }) }, <NavRailBotDot />);
    expect(screen.queryByTestId('nav-rail-bots-dot')).toBeNull();
  });
});
