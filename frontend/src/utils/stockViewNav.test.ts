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
    (window as Window & { novaDesktop?: unknown }).novaDesktop = {
      isDesktop: true,
      openStockView,
    };
    const openSpy = vi.fn();
    window.open = openSpy as typeof window.open;
    await expect(openStockViewWindow('lvlu')).resolves.toBe(true);
    expect(openStockView).toHaveBeenCalledOnce();
    expect(openSpy).not.toHaveBeenCalled();
  });

  it('treats a real window.open handle as success (no noopener null trap)', async () => {
    const fakeWin = { opener: {} as Window | null };
    window.open = vi.fn(() => fakeWin as unknown as Window) as typeof window.open;
    await expect(openStockViewWindow('SHPH')).resolves.toBe(true);
    expect(fakeWin.opener).toBeNull();
  });
});
