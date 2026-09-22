import { describe, expect, it, vi } from 'vitest';
import {
  envelopeTables,
  nextRetryDelay,
  readScannerEnvelope,
  scannerRestErrorText,
  scannerRestTransportError,
} from './scannerRest';
import { applyEnvelopeTables, applyScannerTableReplies, readCatalystReply } from './scannerRestApply';

function reply(status: number, body: string): Response {
  return new Response(body, { status, headers: { 'Content-Type': 'text/plain' } });
}

describe('readScannerEnvelope (QA C31)', () => {
  it('names every failure shape instead of swallowing it', async () => {
    const shapes: Array<[Response, RegExp]> = [
      [reply(500, 'Internal Server Error'), /HTTP 500/],
      [reply(404, '{"detail":"Not Found"}'), /HTTP 404/],
      [reply(502, '<html>Bad gateway</html>'), /HTTP 502/],
      [reply(200, '<html>oops</html>'), /not JSON/],
      [reply(200, ''), /not JSON/],
      [reply(200, '{"gainers": ['), /not JSON/],
      [reply(200, 'null'), /unreadable/],
      [reply(200, '[1, 2]'), /unreadable/],
    ];
    for (const [res, pattern] of shapes) {
      const read = await readScannerEnvelope(res, '/api/movers');
      expect(read.ok).toBe(false);
      if (!read.ok) {
        expect(read.error).toMatch(pattern);
        expect(read.error).toContain('/api/movers');
      }
    }
    const ok = await readScannerEnvelope(reply(200, '{"mode":"closed"}'), '/api/movers');
    expect(ok).toEqual({ ok: true, data: { mode: 'closed' } });
  });

  it('writes one board line and backs off the retry', () => {
    expect(scannerRestErrorText([])).toBeNull();
    expect(scannerRestErrorText(['/api/movers answered HTTP 500'])).toBe('Scanner feed failed: /api/movers answered HTTP 500');
    expect(scannerRestTransportError(new DOMException('t', 'TimeoutError'))).toMatch(/did not answer in time/);
    expect(scannerRestTransportError(new TypeError('Failed to fetch'))).toMatch(/could not be reached/);
    expect([0, 1, 2, 3, 9].map((n) => nextRetryDelay(n, 2000, 30000))).toEqual([2000, 4000, 8000, 16000, 30000]);
  });
});

describe('applyScannerTableReplies', () => {
  function sink() {
    return {
      applyEnvelope: vi.fn(),
      setGappers: vi.fn(),
      setGainers: vi.fn(),
      setLosers: vi.fn(),
      setAfterhours: vi.fn(),
      setLargeCap: vi.fn(),
      setLastGood: vi.fn(),
      setTableMeta: vi.fn(),
      setScanAges: vi.fn(),
    };
  }

  it('applies the routes that answered and returns the ones that failed', async () => {
    const s = sink();
    const failures = await applyScannerTableReplies(
      {
        gappers: reply(200, JSON.stringify({ mode: 'closed', gappers: [{ symbol: 'GRML' }], last_scan: 10 })),
        movers: reply(500, 'Internal Server Error'),
        afterhours: reply(200, JSON.stringify({ afterhours: [] })),
        largeCap: reply(200, '[]'),
      },
      s,
    );
    expect(failures).toEqual(['/api/movers answered HTTP 500', '/api/large-cap answered an unreadable body']);
    expect(s.applyEnvelope).toHaveBeenCalledTimes(2);
    expect(s.setGappers).toHaveBeenCalledTimes(1);
    expect(s.setGainers).not.toHaveBeenCalled();
  });

  it('reads catalysts rows or states why not', async () => {
    expect((await readCatalystReply(reply(503, 'x'))).error).toMatch(/HTTP 503/);
    expect((await readCatalystReply(reply(200, '[]'))).error).toMatch(/not readable/);
    const good = await readCatalystReply(reply(200, JSON.stringify({ catalysts: [{ symbol: 'qnme' }] })));
    expect(good.rows?.map((c) => c.symbol)).toEqual(['QNME']);
  });
});

describe('envelope tables (QA C48)', () => {
  it('reads each table state and last scan, ignoring junk', () => {
    const data = {
      tables: {
        gappers: { table_state: 'frozen', roster_ts: 5, last_scan: 100 },
        gainers: { table_state: 'live', roster_ts: 6, last_scan: 'x' },
        bogus: { table_state: 'live' },
        losers: null,
      },
    };
    expect(envelopeTables(data)).toEqual([
      { table: 'gappers', state: 'frozen', rosterTs: 5, lastScan: 100 },
      { table: 'gainers', state: 'live', rosterTs: 6, lastScan: null },
    ]);
    expect(envelopeTables({ tables: [] })).toEqual([]);
  });

  it('merges table meta and only ever moves scan ages forward', () => {
    let meta: Record<string, unknown> = {};
    let ages = { gappers: 200, movers: 0, afterhours: 0, largeCap: 0 };
    const s = {
      setTableMeta: vi.fn((fn: (p: typeof meta) => typeof meta) => { meta = fn(meta); }),
      setScanAges: vi.fn((fn: (p: typeof ages) => typeof ages) => { ages = fn(ages); }),
    } as unknown as Parameters<typeof applyEnvelopeTables>[1];
    applyEnvelopeTables({
      tables: {
        gappers: { table_state: 'frozen', roster_ts: 5, last_scan: 100 },
        gainers: { table_state: 'live', roster_ts: 6, last_scan: 300 },
      },
    }, s);
    expect(Object.keys(meta)).toEqual(['gappers', 'gainers']);
    expect(ages).toEqual({ gappers: 200, movers: 300, afterhours: 0, largeCap: 0 });
  });
});
