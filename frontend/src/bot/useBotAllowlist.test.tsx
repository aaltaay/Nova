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
          json: async () => ({
            symbol_allowlist: body.op === 'remove' ? [] : ['ABCD'],
          }),
        };
      }
      return {
        ok: true,
        json: async () => ({ symbol_allowlist: [] }),
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
