/**
 * @vitest-environment jsdom
 */
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { StrategyTab } from './StrategyTab';
import type { BotSession } from './types';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';

beforeEach(() => {
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
});

afterEach(() => {
  cleanup();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  vi.unstubAllGlobals();
});

function session(partial: Partial<BotSession> = {}): BotSession {
  return {
    level: 1,
    armed: false,
    strategy: null,
    active_pack: 'halt-luld',
    symbol_allowlist: [],
    brain_session_id: null,
    brain_alive: false,
    live_fire_ready: false,
    caps: {
      max_shares: 1,
      bp_budget_usd: 50,
      working_ttl_sec: 3,
      extended_hours: false,
      allowlist: [],
    },
    advise: {
      enabled: false,
      usd_cap: 2,
      call_cap: 10,
      usd_spent: 0,
      calls_used: 0,
    },
    soft_breaker_fired: false,
    hard_lock_until_date: null,
    day_lock_active: false,
    focus: [],
    trader_live: ['AAPL'],
    working: [],
    ...partial,
  };
}

describe('StrategyTab', () => {
  it('loads settings only -- no autonomy radios', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const href = String(url);
      if (href.includes('/bot/session')) {
        return { ok: true, json: async () => session() };
      }
      return { ok: true, json: async () => (href.includes('proposals') ? { proposals: [] } : { entries: [] }) };
    }));

    await act(async () => {
      render(<StrategyTab />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText(/Strategy -- small-cap settings/)).toBeTruthy();
    expect(screen.getByText(/Live L2/)).toBeTruthy();
    expect(screen.queryByLabelText(/Strategy \(L2 small-cap\)/)).toBeNull();
    expect(screen.queryByRole('radio')).toBeNull();
    expect(screen.getByText(/header/)).toBeTruthy();
  });

  it('shows the -$200 day lock banner', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const href = String(url);
      if (href.includes('/bot/session')) {
        return {
          ok: true,
          json: async () => session({ day_lock_active: true, hard_lock_until_date: '2026-09-18' }),
        };
      }
      return { ok: true, json: async () => (href.includes('proposals') ? { proposals: [] } : { entries: [] }) };
    }));

    await act(async () => {
      render(<StrategyTab />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByRole('alert').textContent).toMatch(/-\$200 day lock/);
  });

  it('shows the active pack description and LLM Activate copy', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const href = String(url);
      if (href.includes('/bot/session')) {
        return {
          ok: true,
          json: async () => session({
            active_pack: 'llm-decide',
            packs: [{
              id: 'llm-decide',
              label: 'LLM decide',
              status: 'live',
              description: 'Live fire needs L2 + Activate.',
            }],
            llm: {
              configured: false,
              live_fire: false,
              call_cap: 10,
              usd_cap: 2,
              usd_spent: 0,
              calls_used: 0,
            },
          }),
        };
      }
      return { ok: true, json: async () => (href.includes('proposals') ? { proposals: [] } : { entries: [] }) };
    }));

    await act(async () => {
      render(<StrategyTab />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId('bot-pack-desc').textContent).toMatch(/L2 \+ Activate/);
    expect(screen.getByTestId('bot-llm-fire-status').textContent).toMatch(/live-fire when Activate/);
  });

  it('shows quote-spike signal settings', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const href = String(url);
      if (href.includes('/bot/session')) {
        return {
          ok: true,
          json: async () => session({
            active_pack: 'quote-spike',
            pack_settings: {
              'quote-spike': {
                spike_kind: 'buy_market',
                min_pct: 3,
                window_sec: 5,
                cooldown_sec: 30,
              },
            },
            packs: [{
              id: 'quote-spike',
              label: 'Quote spike',
              status: 'live',
              description: 'Last or mid rises 3% in 5s.',
            }],
          }),
        };
      }
      return { ok: true, json: async () => (href.includes('proposals') ? { proposals: [] } : { entries: [] }) };
    }));

    await act(async () => {
      render(<StrategyTab />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId('bot-pack-desc').textContent).toMatch(/3%/);
    expect(screen.getByTestId('bot-quote-spike-settings').textContent).toMatch(/3%/);
    expect(screen.getByTestId('bot-quote-spike-settings').textContent).not.toMatch(/stub/i);
  });

  it('shows volume signal settings', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const href = String(url);
      if (href.includes('/bot/session')) {
        return {
          ok: true,
          json: async () => session({
            active_pack: 'volume',
            pack_settings: {
              volume: {
                volume_kind: 'buy_market',
                min_mult: 5,
                window_sec: 60,
                baseline_sec: 600,
                cooldown_sec: 60,
              },
            },
            packs: [{
              id: 'volume',
              label: 'Volume boost',
              status: 'live',
              description: 'Last-60s day-volume rate is 5x the prior 10m baseline.',
            }],
          }),
        };
      }
      return { ok: true, json: async () => (href.includes('proposals') ? { proposals: [] } : { entries: [] }) };
    }));

    await act(async () => {
      render(<StrategyTab />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId('bot-pack-desc').textContent).toMatch(/5x|10m|day-volume/i);
    expect(screen.getByTestId('bot-volume-settings').textContent).toMatch(/5x/);
    expect(screen.getByTestId('bot-volume-settings').textContent).not.toMatch(/stub/i);
  });
});
