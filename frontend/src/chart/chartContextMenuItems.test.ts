/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import {
  chartContextMenuItems,
  chartMenuPriceLabel,
  shouldOpenChartContextMenu,
} from './chartContextMenuItems';

const BASE = { symbol: 'smpl', price: 4.2, quantityValue: '100', hasPosition: false };

describe('chartContextMenuItems', () => {
  it('labels the Webull order rows with the price under the cursor', () => {
    const labels = chartContextMenuItems(BASE).map((item) => item.label);
    expect(labels).toContain('Create New Order @4.20');
    expect(labels).toContain('Buy SMPL 100 @4.20');
    expect(labels).toContain('Sell SMPL 100 @4.20');
  });

  it('omits order rows when the series cannot price the cursor', () => {
    const ids = chartContextMenuItems({ ...BASE, price: null }).map((item) => item.id);
    expect(ids).toEqual(['drawings', 'reset', 'snapshot']);
  });

  it('shows Close Position only while a position is open', () => {
    expect(chartContextMenuItems(BASE).some((i) => i.id === 'close_position')).toBe(false);
    const withPos = chartContextMenuItems({ ...BASE, hasPosition: true });
    expect(withPos.some((i) => i.id === 'close_position')).toBe(true);
    expect(withPos.find((i) => i.id === 'close_position')?.kind).toBe('position');
  });

  it('never offers a surface Nova cannot perform', () => {
    const ids = chartContextMenuItems({ ...BASE, hasPosition: true }).map((i) => i.id);
    expect(ids).not.toContain('create_alert');
    expect(ids).not.toContain('add_to_watchlist');
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
