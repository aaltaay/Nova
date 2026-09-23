/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BOT_SETUP_BLURBS, botAllowlistStripLabel } from '../constantGroups/bot';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { BotAutonomyCard } from './BotAutonomyCard';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import type { BotSession } from './types';

const ibkrStatus = {
  connected: true,
  spend_status: 'paper_armed',
  spend_locked_reason: null as string | null,
  trading_allowed: true as boolean,
  trading_allowed_reason: null as string | null,
  armed: true as boolean,
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

function session(partial: Partial<BotSession> = {}): BotSession {
  return {
    level: 0, armed: false, has_desk_arm: false, strategy: null, setup: 'first_pullback',
    setups: [{ id: 'first_pullback', scanner: true }, { id: 'gap_and_go', scanner: false }],
    readout: {
      state: 'collecting', passed: false, reason: '12 of 50 go setups triggered',
      go: { triggered: 12, scored: 12, win_pct: 58, avg_net_r: 0.31 },
      control: { triggered: 40, scored: 40, win_pct: 30, avg_net_r: -0.18 },
      rules: { min_go: 50 },
    },
    symbol_allowlist: ['GRML', 'VXTL'], brain_session_id: null, brain_alive: false, live_fire_ready: false,
    caps: { max_shares: 1, bp_budget_usd: 50, working_ttl_sec: 3, extended_hours: false, allowlist: [] },
    advise: { enabled: false, usd_cap: 2, call_cap: 10, usd_spent: 0, calls_used: 0 },
    soft_breaker_fired: false, hard_lock_until_date: null, day_lock_active: false, focus: [], trader_live: [],
    working: [], ...partial,
  };
}

const posts: { href: string; method: string }[] = [];

function mockFetch(current: () => BotSession) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (init?.method && init.method !== 'GET') posts.push({ href, method: init.method });
    if (href.includes('/bot/proposals')) return { ok: true, status: 200, json: async () => ({ proposals: [] }) };
    if (href.includes('/bot/audit')) return { ok: true, status: 200, json: async () => ({ entries: [] }) };
    if (href.includes('/session/arm')) return { ok: true, status: 200, json: async () => session({ armed: true, has_desk_arm: true, desk_arm_token: 't' }) };
    return { ok: true, status: 200, json: async () => current() };
  }));
}

beforeEach(() => {
  ibkrStatus.armed = true;
  ibkrStatus.trading_allowed = true;
  ibkrStatus.trading_allowed_reason = null;
  posts.length = 0;
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
  it('shows Level, the Setup (what it trades as the i tooltip), Allowlist count and Not active · Activate', async () => {
    mockFetch(() => session());
    await act(async () => { render(<BotAutonomyCard />); });
    expect(screen.getByTestId('bot-card-state').textContent).toBe('Not active');
    expect(screen.getByTestId('bot-card-activate')).toBeTruthy();
    expect((screen.getByTestId('bot-card-level') as HTMLSelectElement).value).toBe('0');
    expect(screen.getByTestId('bot-card-setup').textContent).toBe('First pullback');
    expect(screen.getByTestId('bot-card-setup-info').title).toBe(BOT_SETUP_BLURBS.first_pullback);
    // The long sentence is a tooltip, not card text.
    expect(screen.queryByText(BOT_SETUP_BLURBS.first_pullback)).toBeNull();
    expect(screen.getByTestId('bot-arm-allowlist-toggle').textContent).toBe(botAllowlistStripLabel(2));
  });

  it('Activate arms through the session arm endpoint; the button then reads Deactivate', async () => {
    mockFetch(() => session());
    await act(async () => { render(<BotAutonomyCard />); });
    await act(async () => { fireEvent.click(screen.getByTestId('bot-card-activate')); });
    expect(posts.some(p => p.href.includes('/session/arm') && p.method === 'POST')).toBe(true);
    // The arm response is the armed session, so the card flips without a poll.
    expect(screen.getByTestId('bot-card-stop')).toBeTruthy();
    expect(screen.getByTestId('bot-card-state').textContent).toBe('Active');
  });

  it('refuses Activate while the desk gate blocks places, and says why', async () => {
    ibkrStatus.trading_allowed = false;
    ibkrStatus.trading_allowed_reason = 'Spend locked';
    mockFetch(() => session());
    await act(async () => { render(<BotAutonomyCard />); });
    const activate = screen.getByTestId('bot-card-activate') as HTMLButtonElement;
    expect(activate.disabled).toBe(true);
    expect(activate.title).toBe('Spend locked');
  });

  it('refuses Activate at Strategy until the first-pullback read-out passes, and says why', async () => {
    mockFetch(() => session({ level: 2 }));
    await act(async () => { render(<BotAutonomyCard />); });
    const activate = screen.getByTestId('bot-card-activate') as HTMLButtonElement;
    expect(activate.disabled).toBe(true);
    expect(activate.title).toContain('12 of 50 go setups triggered');
    await act(async () => { fireEvent.click(activate); });
    expect(posts.some(p => p.href.includes('/session/arm'))).toBe(false);
  });
});
