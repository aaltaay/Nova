/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PAPER_ACCOUNT } from './practiceFixtures';
import { resetPracticeAccount, usePracticeAccount } from './practiceAccountResource';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));

function Probe({ venue }: { venue: string | null }) {
  const { data, error } = usePracticeAccount(venue);
  return <output data-testid="probe">{error ?? (data ? `${data.venue}:${data.cash}` : 'idle')}</output>;
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.fetch.mockReset();
  mocks.fetch.mockImplementation(async (url: string) => ({
    ok: true, status: 200,
    json: async () => (url.includes('venue=sim')
      ? { ...PAPER_ACCOUNT, venue: 'sim', account_id: 'NOVA-SIM', cash: 1 }
      : PAPER_ACCOUNT),
  }));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('usePracticeAccount', () => {
  it('stays idle with no request off the practice venues', async () => {
    await act(async () => { render(<Probe venue="live" />); });
    expect(screen.getByTestId('probe').textContent).toBe('idle');
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it('polls the venue endpoint and stops when the last subscriber leaves', async () => {
    const view = await act(async () => render(<Probe venue="paper" />));
    expect(screen.getByTestId('probe').textContent).toBe('paper:98750.5');
    await act(async () => { await vi.advanceTimersByTimeAsync(2_100); });
    expect(mocks.fetch).toHaveBeenCalledTimes(2);
    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(mocks.fetch).toHaveBeenCalledTimes(2);
  });

  it('switches resources when the venue changes', async () => {
    const view = await act(async () => render(<Probe venue="paper" />));
    expect(screen.getByTestId('probe').textContent).toBe('paper:98750.5');
    await act(async () => { view.rerender(<Probe venue="sim" />); });
    expect(screen.getByTestId('probe').textContent).toBe('sim:1');
  });
});

describe('resetPracticeAccount', () => {
  it('POSTs and publishes the answer to the venue resource at once', async () => {
    await act(async () => { render(<Probe venue="paper" />); });
    mocks.fetch.mockImplementation(async () => ({
      ok: true, status: 200, json: async () => ({ ...PAPER_ACCOUNT, cash: 77 }),
    }));
    await act(async () => { await resetPracticeAccount('paper', null); });
    const [url, init] = mocks.fetch.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toContain('/api/practice/reset');
    expect(JSON.parse(String(init.body))).toEqual({ venue: 'paper' });
    expect(screen.getByTestId('probe').textContent).toBe('paper:77');
  });
});
