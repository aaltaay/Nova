import { describe, expect, it } from 'vitest';
import {
  closeBotSymbolMenu,
  getBotSymbolMenu,
  openBotSymbolMenu,
  subscribeBotSymbolMenu,
} from './botSymbolMenuStore';

describe('botSymbolMenuStore', () => {
  it('opens and closes a symbol menu', () => {
    const seen: Array<string | null> = [];
    const unsub = subscribeBotSymbolMenu(value => {
      seen.push(value?.symbol ?? null);
    });
    openBotSymbolMenu('abcd', 10, 20);
    expect(getBotSymbolMenu()).toEqual({ symbol: 'ABCD', x: 10, y: 20 });
    closeBotSymbolMenu();
    expect(getBotSymbolMenu()).toBeNull();
    unsub();
    expect(seen).toEqual(['ABCD', null]);
  });
});
