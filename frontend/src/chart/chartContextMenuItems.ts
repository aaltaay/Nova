/**
 * Pure model for the chart right-click menu.
 *
 * Only rows Nova can actually perform are built. Webull's Create Alert / Add to
 * Watchlist / Line Style / Show Layers / Chart Settings have no Nova surface
 * yet (watchlist is read-only Nova OS output, alerts are delivery channels), so
 * they are omitted rather than shipped as dead "Coming soon" rows (#116).
 */
import { formatSeedPrice } from '../ibkr/tradeDefaultSeed';
import {
  CHART_CONTEXT_MENU_BUY,
  CHART_CONTEXT_MENU_CLOSE_POSITION,
  CHART_CONTEXT_MENU_CREATE_ORDER,
  CHART_CONTEXT_MENU_DRAWINGS,
  CHART_CONTEXT_MENU_IGNORE_SELECTOR,
  CHART_CONTEXT_MENU_RESET,
  CHART_CONTEXT_MENU_SELL,
  CHART_CONTEXT_MENU_SNAPSHOT,
} from './chartContextMenuConstants';

export type ChartContextMenuItemId =
  | 'create_order'
  | 'buy'
  | 'sell'
  | 'close_position'
  | 'drawings'
  | 'reset'
  | 'snapshot';

export interface ChartContextMenuItem {
  id: ChartContextMenuItemId;
  label: string;
  /** `order` rows stage the trade ticket; `position` is the flatten SSOT row. */
  kind: 'order' | 'position' | 'submenu' | 'view';
  /** Render a divider above this row. */
  dividerBefore?: boolean;
}

export interface ChartContextMenuInput {
  symbol: string;
  /** Price under the cursor; null when the series cannot resolve a coordinate. */
  price: number | null;
  /** Share count the ticket would receive (see `defaultTicketQty`). */
  quantityValue: string;
  hasPosition: boolean;
}

/** Same formatter the ticket seeds with, so the label matches the staged price. */
export function chartMenuPriceLabel(price: number): string {
  return formatSeedPrice(price);
}

export function chartContextMenuItems(
  input: ChartContextMenuInput,
): ChartContextMenuItem[] {
  const items: ChartContextMenuItem[] = [];
  const symbol = input.symbol.trim().toUpperCase();
  const priced = input.price != null && Number.isFinite(input.price) && input.price > 0;

  if (priced) {
    const price = chartMenuPriceLabel(input.price as number);
    items.push({
      id: 'create_order',
      label: `${CHART_CONTEXT_MENU_CREATE_ORDER} @${price}`,
      kind: 'order',
    });
    items.push({
      id: 'buy',
      label: `${CHART_CONTEXT_MENU_BUY} ${symbol} ${input.quantityValue} @${price}`,
      kind: 'order',
    });
    items.push({
      id: 'sell',
      label: `${CHART_CONTEXT_MENU_SELL} ${symbol} ${input.quantityValue} @${price}`,
      kind: 'order',
    });
  }

  if (input.hasPosition) {
    items.push({
      id: 'close_position',
      label: CHART_CONTEXT_MENU_CLOSE_POSITION,
      kind: 'position',
      dividerBefore: priced,
    });
  }

  items.push({
    id: 'drawings',
    label: CHART_CONTEXT_MENU_DRAWINGS,
    kind: 'submenu',
    dividerBefore: items.length > 0,
  });
  items.push({ id: 'reset', label: CHART_CONTEXT_MENU_RESET, kind: 'view', dividerBefore: true });
  items.push({ id: 'snapshot', label: CHART_CONTEXT_MENU_SNAPSHOT, kind: 'view' });
  return items;
}

/**
 * The chart menu listens natively on `.chart-body`, which fires before React
 * re-dispatches the same event at the root -- so the position tag's
 * `stopPropagation` cannot suppress us. Skip its subtree explicitly instead.
 */
export function shouldOpenChartContextMenu(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return true;
  return !target.closest(CHART_CONTEXT_MENU_IGNORE_SELECTOR);
}
