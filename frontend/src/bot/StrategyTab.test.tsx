/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BOT_HARD_BREAKER_USD,
  BOT_SOFT_BREAKER_USD,
} from '../constantGroups/bot';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { StrategyTab } from './StrategyTab';
import type { BotSession } from './types';

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

function mockBotFetch(opts: {
  session?: BotSession;
  onPatch?: (body: Record<string, unknown>) => BotSession;
  onAllowlist?: (body: { symbol: string; op: string }) => BotSession;
} = {}) {
  let current = opts.session ?? session();
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/bot/proposals')) {
      return { ok: true, json: async () => ({ proposals: [] }) };
    }
    if (href.includes('/bot/audit')) {
      return { ok: true, json: async () => ({ entries: [] }) };
    }
    if (href.includes('/bot/allowlist') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body || '{}')) as { symbol: string; op: string };
      current = opts.onAllowlist?.(body) ?? {
        ...current,
        symbol_allowlist: body.op === 'remove' ? [] : [String(body.symbol).toUpperCase()],
      };
      return { ok: true, json: async () => current };
    }
    if (href.includes('/bot/session') && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body || '{}')) as Record<string, unknown>;
      current = opts.onPatch?.(body) ?? current;
      return { ok: true, json: async () => current };
    }
    if (href.includes('/bot/session')) {
      return { ok: true, json: async () => current };
    }
    return { ok: true, json: async () => ({}) };
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function renderTab() {
  await act(async () => {
    render(<StrategyTab />);
    await Promise.resolve();
    await Promise.resolve();
  });
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

  it('keeps pack picker and Activate in the header -- not this tab', async () => {
    mockBotFetch();
    await renderTab();

    expect(screen.queryByTestId('bot-arm-controls')).toBeNull();
    expect(screen.queryByLabelText('Bot pack')).toBeNull();
    expect(screen.queryByLabelText('Bot autonomy')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Activate' })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: /Bot is in control/i })).toBeNull();
  });

  it('PATCHes small-cap caps and Advise through /bot/session', async () => {
    const patches: Record<string, unknown>[] = [];
    mockBotFetch({
      onPatch: (body) => {
        patches.push(body);
        return session({
          caps: {
            max_shares: 4,
            bp_budget_usd: 25,
            working_ttl_sec: 7,
            extended_hours: true,
            allowlist: [],
          },
          advise: {
            enabled: true,
            usd_cap: 2,
            call_cap: 10,
            usd_spent: 0,
            calls_used: 0,
          },
        });
      },
    });
    await renderTab();

    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-strategy-max-shares'), { target: { value: '4' } });
      fireEvent.change(screen.getByTestId('bot-strategy-bp-budget'), { target: { value: '25' } });
      fireEvent.change(screen.getByTestId('bot-strategy-ttl'), { target: { value: '7' } });
      fireEvent.click(screen.getByTestId('bot-strategy-eh'));
      fireEvent.click(screen.getByTestId('bot-strategy-advise-enabled'));
      await Promise.resolve();
    });

    expect(patches).toEqual(expect.arrayContaining([
      { caps: { max_shares: 4 } },
      { caps: { bp_budget_usd: 25 } },
      { caps: { working_ttl_sec: 7 } },
      { caps: { extended_hours: true } },
      { advise: { enabled: true } },
    ]));
  });

  it('manages the symbol allowlist through the existing POST /bot/allowlist', async () => {
    const ops: Array<{ symbol: string; op: string }> = [];
    mockBotFetch({
      session: session({ symbol_allowlist: ['ABCD'] }),
      onAllowlist: (body) => {
        ops.push(body);
        return session({
          symbol_allowlist: body.op === 'remove' ? [] : ['ABCD', String(body.symbol).toUpperCase()],
        });
      },
    });
    await renderTab();

    expect(screen.getByTestId('bot-strategy-allowlist').textContent).toMatch(/ABCD/);
    expect(screen.getByTestId('bot-strategy-allowlist').textContent).toMatch(/right-click/i);

    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-strategy-allowlist-input'), { target: { value: 'efgh' } });
      fireEvent.click(screen.getByTestId('bot-strategy-allowlist-add'));
      await Promise.resolve();
    });
    expect(ops).toContainEqual({ symbol: 'efgh', op: 'add' });

    await act(async () => {
      fireEvent.click(screen.getByTestId('bot-strategy-allowlist-remove-ABCD'));
      await Promise.resolve();
    });
    expect(ops).toContainEqual({ symbol: 'ABCD', op: 'remove' });
  });

  it('shows locked breaker thresholds as display-only', async () => {
    mockBotFetch();
    await renderTab();

    const soft = screen.getByTestId('bot-strategy-breaker-soft') as HTMLInputElement;
    const hard = screen.getByTestId('bot-strategy-breaker-hard') as HTMLInputElement;
    expect(Number(soft.value)).toBe(BOT_SOFT_BREAKER_USD);
    expect(Number(hard.value)).toBe(BOT_HARD_BREAKER_USD);
    expect(soft.disabled).toBe(true);
    expect(hard.disabled).toBe(true);
    expect(screen.getByTestId('bot-strategy-breakers').textContent).toMatch(/locked/i);
  });
});
