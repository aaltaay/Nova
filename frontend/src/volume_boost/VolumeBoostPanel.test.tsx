/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VolumeBoostPanel } from './VolumeBoostPanel';
import type { VolumeBoostView } from './types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function emptyView(): VolumeBoostView {
  return {
    rev: '4',
    volume_boost: [],
    table_state: 'live',
    last_scan: 1,
    feed_error: null,
    watched: 12,
  };
}

function spikeView(): VolumeBoostView {
  return {
    ...emptyView(),
    volume_boost: [
      {
        symbol: 'SPIK',
        price: 2.5,
        spike_ratio: 7.2,
        spike_shares: 55_000,
        baseline_shares: 11_000,
        baseline_rate: 18.3,
        status: 'hot',
        spike_started_ts: 10,
        age_sec: 12,
      },
    ],
  };
}

describe('VolumeBoostPanel', () => {
  it('renders an honest empty desk when the API has no spikes', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => emptyView(),
      status: 200,
    }));
    vi.stubGlobal('fetch', fetchMock);

    await act(async () => {
      render(
        <VolumeBoostPanel
          selectedSymbol={null}
          onSelect={() => {}}
          onOpenTrading={() => {}}
        />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/volume-boost'),
      expect.anything(),
    );
    expect(screen.getByTestId('volume-boost-empty').textContent).toMatch(
      /No exceptional volume-rate spikes/,
    );
  });

  it('opens Trader from the ticker button', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => spikeView(),
      status: 200,
    }));
    vi.stubGlobal('fetch', fetchMock);
    const onSelect = vi.fn();
    const onOpenTrading = vi.fn();

    await act(async () => {
      render(
        <VolumeBoostPanel
          selectedSymbol={null}
          onSelect={onSelect}
          onOpenTrading={onOpenTrading}
        />,
      );
      await Promise.resolve();
      await Promise.resolve();
    });

    fireEvent.click(screen.getByRole('button', { name: 'SPIK' }));
    expect(onSelect).toHaveBeenCalledWith('SPIK');
    expect(onOpenTrading).toHaveBeenCalledWith('SPIK');
    expect(screen.getByText('7.2x')).toBeTruthy();
    expect(screen.getByText('12s ago')).toBeTruthy();
  });

  it('uses sample fixtures without fetching', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(
      <VolumeBoostPanel
        selectedSymbol={null}
        onSelect={() => {}}
        onOpenTrading={() => {}}
        sampleMode
      />,
    );
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText('BOOST')).toBeTruthy();
    expect(screen.getByText(/Sample Data mode/)).toBeTruthy();
  });
});
