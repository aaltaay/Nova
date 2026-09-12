/** Keep the cursor-anchored chart menu (and its submenu) inside the viewport. */
import {
  CHART_CONTEXT_MENU_EDGE_PAD_PX,
} from './chartContextMenuConstants';

export interface ChartMenuPlacementInput {
  x: number;
  y: number;
  menuWidth: number;
  menuHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  pad?: number;
}

/** Prefer down-right of the cursor; flip/clamp when that would overflow. */
export function chartContextMenuPosition(
  input: ChartMenuPlacementInput,
): { top: number; left: number } {
  const pad = input.pad ?? CHART_CONTEXT_MENU_EDGE_PAD_PX;
  const maxLeft = input.viewportWidth - input.menuWidth - pad;
  const maxTop = input.viewportHeight - input.menuHeight - pad;
  const left = input.x + input.menuWidth + pad > input.viewportWidth
    ? Math.max(pad, Math.min(input.x - input.menuWidth, maxLeft))
    : input.x;
  const top = input.y + input.menuHeight + pad > input.viewportHeight
    ? Math.max(pad, maxTop)
    : input.y;
  return { top: Math.max(pad, top), left: Math.max(pad, left) };
}

/** Submenu opens to the right of the parent row, or left when it would overflow. */
export function chartSubmenuPosition(input: {
  parentLeft: number;
  parentWidth: number;
  rowTop: number;
  submenuWidth: number;
  submenuHeight: number;
  viewportWidth: number;
  viewportHeight: number;
  pad?: number;
}): { top: number; left: number } {
  const pad = input.pad ?? CHART_CONTEXT_MENU_EDGE_PAD_PX;
  const rightEdge = input.parentLeft + input.parentWidth;
  const left = rightEdge + input.submenuWidth + pad > input.viewportWidth
    ? Math.max(pad, input.parentLeft - input.submenuWidth)
    : rightEdge;
  const maxTop = input.viewportHeight - input.submenuHeight - pad;
  return { top: Math.max(pad, Math.min(input.rowTop, maxTop)), left };
}
