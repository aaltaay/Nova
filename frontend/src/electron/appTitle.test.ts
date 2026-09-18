import { describe, expect, it } from 'vitest';
import {
  formatElectronTraderTitle,
  formatScannerWindowTitle,
  formatTraderDocumentTitle,
  injectNovaTitle,
  novaWindowTitle,
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

  it('rewrites the HTML title tag for first paint', () => {
    const html = '<html><head><title>Nova — Stock Scanner</title></head></html>';
    expect(injectNovaTitle(html, 'v477')).toContain(
      '<title>Nova — Stock Scanner · v477</title>',
    );
  });
});
