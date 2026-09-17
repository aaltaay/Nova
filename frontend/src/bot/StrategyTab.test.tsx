/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { StrategyTab } from './StrategyTab';
import type { BotSession } from './types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function session(partial: Partial<BotSession> = {}): BotSession {
  return {
    level: 1,
    armed: false,
    strategy: null,
    brain_session_id: null,
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
  it('loads session settings and patches autonomy', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const href = String(url);
      if (href.includes('/bot/session') && (!init || init.method === undefined || init.method === 'GET')) {
        return { ok: true, json: async () => session() };
      }
      if (href.includes('/bot/session') && init?.method === 'PATCH') {
        return { ok: true, json: async () => session({ level: 2, armed: true, strategy: 'small-cap' }) };
      }
      if (href.includes('/bot/proposals')) {
        return { ok: true, json: async () => ({ proposals: [] }) };
      }
      if (href.includes('/bot/audit')) {
        return { ok: true, json: async () => ({ entries: [] }) };
      }
      return { ok: false, json: async () => ({}) };
    });
    vi.stubGlobal('fetch', fetchMock);

    await act(async () => {
      render(<StrategyTab />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText(/Strategy -- small-cap/)).toBeTruthy();
    expect(screen.getByText(/Live L2/)).toBeTruthy();
    expect(screen.getByText(/parked \(#216\)/)).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByLabelText(/Strategy \(L2 small-cap\)/));
      await Promise.resolve();
    });

    const patchCall = fetchMock.mock.calls.find(([, init]) => init && (init as RequestInit).method === 'PATCH');
    expect(patchCall).toBeTruthy();
    expect(String(patchCall?.[1] && (patchCall[1] as RequestInit).body)).toContain('"level":2');
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
});
