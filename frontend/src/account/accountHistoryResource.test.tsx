/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AccountRange } from '../constantGroups/account_page';
import { paperHistoryFixture } from './accountFixtures';
import {
  invalidateAccountHistory,
  resetAccountHistoryResourcesForTests,
  useAccountHistory,
} from './accountHistoryResource';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));

function Probe({ venue, range }: { venue: string | null; range: AccountRange }) {
  const { data, error } = useAccountHistory(venue, range);
  return <div data-testid="probe">{error ?? (data ? `${data.venue}:${data.range}:${data.fills.length}` : 'idle')}</div>;
}

beforeEach(() => {
  resetAccountHistoryResourcesForTests();
  mocks.fetch.mockReset();
  mocks.fetch.mockImplementation(async (url: string) => {
    const range = /range=([A-Z0-9]+)/.exec(url)?.[1] ?? '1D';
    return { ok: true, status: 200, json: async () => ({ ...paperHistoryFixture(), range }) };
  });
});

afterEach(cleanup);

describe('useAccountHistory', () => {
  it('polls GET /api/practice/history keyed by venue and range', async () => {
    render(<Probe venue="paper" range="5D" />);
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('paper:5D:6'));
    expect(mocks.fetch).toHaveBeenCalledTimes(1);
    expect(String(mocks.fetch.mock.calls[0][0])).toContain('/api/practice/history?venue=paper&range=5D');
  });

  it('subscribes to nothing on Live -- no request, an idle state', async () => {
    render(<Probe venue="live" range="1D" />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId('probe').textContent).toBe('idle');
    expect(mocks.fetch).not.toHaveBeenCalled();
  });

  it('a range change is a different resource; invalidating the venue refetches it', async () => {
    const view = render(<Probe venue="sim" range="1D" />);
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('paper:1D:6'));
    view.rerender(<Probe venue="sim" range="YTD" />);
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('paper:YTD:6'));
    expect(mocks.fetch).toHaveBeenCalledTimes(2);
    expect(String(mocks.fetch.mock.calls[1][0])).toContain('venue=sim&range=YTD');
    await act(async () => { invalidateAccountHistory('sim'); });
    await waitFor(() => expect(mocks.fetch).toHaveBeenCalledTimes(3));
  });

  it('surfaces a failed poll as its message, never as an empty ledger', async () => {
    mocks.fetch.mockImplementation(async () => ({ ok: false, status: 503, json: async () => ({ detail: 'ledger locked' }) }));
    render(<Probe venue="paper" range="1D" />);
    await waitFor(() => expect(screen.getByTestId('probe').textContent).toBe('ledger locked'));
  });
});
