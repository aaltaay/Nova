/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VolumeBoostTable } from './VolumeBoostTable';
import type { VolumeBoostRow } from './types';

function spike(symbol: string, over: Partial<VolumeBoostRow>): VolumeBoostRow {
  return {
    symbol,
    price: 1,
    spike_ratio: 5,
    spike_shares: 10_000,
    baseline_shares: 2_000,
    baseline_rate: 3,
    status: 'hot',
    spike_started_ts: 1,
    age_sec: 30,
    ...over,
  };
}

const ROWS: VolumeBoostRow[] = [
  spike('AAA', { spike_ratio: 3.1, age_sec: 74, status: 'cooling' }),
  spike('BBB', { spike_ratio: 8.4, age_sec: 14 }),
  spike('CCC', { spike_ratio: null, age_sec: null }),
  spike('DDD', { spike_ratio: 5.2, age_sec: 40 }),
];

const order = () => screen.getAllByRole('row').slice(1).map(r => r.querySelector('[data-col="symbol"]')?.textContent);

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe('VolumeBoostTable sorting', () => {
  function renderTable() {
    render(<VolumeBoostTable rows={ROWS} selectedSymbol={null} onSelect={vi.fn()} onOpenTrading={vi.fn()} />);
  }

  it('sorts the spike biggest first, then smallest, with an unknown spike last both ways', () => {
    renderTable();
    const spikeHead = screen.getByRole('columnheader', { name: 'Spike' });
    fireEvent.click(spikeHead);
    expect(order()).toEqual(['BBB', 'DDD', 'AAA', 'CCC']);
    fireEvent.click(spikeHead);
    expect(order()).toEqual(['AAA', 'DDD', 'BBB', 'CCC']);
    fireEvent.click(spikeHead);
    expect(order()).toEqual(['AAA', 'BBB', 'CCC', 'DDD']);
  });

  it('starts Age with the newest spike and Status with Hot', () => {
    renderTable();
    fireEvent.click(screen.getByRole('columnheader', { name: 'Age' }));
    expect(order()).toEqual(['BBB', 'DDD', 'AAA', 'CCC']);
    fireEvent.click(screen.getByRole('columnheader', { name: 'Status' }));
    expect(order()).toEqual(['BBB', 'CCC', 'DDD', 'AAA']);
  });
});
