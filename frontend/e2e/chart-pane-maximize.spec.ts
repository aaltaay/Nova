import { expect, test } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('Trader chart pane maximize', () => {
  test('double-click fills the chart grid only; Esc restores rails', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    const grid = page.getByTestId('chart-grid');
    const cell = page.getByTestId('chart-grid-cell-5Min');
    await expect(grid).toBeVisible();
    await expect(page.getByTestId('stock-view-rail')).toBeVisible();

    await cell.locator('.chart-body').dblclick({ position: { x: 40, y: 40 } });
    await expect(grid).toHaveClass(/chart-grid--pane-maximized/);
    await expect(grid).toHaveAttribute('data-maximized-pane', '5Min');
    await expect(cell).toHaveClass(/chart-grid-cell--maximized/);
    await expect(page.getByTestId('stock-view-rail')).toBeVisible();
    await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible();
    await page.screenshot({
      path: '/opt/cursor/artifacts/chart-pane-maximized.png',
      fullPage: true,
    });

    await page.keyboard.press('Escape');
    await expect(grid).not.toHaveClass(/chart-grid--pane-maximized/);
    await expect(grid).toHaveAttribute('data-maximized-pane', '');
    await page.screenshot({
      path: '/opt/cursor/artifacts/chart-pane-restored.png',
      fullPage: true,
    });
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('header expand enters fullscreen; Esc exits and keeps the desk', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    const grid = page.getByTestId('chart-grid');
    const cell = page.getByTestId('chart-grid-cell-10Sec');
    await expect(grid).toBeVisible();

    await cell.getByTestId('chart-expand-btn').click();
    await expect(grid).not.toHaveClass(/chart-grid--pane-maximized/);
    const fullscreenClass = await page.evaluate(() => {
      const el = document.fullscreenElement;
      return el instanceof HTMLElement ? el.className : '';
    });
    expect(fullscreenClass).toContain('chart-portal-host');
    await expect(page.locator('[data-testid="chart-portal-host"][data-chart-fullscreen="1"]')).toHaveCount(1);

    await page.keyboard.press('Escape');
    await expect.poll(async () => page.evaluate(() => document.fullscreenElement === null)).toBe(true);
    await expect(grid).not.toHaveClass(/chart-grid--pane-maximized/);
    await expect(page.getByTestId('stock-view-rail')).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Esc after fullscreen leaves a grid-maximized desk intact', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    const grid = page.getByTestId('chart-grid');
    const cell = page.getByTestId('chart-grid-cell-5Min');
    await cell.locator('.chart-body').dblclick({ position: { x: 40, y: 40 } });
    await expect(grid).toHaveAttribute('data-maximized-pane', '5Min');

    await cell.getByTestId('chart-expand-btn').click();
    await expect.poll(async () => page.evaluate(() => document.fullscreenElement !== null)).toBe(true);
    await expect(grid).toHaveAttribute('data-maximized-pane', '5Min');

    await page.keyboard.press('Escape');
    await expect.poll(async () => page.evaluate(() => document.fullscreenElement === null)).toBe(true);
    await expect(grid).toHaveAttribute('data-maximized-pane', '5Min');
    await expect(page.getByTestId('stock-view-rail')).toBeVisible();
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
