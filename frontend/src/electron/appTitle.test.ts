import { describe, expect, it } from 'vitest';
import {
  backendRemedy,
  formatElectronTraderTitle,
  formatScannerWindowTitle,
  formatTraderDocumentTitle,
  injectNovaTitle,
  isOlderTag,
  novaWindowTitle,
  resolveNovaTitleDesk,
  withBackendTag,
} from '../../electron/appTitle.mjs';

describe('Nova window titles', () => {
  it('keeps the scanner view label and appends vNNN', () => {
    expect(formatScannerWindowTitle('v477')).toBe('Nova — Stock Scanner · v477');
  });

  it('keeps the trader document.title shape and appends vNNN', () => {
    expect(formatTraderDocumentTitle('AAPL', 'v477')).toBe(
      'AAPL · Trader · Nova · v477',
    );
  });

  it('uses the Trader view label when the tab is still a draft', () => {
    expect(formatTraderDocumentTitle('', 'v477')).toBe('Trader · Nova · v477');
    expect(formatTraderDocumentTitle('   ', 'v042')).toBe('Trader · Nova · v042');
  });

  it('keeps popped-out Electron titles as Nova -- SYMBOL plus version', () => {
    expect(formatElectronTraderTitle('SWVL', 'v477')).toBe('Nova -- SWVL · v477');
  });

  it('omits the version suffix when the tag is empty', () => {
    expect(formatScannerWindowTitle('')).toBe('Nova — Stock Scanner');
    expect(formatTraderDocumentTitle('AAPL', '  ')).toBe('AAPL · Trader · Nova');
  });

  it('picks scanner vs trader from desk state', () => {
    expect(
      novaWindowTitle({
        traderActive: false,
        traderSymbol: 'AAPL',
        releaseTag: 'v477',
      }),
    ).toBe('Nova — Stock Scanner · v477');
    expect(
      novaWindowTitle({
        traderActive: true,
        traderSymbol: 'AAPL',
        releaseTag: 'v477',
      }),
    ).toBe('AAPL · Trader · Nova · v477');
  });

  it('treats sample+symbol as Trader so e2e ?view=sample&symbol=SMPL keeps the view label', () => {
    expect(
      resolveNovaTitleDesk({
        sampleMode: true,
        sampleSymbol: 'SMPL',
        liveTraderActive: false,
        liveTraderSymbol: null,
      }),
    ).toEqual({ traderActive: true, traderSymbol: 'SMPL' });
    expect(
      resolveNovaTitleDesk({
        sampleMode: true,
        sampleSymbol: '',
        liveTraderActive: true,
        liveTraderSymbol: 'AAPL',
      }),
    ).toEqual({ traderActive: false, traderSymbol: '' });
  });

  it('names the backend revision after the desk one, and says when it is older', () => {
    const desk = 'Nova — Stock Scanner · v1006';
    expect(withBackendTag(desk, 'v1006', 'v1006')).toBe('Nova — Stock Scanner · v1006 · backend v1006');
    expect(withBackendTag(desk, 'v991', 'v1006'))
      .toBe('Nova — Stock Scanner · v1006 · backend v991 (older -- restart it)');
    // A backend newer than the desk (the desk not updated yet) is named, never called older.
    expect(withBackendTag('Nova — Stock Scanner · v991', 'v1006', 'v991'))
      .toBe('Nova — Stock Scanner · v991 · backend v1006');
    // Unknown adds nothing: the API not answering, the sample desk.
    expect(withBackendTag(desk, null, 'v1006')).toBe(desk);
    expect(withBackendTag(desk, '  ', 'v1006')).toBe(desk);
  });

  it('says to pull first when a restart would load the same code (operator report 2026-09-25)', () => {
    // The desk updated itself to v1024; the backend runs v1017 from a checkout still at v1017.
    const desk = 'Nova — Stock Scanner · v1024';
    expect(withBackendTag(desk, 'v1017', 'v1024', 'v1017'))
      .toBe('Nova — Stock Scanner · v1024 · backend v1017 (older -- pull master, then restart)');
    // The checkout was pulled: a restart loads newer code.
    expect(withBackendTag(desk, 'v1017', 'v1024', 'v1024'))
      .toBe('Nova — Stock Scanner · v1024 · backend v1017 (older -- restart it)');
    // Ahead of the backend but still behind the desk: a restart still helps.
    expect(withBackendTag(desk, 'v1017', 'v1024', 'v1020')).toContain('(older -- restart it)');
    // A checkout Nova cannot read keeps the old advice rather than guessing.
    expect(withBackendTag(desk, 'v1017', 'v1024', null)).toContain('(older -- restart it)');
    expect(withBackendTag(desk, 'v1017', 'v1024', 'main')).toContain('(older -- restart it)');
    // A checkout behind what runs: a restart would load older code still.
    expect(withBackendTag(desk, 'v1017', 'v1024', 'v1010')).toContain('(older -- pull master, then restart)');
  });

  it('names what an older backend needs, and nothing for one that is not older', () => {
    expect(backendRemedy('v1017', 'v1024', 'v1017')).toBe('pull');
    expect(backendRemedy('v1017', 'v1024', 'v1024')).toBe('restart');
    expect(backendRemedy('v1017', 'v1024', undefined)).toBe('restart');
    expect(backendRemedy('v1024', 'v1024', 'v1017')).toBeNull();
    expect(backendRemedy('v1025', 'v1024', 'v1025')).toBeNull();
    expect(backendRemedy(null, 'v1024', 'v1017')).toBeNull();
  });

  it('carries the checkout revision through the whole window title', () => {
    expect(novaWindowTitle({
      releaseTag: 'v1024', backendTag: 'v1017', checkoutTag: 'v1017',
    })).toBe('Nova — Stock Scanner · v1024 · backend v1017 (older -- pull master, then restart)');
  });

  it('compares revisions by number, never as text', () => {
    expect(isOlderTag('v991', 'v1006')).toBe(true);
    expect(isOlderTag('v1006', 'v991')).toBe(false);
    expect(isOlderTag('v1006', 'v1006')).toBe(false);
    expect(isOlderTag('dev', 'v1006')).toBe(false);
    expect(isOlderTag('v991', '')).toBe(false);
  });

  it('keeps the backend revision on the trader view and under REC', () => {
    expect(novaWindowTitle({
      traderActive: true, traderSymbol: 'AAPL', releaseTag: 'v1006', backendTag: 'v1006', recordingSymbol: 'GRML',
    })).toBe('● REC GRML — AAPL · Trader · Nova · v1006 · backend v1006');
  });

  it('rewrites the HTML title tag for first paint', () => {
    const html = '<html><head><title>Nova — Stock Scanner</title></head></html>';
    expect(injectNovaTitle(html, 'v477')).toContain(
      '<title>Nova — Stock Scanner · v477</title>',
    );
  });
});
