/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import {
  _resetBotSessionPollerForTests,
  getBotSessionSnapshot,
} from './botSessionPoller';
import { useBotAllowlist } from './useBotAllowlist';

function Probe() {
  const { symbols, add, remove } = useBotAllowlist();
  return (
    <div>
      <div data-testid="syms">{symbols.join(',')}</div>
      <button type="button" onClick={() => void add('abcd')}>add</button>
      <button type="button" onClick={() => void remove('abcd')}>remove</button>
    </div>
  );
}

describe('useBotAllowlist', () => {
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

  it('reads the shared session snapshot and writes through POST /bot/allowlist', async () => {
    // A session the Bots page can render: caps and advise are part of every
    // answer, and a body without them is refused as unreadable (QA C12).
    const session = (allow: string[]) => ({
      level: 0, armed: false, strategy: null, brain_session_id: null,
      caps: { max_shares: 1, bp_budget_usd: 50, working_ttl_sec: 3, extended_hours: false, allowlist: [] },
      advise: { enabled: false, usd_cap: 2, call_cap: 10, usd_spent: 0, calls_used: 0 },
      soft_breaker_fired: false, hard_lock_until_date: null, day_lock_active: false,
      focus: [], trader_live: [], working: [], symbol_allowlist: allow,
    });
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const href = String(url);
      if (href.includes('/bot/proposals')) {
        return { ok: true, json: async () => ({ proposals: [] }) };
      }
      if (href.includes('/bot/audit')) {
        return { ok: true, json: async () => ({ entries: [] }) };
      }
      if (href.includes('/bot/allowlist') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body || '{}')) as { symbol: string; op: string };
        return {
          ok: true,
          json: async () => session(body.op === 'remove' ? [] : ['ABCD']),
        };
      }
      return {
        ok: true,
        json: async () => session([]),
      };
    }));

    await act(async () => {
      render(<Probe />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByTestId('syms').textContent).toBe('');

    await act(async () => {
      fireEvent.click(screen.getByText('add'));
      await Promise.resolve();
    });
    expect(screen.getByTestId('syms').textContent).toBe('ABCD');
    expect(getBotSessionSnapshot().session?.symbol_allowlist).toEqual(['ABCD']);

    const allowCalls = vi.mocked(fetch).mock.calls.filter((call) =>
      String(call[0]).includes('/bot/allowlist'),
    );
    expect(allowCalls).toHaveLength(1);
    expect(String((allowCalls[0][1] as RequestInit).body)).toContain('abcd');
  });
});
