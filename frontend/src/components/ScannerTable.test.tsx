/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LARGE_CAP_COLUMNS, SCANNER_ROW_NUM_LABEL } from '../constants';
import type { ScannerRow } from '../types/scanner';
import { ScannerTable } from './ScannerTable';

// Row marks / hover actions read the recording + bot stores, whose
// subscriptions start pollers; keep this a pure rendering test.
vi.mock('./useScannerRowFacts', () => ({
  useScannerRowFacts: () => ({ recording: false, allowlisted: false, depthHeld: false }),
}));
vi.mock('../bot/useBotAllowlist', () => ({
  useBotAllowlist: () => ({ symbols: [], isAllowed: () => false, add: vi.fn(), remove: vi.fn(), refresh: vi.fn() }),
}));

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

    // The th title carries each column's full name; a narrow icon column may
    // show a short label (QA: "EARNINGS" was clipped to "EARNIN").
    const headers = [...container.querySelectorAll('thead th')].map(
      th => th.getAttribute('title') || (th.textContent?.replace(/[↑↓↕]/g, '').trim() ?? ''),
    );
    expect(headers).toContain('News');
    expect(headers).toContain('Earnings');
    expect(headers).toContain('Days');
    expect(headers.filter(h => h === 'Earnings')).toHaveLength(1);
    const earnings = container.querySelector('thead th[data-col="earnings_day_offset"] .th-label');
    expect(earnings?.textContent).toBe('Earn');
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

  const HONESTY_COLUMNS: [string, string][] = [
    ['symbol', 'Symbol'],
    ['price', 'Price'],
    ['change_pct', 'Change'],
    ['gap_percent', 'Gap %'],
    ['volume', 'Volume · RVOL'],
  ];

  async function renderRows(data: ScannerRow[]) {
    await act(() => {
      root.render(
        <ScannerTable
          columns={HONESTY_COLUMNS}
          data={data}
          sortState={{ key: '', dir: null }}
          onSort={() => {}}
          selectedSymbol={null}
          onSelect={() => {}}
          onOpenTrading={() => {}}
        />,
      );
    });
  }

  it('states a missing change, gap and name-only volume as muted dashes (QA V21 / C37)', async () => {
    await renderRows([{ ...row('SMX'), price: null, change_pct: null, change_abs: null, gap_percent: null, volume: null }]);
    const change = container.querySelector('td[data-col="change_pct"] .cell-stack-primary') as HTMLElement;
    expect(change.textContent).toBe('—');
    expect(change.className).not.toContain('negative');
    expect(container.querySelector('td[data-col="gap_percent"]')?.textContent).toBe('—');
    expect(container.querySelector('td[data-col="volume"] .cell-stack-primary')?.textContent).toBe('—');
    expect(container.textContent).not.toContain('N/A');
  });

  it('names the RVOL source each row really divides by (QA C39)', async () => {
    await renderRows([
      { ...row('GRML'), rel_volume: 54.37, rvol_source: 'yfinance' },
      { ...row('TOPS'), rel_volume: 54.29, rvol_source: 'alpaca' },
      { ...row('OLD'), rel_volume: 2.5 },
    ]);
    const badges = [...container.querySelectorAll('.rvol-source-badge')].map((b) => b.textContent);
    expect(badges).toEqual(['yf', 'IEX', 'avg?']);
    expect((container.querySelectorAll('.rvol-source-badge')[1] as HTMLElement).title).toMatch(/Alpaca IEX/);
  });

  it('shows a prior-close fallback as a close, not a live price with 0.00% (QA C50)', async () => {
    await renderRows([{ ...row('GDC'), price: 2, change_pct: 0, change_abs: 0, quote_quality: 'close_fallback' }]);
    const price = container.querySelector('td[data-col="price"]') as HTMLElement;
    expect(price.textContent).toContain('$2.00');
    expect(price.textContent).toContain('close');
    const change = container.querySelector('td[data-col="change_pct"]') as HTMLElement;
    expect(change.textContent).not.toContain('0.00%');
    expect(change.textContent).toContain('—');
  });

  it('states no gap for a prior-close fallback either (QA W12)', async () => {
    await renderRows([{ ...row('CLSF'), price: 2, change_pct: 0, change_abs: 0, gap_percent: 0, quote_quality: 'close_fallback' }]);
    const gap = container.querySelector('td[data-col="gap_percent"]') as HTMLElement;
    expect(gap.textContent).toBe('—');
    expect(gap.querySelector('.positive')).toBeNull();
    expect((gap.firstElementChild as HTMLElement).title).toMatch(/No trade yet/);
  });

  it('writes a flat move without a sign or a tone (QA W21)', async () => {
    await renderRows([{ ...row('NEGZ'), change_pct: -0.000025, change_abs: -0.0001, gap_percent: 0 }]);
    const change = container.querySelector('td[data-col="change_pct"]') as HTMLElement;
    expect(change.textContent).toContain('0.00%');
    expect(change.textContent).not.toContain('-0.00%');
    expect(change.textContent).toContain('$0.00');
    expect(change.querySelector('.negative, .positive')).toBeNull();
  });
});

describe('ScannerTable float and short interest (#532)', () => {
  let container: HTMLDivElement;
  let root: Root;
  const AUG_31 = Date.UTC(2026, 7, 31) / 1000;
  const REASON =
    'Float 54K is under half of the 568K shares not held by insiders (568K outstanding, 0% insiders) -- likely stale since a dilution';

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

  async function render(data: ScannerRow[]) {
    await act(() => {
      root.render(
        <ScannerTable
          columns={[['symbol', 'Symbol'], ['float', 'Float'], ['short_interest', 'Short Int.']]}
          data={data}
          sortState={{ key: '', dir: null }}
          onSort={() => {}}
          selectedSymbol={null}
          onSelect={() => {}}
          onOpenTrading={() => {}}
        />,
      );
    });
  }

  const cell = (i: number, col: string) =>
    container.querySelectorAll(`td[data-col="${col}"]`)[i] as HTMLElement;

  it('marks a contradicted float "54.0K?" and says why on hover', async () => {
    await render([
      { ...row('WHLR'), float: 54_000, shares_outstanding: 568_000, float_contradicted: true, float_contradicted_reason: REASON },
      { ...row('AAPL'), float: 14_800_000_000, float_contradicted: false, float_contradicted_reason: null },
      { ...row('OLD'), float: 54_000 },
    ]);
    const whlr = cell(0, 'float').firstElementChild as HTMLElement;
    expect(whlr.textContent).toBe('54.0K?');
    expect(whlr.title).toBe(REASON);
    expect(whlr.dataset.floatContradicted).toBe('true');
    const aapl = cell(1, 'float').firstElementChild as HTMLElement;
    expect(aapl.textContent).toBe('14.80B');
    expect(aapl.title).toBe('');
    expect(cell(2, 'float').textContent).toBe('54.0K');
  });

  it("puts the settlement date over Yahoo's ratio and names both on hover", async () => {
    await render([
      { ...row('WNW'), short_interest: 319_000, short_ratio: 6.9, short_interest_ts: AUG_31 },
      { ...row('NODATE'), short_interest: 88_477, short_ratio: 0.02 },
      { ...row('NONE') },
    ]);
    const wnw = cell(0, 'short_interest').firstElementChild as HTMLElement;
    expect(wnw.querySelector('.cell-stack-primary')?.textContent).toBe('319.0K');
    expect(wnw.querySelector('.cell-stack-secondary')?.textContent).toBe('8/31 · 6.9');
    expect(wnw.title).toContain('FINRA settlement Aug 31, 2026');
    expect(wnw.title).toContain("Short ratio 6.9 is Yahoo's own");
    const undated = cell(1, 'short_interest').firstElementChild as HTMLElement;
    expect(undated.querySelector('.cell-stack-secondary')?.textContent).toBe('0.0 ratio');
    expect(undated.title).toContain('settlement date not reported');
    // No figure, no date: both lines are stated absences (the row's hover actions share this last cell).
    expect(cell(2, 'short_interest').firstElementChild?.textContent).toBe('——');
    expect((cell(2, 'short_interest').firstElementChild as HTMLElement).title).toBe('');
  });
});
