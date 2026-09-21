/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PracticeAccountStrip } from './PracticeAccountStrip';
import { PAPER_ACCOUNT as PAPER } from './practiceFixtures';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));

function answer(body: unknown, ok = true, status = 200) {
  mocks.fetch.mockImplementation(async () => ({ ok, status, json: async () => body }));
}

async function mount(venue: string | null) {
  await act(async () => { render(<PracticeAccountStrip venue={venue} />); });
}

beforeEach(() => {
  mocks.fetch.mockReset();
  answer(PAPER);
});

afterEach(() => {
  cleanup();
});

describe('PracticeAccountStrip', () => {
  it('renders nothing and asks nothing off the practice venues', async () => {
    for (const venue of ['live', 'disconnected', null]) {
      await mount(venue);
      expect(screen.queryByTestId('practice-strip')).toBeNull();
      cleanup();
    }
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it('polls the Paper account and shows id, cash, BP, day P&L and fees with tooltips', async () => {
    await mount('paper');
    expect(mocks.fetch).toHaveBeenCalledTimes(1);
    expect(String(mocks.fetch.mock.calls[0][0])).toContain('/api/practice/account?venue=paper');
    const strip = screen.getByTestId('practice-strip');
    expect(strip.dataset.state).toBe('ready');
    expect(strip.dataset.venue).toBe('paper');
    expect(screen.getByTestId('practice-strip-account').textContent).toBe('NOVA-PAPER');
    expect(screen.getByTestId('practice-strip-account').title).toMatch(/fake money/i);
    expect(screen.getByTestId('practice-strip-cash').textContent).toContain('$98,750.50');
    expect(screen.getByTestId('practice-strip-cash').title).toMatch(/Net liquidation/);
    expect(screen.getByTestId('practice-strip-bp').textContent).toContain('$395,002.00');
    expect(screen.getByTestId('practice-strip-day-pnl').textContent).toContain('+$250.25');
    expect(screen.getByTestId('practice-strip-day-pnl').title).toMatch(/realized/);
    expect(screen.getByTestId('practice-strip-fees').textContent).toContain('$3.50');
    expect(screen.getByTestId('practice-strip-fees').title).toMatch(/commissions/i);
    expect(screen.queryByTestId('practice-strip-replay')).toBeNull();
  });

  it('shows the replay key on Sim', async () => {
    answer({ ...PAPER, venue: 'sim', account_id: 'NOVA-SIM', replay_key: 'capture:AAPL:2026-09-19' });
    await mount('sim');
    expect(String(mocks.fetch.mock.calls[0][0])).toContain('venue=sim');
    expect(screen.getByTestId('practice-strip-account').textContent).toBe('NOVA-SIM');
    const replay = screen.getByTestId('practice-strip-replay');
    expect(replay.textContent).toContain('capture:AAPL:2026-09-19');
    expect(replay.title).toMatch(/replay/i);
  });

  it('says the account is unavailable when the backend refuses, never a stale number', async () => {
    answer({ detail: 'practice ledger locked' }, false, 503);
    await mount('paper');
    const strip = screen.getByTestId('practice-strip');
    expect(strip.dataset.state).toBe('unavailable');
    expect(strip.title).toContain('practice ledger locked');
    expect(strip.textContent).toMatch(/unavailable/i);
    expect(screen.queryByTestId('practice-strip-cash')).toBeNull();
  });
});
