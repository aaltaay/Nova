/**
 * Pure model for the chart right-click menu.
 *
 * Money rows, layers and the watch list toggle are real Nova actions. Create
 * Alert has no price-alert API, so it ships disabled with a reason (#116).
 * Line Style and Chart Settings still have no surface -- omit.
 */
import { formatSeedPrice } from '../ibkr/tradeDefaultSeed';
import { CHART_POSITION_MENU_VIEW_DETAILS } from './positionOverlayConstants';
import {
  CHART_CONTEXT_MENU_BOT_ALLOWLIST_ADD,
  CHART_CONTEXT_MENU_BOT_ALLOWLIST_REMOVE,
  CHART_CONTEXT_MENU_ALERT_REASON,
  CHART_CONTEXT_MENU_BUY,
  CHART_CONTEXT_MENU_CLOSE_POSITION,
  CHART_CONTEXT_MENU_CREATE_ALERT,
  CHART_CONTEXT_MENU_CREATE_ORDER,
  CHART_CONTEXT_MENU_DRAWINGS,
  CHART_CONTEXT_MENU_IGNORE_SELECTOR,
  CHART_CONTEXT_MENU_RESET,
  CHART_CONTEXT_MENU_SELL,
  CHART_CONTEXT_MENU_SHOW_LAYERS,
  CHART_CONTEXT_MENU_SNAPSHOT,
  CHART_CONTEXT_MENU_WATCH_ADD,
  CHART_CONTEXT_MENU_WATCH_REMOVE,
} from './chartContextMenuConstants';

export type ChartContextMenuItemId =
  | 'create_order'
  | 'buy'
  | 'sell'
  | 'close_position'
  | 'view_details'
  | 'drawings'
  | 'show_layers'
  | 'create_alert'
  | 'watch_list_add'
  | 'watch_list_remove'
  | 'bot_allowlist_add'
  | 'bot_allowlist_remove'
  | 'reset'
  | 'snapshot';

export type ChartContextMenuItemKind =
  | 'order'
  | 'position'
  | 'submenu'
  | 'view'
  | 'unavailable'
  | 'action';

export interface ChartContextMenuItem {
  id: ChartContextMenuItemId;
  label: string;
  kind: ChartContextMenuItemKind;
  /** Render a divider above this row. */
  dividerBefore?: boolean;
  /** Honest disable reason -- only on `unavailable` rows. */
  reason?: string;
}

export interface ChartContextMenuInput {
  symbol: string;
  /** Price under the cursor; null when the series cannot resolve a coordinate. */
  price: number | null;
  /** Share count the ticket would receive (see `defaultTicketQty`). */
  quantityValue: string;
  hasPosition: boolean;
  allowlisted?: boolean;
  /** On the operator's watch list. */
  watched?: boolean;
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
    items.push({
      id: 'view_details',
      label: CHART_POSITION_MENU_VIEW_DETAILS,
      kind: 'view',
    });
  }

  items.push({
    id: 'drawings',
    label: CHART_CONTEXT_MENU_DRAWINGS,
    kind: 'submenu',
    dividerBefore: items.length > 0,
  });
  items.push({
    id: 'show_layers',
    label: CHART_CONTEXT_MENU_SHOW_LAYERS,
    kind: 'submenu',
  });
  items.push({
    id: 'create_alert',
    label: CHART_CONTEXT_MENU_CREATE_ALERT,
    kind: 'unavailable',
    reason: CHART_CONTEXT_MENU_ALERT_REASON,
  });
  items.push({
    id: input.watched ? 'watch_list_remove' : 'watch_list_add',
    label: input.watched ? CHART_CONTEXT_MENU_WATCH_REMOVE : CHART_CONTEXT_MENU_WATCH_ADD,
    kind: 'action',
  });
  items.push({
    id: input.allowlisted ? 'bot_allowlist_remove' : 'bot_allowlist_add',
    label: input.allowlisted
      ? CHART_CONTEXT_MENU_BOT_ALLOWLIST_REMOVE
      : CHART_CONTEXT_MENU_BOT_ALLOWLIST_ADD,
    kind: 'action',
    dividerBefore: true,
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
