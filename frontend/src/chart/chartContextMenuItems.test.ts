/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import {
  chartContextMenuItems,
  chartMenuPriceLabel,
  shouldOpenChartContextMenu,
} from './chartContextMenuItems';
import {
  CHART_CONTEXT_MENU_ALERT_REASON,
  CHART_CONTEXT_MENU_WATCHLIST_REASON,
} from './chartContextMenuConstants';

const BASE = { symbol: 'smpl', price: 4.2, quantityValue: '100', hasPosition: false };

describe('chartContextMenuItems', () => {
  it('labels the Webull order rows with the price under the cursor', () => {
    const labels = chartContextMenuItems(BASE).map((item) => item.label);
    expect(labels).toContain('Create New Order @4.20');
    expect(labels).toContain('Buy SMPL 100 @4.20');
    expect(labels).toContain('Sell SMPL 100 @4.20');
  });

  it('keeps view actions when the series cannot price the cursor', () => {
    const ids = chartContextMenuItems({ ...BASE, price: null }).map((item) => item.id);
    expect(ids).toEqual([
      'drawings',
      'show_layers',
      'create_alert',
      'add_to_watchlist',
      'bot_allowlist_add',
      'reset',
      'snapshot',
    ]);
  });

  it('shows Close Position and View Trade Details only while a position is open', () => {
    const closed = chartContextMenuItems(BASE);
    expect(closed.some((i) => i.id === 'close_position')).toBe(false);
    expect(closed.some((i) => i.id === 'view_details')).toBe(false);
    const withPos = chartContextMenuItems({ ...BASE, hasPosition: true });
    expect(withPos.find((i) => i.id === 'close_position')?.kind).toBe('position');
    expect(withPos.find((i) => i.id === 'view_details')?.label).toBe('View Trade Details');
  });

  it('disables Create Alert and Add to Watchlist with an honest reason', () => {
    const items = chartContextMenuItems(BASE);
    const alert = items.find((i) => i.id === 'create_alert');
    const watch = items.find((i) => i.id === 'add_to_watchlist');
    expect(alert).toEqual(
      expect.objectContaining({
        kind: 'unavailable',
        reason: CHART_CONTEXT_MENU_ALERT_REASON,
      }),
    );
    expect(watch).toEqual(
      expect.objectContaining({
        kind: 'unavailable',
        reason: CHART_CONTEXT_MENU_WATCHLIST_REASON,
      }),
    );
  });

  it('adds or removes the bot allowlist from the live menu', () => {
    const add = chartContextMenuItems(BASE).find((i) => i.id === 'bot_allowlist_add');
    expect(add?.kind).toBe('action');
    const remove = chartContextMenuItems({ ...BASE, allowlisted: true }).find(
      (i) => i.id === 'bot_allowlist_remove',
    );
    expect(remove?.label).toBe('Remove from bot allowlist');
  });

  it('exposes Show Layers and omits surfaces Nova cannot perform', () => {
    const ids = chartContextMenuItems({ ...BASE, hasPosition: true }).map((i) => i.id);
    expect(ids).toContain('show_layers');
    expect(ids).not.toContain('line_style');
    expect(ids).not.toContain('chart_settings');
  });

  it('formats the price the same way the ticket seeds it', () => {
    expect(chartMenuPriceLabel(147.766)).toBe('147.77');
  });
});

describe('shouldOpenChartContextMenu', () => {
  it('opens on the plot area', () => {
    const canvas = document.createElement('canvas');
    document.body.appendChild(canvas);
    expect(shouldOpenChartContextMenu(canvas)).toBe(true);
    canvas.remove();
  });

  it('defers to the Long/Short tag, which owns its own menu', () => {
    const tag = document.createElement('div');
    tag.className = 'chart-position-tag';
    const badge = document.createElement('button');
    tag.appendChild(badge);
    document.body.appendChild(tag);
    expect(shouldOpenChartContextMenu(badge)).toBe(false);
    tag.remove();
  });

  it('does not reopen over itself', () => {
    const menu = document.createElement('div');
    menu.className = 'chart-context-menu';
    document.body.appendChild(menu);
    expect(shouldOpenChartContextMenu(menu)).toBe(false);
    menu.remove();
  });
});
