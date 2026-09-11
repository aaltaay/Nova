/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SAMPLE_NOVA_NEWS_DESK } from './sampleDesk';
import { NovaNewsPanel } from './NovaNewsPanel';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('NovaNewsPanel', () => {
  it('fetches the desk and renders four criticality columns', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => SAMPLE_NOVA_NEWS_DESK,
    }));
    vi.stubGlobal('fetch', fetchMock);

    await act(async () => {
      render(
        <NovaNewsPanel selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/news/desk'),
      expect.anything(),
    );
    expect(screen.getByTestId('nova-news-grid')).toBeTruthy();
    expect(screen.getByTestId('nova-news-lead')).toBeTruthy();
    expect(screen.getAllByText('SEC charges ACME after FDA rejection').length).toBeGreaterThan(0);
    expect(screen.getByTestId('nova-news-column-critical')).toBeTruthy();
    expect(screen.getByTestId('nova-news-column-background')).toBeTruthy();
  });

  it('Yahoo filter hides non-yahoo stories', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => SAMPLE_NOVA_NEWS_DESK,
    })));

    await act(async () => {
      render(
        <NovaNewsPanel selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('tab', { name: 'Yahoo' }));
    });

    expect(screen.getAllByText(/NVDA contract award/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/SEC charges ACME/)).toBeNull();
  });

  it('shows a loud error instead of an empty success', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        ...SAMPLE_NOVA_NEWS_DESK,
        error: 'FINNHUB_API_KEY is not set.',
        stories: [],
        columns: { critical: [], high: [], watch: [], background: [] },
        counts: { critical: 0, high: 0, watch: 0, background: 0, total: 0 },
      }),
    })));

    await act(async () => {
      render(
        <NovaNewsPanel selectedSymbol={null} onSelect={() => {}} onOpenTrading={() => {}} />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId('nova-news-error').textContent).toMatch(/FINNHUB_API_KEY/);
  });

  it('sample mode uses fixtures and does not fetch', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await act(async () => {
      render(
        <NovaNewsPanel
          selectedSymbol={null}
          onSelect={() => {}}
          onOpenTrading={() => {}}
          sampleMode
        />,
      );
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getAllByText(/NVDA contract award/).length).toBeGreaterThan(0);
    expect(screen.getByTestId('nova-news-lead')).toBeTruthy();
  });
});
