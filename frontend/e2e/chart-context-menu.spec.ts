import { test, expect, type Page } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';
import { routeSampleBars } from './helpers/sampleBars';

const ARTIFACTS = '/opt/cursor/artifacts';

async function openSampleTrader(page: Page) {
  await routeSampleBars(page);
  await page.goto('/?view=sample&symbol=SMPL');
  await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible();
  const chart = page.locator('.chart-body').first();
  await expect(chart).toBeVisible();
  await expect(page.locator('[data-testid^="ticker-chart-"]').first()).toHaveAttribute(
    'data-bar-count',
    /[1-9]/,
  );
  return chart;
}

/** Right-click inside the plot area, away from the position tag in the corner. */
async function rightClickChart(page: Page, chart = page.locator('.chart-body').first()) {
  const box = await chart.boundingBox();
  expect(box).toBeTruthy();
  if (!box) throw new Error('chart body has no box');
  await page.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.6, {
    button: 'right',
  });
  return box;
}

test.describe('Trader chart right-click context menu', () => {
  test('opens at the cursor with Webull rows priced off the chart', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openSampleTrader(page);
    await rightClickChart(page);

    const menu = page.getByTestId('chart-context-menu');
    await expect(menu).toBeVisible();
    await expect(page.getByTestId('chart-context-menu-create_order')).toHaveText(
      /^Create New Order @\d+\.\d{2}$/,
    );
    await expect(page.getByTestId('chart-context-menu-buy')).toHaveText(
      /^Buy SMPL \d+ @\d+\.\d{2}$/,
    );
    await expect(page.getByTestId('chart-context-menu-sell')).toHaveText(
      /^Sell SMPL \d+ @\d+\.\d{2}$/,
    );
    // Sample desk holds SMPL 200 -- the flatten row is the shared SSOT button.
    await expect(page.getByTestId('chart-context-menu-close-position')).toHaveText(
      'Close Position',
    );
    await expect(page.getByTestId('chart-context-menu-view_details')).toHaveText(
      'View Trade Details',
    );
    await expect(page.getByTestId('chart-context-menu-show_layers')).toBeVisible();
    await expect(page.getByTestId('chart-context-menu-create_alert')).toBeDisabled();
    await expect(page.getByTestId('chart-context-menu-add_to_watchlist')).toBeDisabled();
    await expect(page.getByTestId('chart-context-menu-reset')).toBeVisible();
    await expect(page.getByTestId('chart-context-menu-snapshot')).toBeVisible();
    await expect(page.getByTestId('chart-context-menu-hint')).toContainText(
      'trade ticket',
    );
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-open.png`,
      fullPage: true,
    });

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Escape and click-outside dismiss it', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openSampleTrader(page);

    await rightClickChart(page);
    await expect(page.getByTestId('chart-context-menu')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    await rightClickChart(page);
    await expect(page.getByTestId('chart-context-menu')).toBeVisible();
    await page.getByTestId('chart-desk-toolbar').click({ position: { x: 2, y: 2 } });
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Buy stages the trade ticket instead of placing an order', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openSampleTrader(page);
    await rightClickChart(page);

    const buy = page.getByTestId('chart-context-menu-buy');
    const label = (await buy.textContent()) ?? '';
    const price = label.split('@')[1]?.trim();
    expect(price, `no price in "${label}"`).toMatch(/^\d+\.\d{2}$/);
    await buy.click();
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    const ticket = page.locator('form.manual-order-ticket').first();
    await expect(ticket).toBeVisible();
    await expect(
      ticket.locator('.manual-order-side button', { hasText: 'Buy' }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(ticket.locator('#manual-order-limit')).toHaveValue(price!);
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-buy-staged.png`,
      fullPage: true,
    });

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Sell stages a SELL ticket at the same price', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openSampleTrader(page);
    await rightClickChart(page);

    const sell = page.getByTestId('chart-context-menu-sell');
    const price = ((await sell.textContent()) ?? '').split('@')[1]?.trim();
    await sell.click();

    const ticket = page.locator('form.manual-order-ticket').first();
    await expect(
      ticket.locator('.manual-order-side button', { hasText: 'Sell' }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(ticket.locator('#manual-order-limit')).toHaveValue(price!);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Drawings submenu arms an existing draw tool', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const chart = await openSampleTrader(page);
    await rightClickChart(page, chart);

    await page.getByTestId('chart-context-menu-drawings').click();
    const submenu = page.getByTestId('chart-context-menu-drawings-submenu');
    await expect(submenu).toBeVisible();
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-drawings.png`,
      fullPage: true,
    });

    await page.getByTestId('chart-context-menu-tool-HorizontalLine').click();
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);
    await expect(chart).toHaveAttribute('data-active-draw-tool', 'HorizontalLine');

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('right-click on the Long/Short tag keeps the position menu', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openSampleTrader(page);

    await page.getByTestId('chart-position-tag-btn').first().click({ button: 'right' });
    await expect(page.getByTestId('chart-position-menu')).toBeVisible();
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('still opens while the pane is in header fullscreen (#117)', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openSampleTrader(page);

    const cell = page.getByTestId('chart-grid-cell-5Min');
    await cell.getByTestId('chart-expand-btn').click();
    await expect
      .poll(async () => page.evaluate(() => document.fullscreenElement !== null))
      .toBe(true);

    // A document.body portal would be invisible here -- only the fullscreen
    // element's subtree paints.
    await rightClickChart(page, cell.locator('.chart-body'));
    const menu = page.getByTestId('chart-context-menu');
    await expect(menu).toBeVisible();
    expect(
      await menu.evaluate((node) => document.fullscreenElement?.contains(node) ?? false),
    ).toBe(true);
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-fullscreen.png`,
      fullPage: true,
    });

    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Show Layers toggles the same indicator SSOT as the desk toolbar', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openSampleTrader(page);
    await rightClickChart(page);

    await page.getByTestId('chart-context-menu-show_layers').click();
    const vwap = page.getByTestId('chart-context-menu-layer-vwap');
    await expect(vwap).toBeVisible();
    const before = await vwap.getAttribute('aria-checked');
    await vwap.click();
    await expect(page.getByTestId('chart-context-menu')).toBeVisible();
    await expect(vwap).toHaveAttribute('aria-checked', before === 'true' ? 'false' : 'true');
    await page.screenshot({
      path: `${ARTIFACTS}/chart-context-menu-layers.png`,
      fullPage: true,
    });

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('View Trade Details docks Positions through the same event as the tag', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await openSampleTrader(page);
    await rightClickChart(page);
    await page.getByTestId('chart-context-menu-view_details').click();
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);
    await expect(page.getByTestId('stock-view-positions')).toBeVisible();

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('does not break double-click pane maximize', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    const chart = await openSampleTrader(page);
    await rightClickChart(page, chart);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('chart-context-menu')).toHaveCount(0);

    const box = await chart.boundingBox();
    if (!box) throw new Error('chart body has no box');
    await page.mouse.dblclick(box.x + box.width * 0.5, box.y + box.height * 0.5);
    await expect(page.locator('.chart-grid--pane-maximized')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.chart-grid--pane-maximized')).toHaveCount(0);

    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
