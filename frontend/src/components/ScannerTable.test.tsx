/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LARGE_CAP_COLUMNS, SCANNER_ROW_NUM_LABEL } from '../constants';
import type { ScannerRow } from '../types/scanner';
import { ScannerTable } from './ScannerTable';

function row(symbol: string): ScannerRow {
  return {
    symbol,
    price: 1.25,
    prev_close: 1,
    change_pct: 25,
    change_abs: 0.25,
    gap_percent: 25,
    volume: 1000,
    rel_volume: null,
    has_news: false,
    newest_headline_at: null,
    market_cap: null,
    float: null,
    short_interest: null,
    short_ratio: null,
  };
}

describe('ScannerTable row numbers', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('numbers displayed rows 1..n and does not treat # as sortable', async () => {
    const onSort = vi.fn();
    await act(() => {
      root.render(
        <ScannerTable
          columns={[['symbol', 'Symbol'], ['price', 'Price']]}
          data={[row('AAA'), row('BBB')]}
          sortState={{ key: '', dir: null }}
          onSort={onSort}
          selectedSymbol={null}
          onSelect={() => {}}
          onOpenTrading={() => {}}
        />,
      );
    });

    const headers = [...container.querySelectorAll('thead th')].map(
      th => th.textContent?.trim() ?? '',
    );
    expect(headers[0]).toBe(SCANNER_ROW_NUM_LABEL);
    expect(container.querySelector('thead th.scanner-row-num-th')).not.toBeNull();

    const nums = [...container.querySelectorAll('td.scanner-row-num')].map(
      td => td.textContent?.trim(),
    );
    expect(nums).toEqual(['1', '2']);

    (container.querySelector('thead th.scanner-row-num-th') as HTMLElement).click();
    expect(onSort).not.toHaveBeenCalled();
  });

  it('shows shared News and Earnings headers on Large Cap columns', async () => {
    await act(() => {
      root.render(
        <ScannerTable
          columns={LARGE_CAP_COLUMNS}
          data={[row('NVDA')]}
          sortState={{ key: '', dir: null }}
          onSort={() => {}}
          selectedSymbol={null}
          onSelect={() => {}}
          onOpenTrading={() => {}}
        />,
      );
    });

    const headers = [...container.querySelectorAll('thead th')].map(
      th => th.textContent?.replace(/[↑↓↕]/g, '').trim() ?? '',
    );
    expect(headers).toContain('News');
    expect(headers).toContain('Earnings');
    expect(headers).toContain('Days');
    expect(headers.filter(h => h === 'Earnings')).toHaveLength(1);
    expect(container.querySelector('.earnings-dots')).not.toBeNull();
  });

  it('locks live numeric columns on the shared scanner shell', async () => {
    await act(() => {
      root.render(
        <ScannerTable
          columns={[
            ['symbol', 'Symbol'],
            ['price', 'Price'],
            ['change_pct', 'Change'],
            ['gap_percent', 'Gap %'],
          ]}
          data={[row('IMCC')]}
          sortState={{ key: '', dir: null }}
          onSort={() => {}}
          selectedSymbol={null}
          onSelect={() => {}}
          onOpenTrading={() => {}}
        />,
      );
    });

    expect(container.querySelector('.table-wrapper--scanner')).not.toBeNull();
    expect(container.querySelector('colgroup')).not.toBeNull();
    const changeTh = container.querySelector('th[data-col="change_pct"]');
    const gapTd = container.querySelector('td[data-col="gap_percent"]');
    expect(changeTh?.className).toContain('scanner-col--pct');
    expect(gapTd?.className).toContain('scanner-col--pct');
    expect(container.querySelector('td[data-col="price"]')?.className).toContain(
      'scanner-col--price',
    );
  });
});
