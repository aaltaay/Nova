/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { importJournalFile } from './importJournal';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('importJournalFile', () => {
  it('POSTs the file as multipart and returns imported count', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, imported: 1, source: 'csv', skipped: 0 }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const file = new File(['symbol,side\n'], 'valid_trades.csv', { type: 'text/csv' });
    const result = await importJournalFile(file);
    expect(result.imported).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    const sent = JSON.parse(String(init.body)) as { filename: string; content: string };
    expect(sent.filename).toBe('valid_trades.csv');
    expect(sent.content).toContain('symbol,side');
  });

  it('surfaces skipped-row errors without inventing a success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({
          detail: {
            ok: false,
            imported: 0,
            skipped: 1,
            error: 'No valid trades -- every row lacked a required fact.',
            errors: ['row 0: missing'],
          },
        }),
      }),
    );
    const file = new File(['bad'], 'bad.csv', { type: 'text/csv' });
    await expect(importJournalFile(file)).rejects.toThrow(/required fact/);
  });
});
