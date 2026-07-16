import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  STOCK_VIEW_QUERY_VIEW,
  buildStockViewUrl,
  openStockViewWindow,
  parseStockViewSymbol,
} from './stockViewNav';

describe('stockViewNav', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      location: { href: 'http://127.0.0.1:5173/' },
      open: vi.fn(),
      novaDesktop: undefined,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds a Stock View URL with view=stock and uppercased symbol', () => {
    const url = buildStockViewUrl('lvlu', 'http://127.0.0.1:5173/');
    expect(url).toContain('view=stock');
    expect(url).toContain('symbol=LVLU');
  });

  it('parses the symbol only when view=stock', () => {
    expect(parseStockViewSymbol('?view=stock&symbol=lvlu')).toBe('LVLU');
    expect(parseStockViewSymbol('?symbol=LVLU')).toBeNull();
    expect(parseStockViewSymbol(`?view=${STOCK_VIEW_QUERY_VIEW}`)).toBeNull();
  });

  it('uses desktop IPC when novaDesktop.openStockView is available', async () => {
    const openStockView = vi.fn(async () => true);
    window.novaDesktop = {
      isDesktop: true,
      apiBase: 'http://127.0.0.1:8000',
      getVersion: async () => 'test',
      openStockView,
    };
    const openSpy = vi.fn();
    window.open = openSpy as typeof window.open;
    await expect(openStockViewWindow('lvlu')).resolves.toBe(true);
    expect(openStockView).toHaveBeenCalledOnce();
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('opens a named popup window with size features (not a bare tab)', async () => {
    const fakeWin = { opener: {} as Window | null, focus: vi.fn() };
    const openSpy = vi.fn(
      (_url?: string | URL, _name?: string, _features?: string) =>
        fakeWin as unknown as Window,
    );
    window.open = openSpy as typeof window.open;
    await expect(openStockViewWindow('SHPH')).resolves.toBe(true);
    expect(openSpy).toHaveBeenCalledOnce();
    expect(openSpy).toHaveBeenCalledWith(
      expect.stringContaining('symbol=SHPH'),
      'nova-stock-SHPH',
      expect.stringMatching(/popup=yes.*width=\d+.*height=\d+/),
    );
    const features = String(openSpy.mock.calls[0]?.[2] ?? '');
    expect(features).not.toContain('noopener');
    expect(fakeWin.opener).toBeNull();
    expect(fakeWin.focus).toHaveBeenCalledOnce();
  });
});
