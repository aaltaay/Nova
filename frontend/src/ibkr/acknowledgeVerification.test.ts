import { beforeEach, describe, expect, it, vi } from 'vitest';
import { novaFetch } from '../api/novaFetch';
import { acknowledgeIbkrVerification } from './acknowledgeVerification';

vi.mock('../api/novaFetch', () => ({
  novaFetch: vi.fn(),
}));

describe('acknowledgeIbkrVerification', () => {
  beforeEach(() => {
    vi.mocked(novaFetch).mockReset();
  });

  it('clears the normalized symbol through the backend latch endpoint', async () => {
    vi.mocked(novaFetch).mockResolvedValue(
      new Response(JSON.stringify({ ok: true, symbol: 'AAPL', cleared: true }), {
        status: 200,
      }),
    );

    await expect(acknowledgeIbkrVerification(' aapl ')).resolves.toBe(true);
    expect(novaFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ibkr/verification/AAPL/acknowledge'),
      { method: 'POST' },
    );
  });

  it('does not report acknowledgment when the backend refuses it', async () => {
    vi.mocked(novaFetch).mockResolvedValue(
      new Response(JSON.stringify({ ok: false }), { status: 503 }),
    );

    await expect(acknowledgeIbkrVerification('AAPL')).resolves.toBe(false);
  });
});
