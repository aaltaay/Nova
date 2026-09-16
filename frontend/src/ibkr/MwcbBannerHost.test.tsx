/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MwcbBannerHost } from './MwcbBannerHost';

afterEach(() => cleanup());

describe('MwcbBannerHost', () => {
  it('renders the desk banner from /api/halts/desk', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        mwcb: { level: 1, reason_code: 'MWC1', source: 'nasdaq_trade_halt_rss', stale: false },
      }),
    });
    render(<MwcbBannerHost fetchImpl={fetchImpl as unknown as typeof fetch} pollMs={60_000} />);
    await waitFor(() => {
      expect(screen.getByTestId('mwcb-banner').textContent).toMatch(/Level 1/);
    });
    expect(String(fetchImpl.mock.calls[0]?.[0])).toMatch(/\/api\/halts\/desk/);
  });

  it('stays hidden when the desk payload has no MWCB', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ mwcb: null }),
    });
    const { container } = render(
      <MwcbBannerHost fetchImpl={fetchImpl as unknown as typeof fetch} pollMs={60_000} />,
    );
    await waitFor(() => {
      expect(fetchImpl).toHaveBeenCalled();
    });
    expect(container.querySelector('[data-testid="mwcb-banner"]')).toBeNull();
  });
});
