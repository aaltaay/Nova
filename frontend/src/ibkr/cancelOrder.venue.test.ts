/**
 * @vitest-environment jsdom
 *
 * A cancel names the venue its row came from (#655, #657): the backend refuses
 * VENUE_CHANGED when the desk has moved, instead of cancelling that venue's
 * order of the same number.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./ibkrAccountPoller', () => ({ getIbkrAccountSnapshot: vi.fn(() => ({ venue: 'paper' })) }));

import { cancelIbkrOrder } from './cancelOrder';
import { getIbkrAccountSnapshot } from './ibkrAccountPoller';

describe('cancelIbkrOrder venue', () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch() {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ ok: true }) }));
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
  }

  it('sends the venue the rows came from', async () => {
    const fetchMock = stubFetch();
    await cancelIbkrOrder(12);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/ibkr\/order\/12\?venue=paper$/);
  });

  it('sends none while the rows name no venue', async () => {
    vi.mocked(getIbkrAccountSnapshot).mockReturnValueOnce({ venue: null } as never);
    const fetchMock = stubFetch();
    await cancelIbkrOrder(12);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/ibkr\/order\/12$/);
  });
});
