/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReportsImport } from './ReportsImport';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ReportsImport', () => {
  it('uploads a file and reports imported count', async () => {
    const onImported = vi.fn();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, imported: 1, source: 'csv', skipped: 0 }),
      }),
    );
    render(<ReportsImport onImported={onImported} />);
    const input = screen.getByTestId('reports-import-input') as HTMLInputElement;
    const file = new File(
      ['symbol,side,qty,entry_price,exit_price,pnl,closed_at\nIMP,long,1,1,1.1,1,2026-03-15\n'],
      'valid_trades.csv',
      { type: 'text/csv' },
    );
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => {
      expect(screen.getByText(/Imported 1 trade/)).toBeTruthy();
    });
    expect(onImported).toHaveBeenCalledTimes(1);
  });

  it('shows a loud skip when the API rejects missing facts', async () => {
    render(<ReportsImport onImported={() => {}} />);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({
          detail: {
            ok: false,
            imported: 0,
            error: 'No valid trades -- every row lacked a required fact.',
            errors: ['row 0: missing'],
          },
        }),
      }),
    );
    const input = screen.getByTestId('reports-import-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'bad.csv', { type: 'text/csv' })] },
    });
    await waitFor(() => {
      expect(screen.getByText(/required fact/)).toBeTruthy();
    });
  });
});
