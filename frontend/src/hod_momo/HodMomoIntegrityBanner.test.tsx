/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HodMomoIntegrityBanner } from './HodMomoIntegrityBanner';

describe('HodMomoIntegrityBanner', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it('hides on pass', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'pass', ok: true, checks: [] }),
    });
    await act(async () => {
      root.render(<HodMomoIntegrityBanner />);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="hod-integrity-banner"]')).toBeNull();
  });

  it('shows fail checks and uncovered symbols', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'fail',
        ok: false,
        checks: [
          { id: 'hod_ticks_flowing', status: 'fail', detail: 'no ticks' },
          { id: 'ok', status: 'pass', detail: 'fine' },
        ],
        hod: { metrics: { uncovered_symbols: ['ZZZ'], uncovered_count: 1 } },
      }),
    });
    await act(async () => {
      root.render(<HodMomoIntegrityBanner />);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const banner = container.querySelector('[data-testid="hod-integrity-banner"]');
    expect(banner).not.toBeNull();
    expect(banner?.getAttribute('data-status')).toBe('fail');
    expect(banner?.textContent).toContain('hod_ticks_flowing');
    expect(banner?.textContent).toContain('ZZZ');
  });

  it('shows warn state', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'warn',
        ok: false,
        checks: [{ id: 'hod_enrichment', status: 'warn', detail: 'low rvol' }],
      }),
    });
    await act(async () => {
      root.render(<HodMomoIntegrityBanner />);
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const banner = container.querySelector('[data-testid="hod-integrity-banner"]');
    expect(banner?.getAttribute('data-status')).toBe('warn');
  });
});
