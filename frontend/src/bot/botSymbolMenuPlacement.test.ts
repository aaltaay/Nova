import { describe, expect, it } from 'vitest';
import { BOT_SYMBOL_MENU_GAP_PX, botSymbolMenuPosition } from './botSymbolMenuPlacement';

describe('botSymbolMenuPosition', () => {
  it('opens below the app bar when the click landed inside it (a trader tab)', () => {
    const at = botSymbolMenuPosition({ x: 120, y: 110, appBarBottom: 180, viewportWidth: 1400 });
    expect(at).toEqual({ top: 180 + BOT_SYMBOL_MENU_GAP_PX, left: 120 });
  });

  it('opens at the pointer for a click already below the bar (a scanner row)', () => {
    expect(botSymbolMenuPosition({ x: 300, y: 500, appBarBottom: 180, viewportWidth: 1400 }))
      .toEqual({ top: 500, left: 300 });
    expect(botSymbolMenuPosition({ x: 300, y: 500, appBarBottom: null, viewportWidth: 1400 }))
      .toEqual({ top: 500, left: 300 });
  });

  it('stays inside the viewport on the right edge', () => {
    expect(botSymbolMenuPosition({ x: 1390, y: 500, appBarBottom: null, viewportWidth: 1400, menuWidth: 240 }).left)
      .toBe(1160);
  });
});
