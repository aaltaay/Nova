/**
 * Where the symbol menu opens. A right-click on a trader tab lands inside the
 * app bar, and a menu dropped at the pointer covered the Sim session bar
 * beneath the tabs (operator, 2026-09-21). The menu now opens below the whole
 * app bar -- over the notice or the chart, never over the bar -- and stays
 * inside the viewport: a right-click low on the screen (a Focus rail or Desk
 * row) opens the menu upward far enough to show all of it.
 */
export const BOT_SYMBOL_MENU_GAP_PX = 4;
/** Mirrors `.symbol-menu { width }` in symbolMenu.css. */
export const BOT_SYMBOL_MENU_WIDTH_PX = 288;

export function botSymbolMenuPosition(args: {
  x: number;
  y: number;
  /** Bottom edge of the app bar (viewport px); null when there is no bar. */
  appBarBottom: number | null;
  viewportWidth: number;
  menuWidth?: number;
  /** With the menu's measured height, keeps its bottom on screen. */
  viewportHeight?: number;
  menuHeight?: number;
}): { top: number; left: number } {
  const width = args.menuWidth ?? BOT_SYMBOL_MENU_WIDTH_PX;
  const minTop = args.appBarBottom != null ? args.appBarBottom + BOT_SYMBOL_MENU_GAP_PX : 0;
  let top = Math.max(args.y, minTop);
  if (args.viewportHeight != null && args.menuHeight != null && args.menuHeight > 0) {
    top = Math.max(minTop, Math.min(top, args.viewportHeight - args.menuHeight - BOT_SYMBOL_MENU_GAP_PX));
  }
  const left = Math.max(0, Math.min(args.x, args.viewportWidth - width));
  return { top, left };
}
