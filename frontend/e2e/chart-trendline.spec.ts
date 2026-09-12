import { test, expect } from '@playwright/test';
import { attachErrorCollector } from './helpers/errorCollector';

test.describe('D-010 Trend Line two-click place', () => {
  test('dropdown opens and arms a tool on the sample desk', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible();

    await page.getByRole('button', { name: 'Line drawing tools' }).click();
    const menu = page.getByTestId('chart-draw-tools-menu');
    await expect(menu).toBeVisible();
    await expect(menu.getByRole('menuitemradio', { name: /Trendline/ })).toBeVisible();
    await page.screenshot({
      path: '/opt/cursor/artifacts/d109-draw-tools-menu.png',
      fullPage: true,
    });
    await menu.getByRole('menuitemradio', { name: /Horizontal Line/ }).click();

    const chart = page.locator('.chart-body').first();
    await expect(chart).toHaveAttribute('data-active-draw-tool', 'HorizontalLine');
    await expect(menu).toHaveCount(0);
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });

  test('Use Trendline arms the chart body for pointerup place', async ({ page }) => {
    const { errors } = attachErrorCollector(page);
    await page.goto('/?view=sample&symbol=SMPL');
    await expect(page.getByTestId('chart-desk-toolbar')).toBeVisible();

    const chart = page.locator('.chart-body').first();
    await expect(chart).toBeVisible();
    await page.getByRole('button', { name: 'Use Trendline' }).click();
    await expect(chart).toHaveAttribute('data-active-draw-tool', 'TrendLine');
    await page.screenshot({
      path: '/opt/cursor/artifacts/d010-trendline-armed.png',
      fullPage: true,
    });

    const box = await chart.boundingBox();
    expect(box).toBeTruthy();
    if (!box) return;
    await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.65);
    await page.mouse.click(box.x + box.width * 0.7, box.y + box.height * 0.35);

    // Offline sample has an empty IBKR time scale, so anchors cannot convert.
    // A click must not throw, and the tool must stay armed until a real series exists.
    await expect(chart).toHaveAttribute('data-active-draw-tool', 'TrendLine');
    expect(errors, `uncaught errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
