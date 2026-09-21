/**
 * Where the symbol menu opens. A right-click on a trader tab lands inside the
 * app bar, and a menu dropped at the pointer covered the Sim session bar
 * beneath the tabs (operator, 2026-09-21). The menu now opens below the whole
 * app bar -- over the notice or the chart, never over the bar -- and stays
 * inside the viewport.
 */
export const BOT_SYMBOL_MENU_GAP_PX = 4;
export const BOT_SYMBOL_MENU_WIDTH_PX = 240;

export function botSymbolMenuPosition(args: {
  x: number;
  y: number;
  /** Bottom edge of the app bar (viewport px); null when there is no bar. */
  appBarBottom: number | null;
  viewportWidth: number;
  menuWidth?: number;
}): { top: number; left: number } {
  const width = args.menuWidth ?? BOT_SYMBOL_MENU_WIDTH_PX;
  const top = args.appBarBottom != null ? Math.max(args.y, args.appBarBottom + BOT_SYMBOL_MENU_GAP_PX) : args.y;
  const left = Math.max(0, Math.min(args.x, args.viewportWidth - width));
  return { top, left };
}
